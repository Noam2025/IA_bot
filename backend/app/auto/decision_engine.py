# backend/app/auto/decision_engine.py
# -*- coding: utf-8 -*-
"""
Decision engine - stratégie Momentum-Breakout + Volatility Expansion.

Expose pour le backend FastAPI :

- evaluate_and_maybe_trade(symbol, timeframe, candles, equity, daily_pnl=0.0)
- get_last_decision()
- get_recent_decisions(limit=100)
- get_recent_orders(limit=100)
- get_pnl_stats()

Les candles doivent contenir au minimum :
    open, high, low, close, volume, timestamp (ou ts)
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from collections import deque
from typing import Any, Dict, List, Optional, Deque
from datetime import datetime, date

import numpy as np
import pandas as pd


# =====================================================================
#                 PARAMÈTRES GLOBAUX DE LA STRATÉGIE
# =====================================================================

# Objectif agressif -> 1% de risk par trade
RISK_PER_TRADE = 0.01          # 1% de l'equity par trade
MAX_DAILY_LOSS = 0.10          # -10% journalier -> stop des nouveaux trades
MAX_OPEN_TRADES = 5            # si tu gères plusieurs positions
MAX_LEVERAGE = 20              # notionnel max = equity * 20

MIN_CANDLES_REQUIRED = 60      # minimum de bougies pour indicateurs fiables

# Files d’historique pour dashboard / API
DECISIONS: Deque[Dict[str, Any]] = deque(maxlen=500)
ORDERS: Deque[Dict[str, Any]] = deque(maxlen=1000)

# PnL journalier (à raffiner côté exécution réelle)
DAILY_PNL: float = 0.0
DAILY_DATE: Optional[date] = None


# =====================================================================
#                              DATA CLASSES
# =====================================================================

@dataclass
class Signal:
    symbol: str
    timeframe: str
    action: str        # "LONG", "SHORT", "NONE"
    reason: str
    mode: str          # "MOMENTUM_BREAKOUT"
    confidence: float
    entry: Optional[float] = None
    sl: Optional[float] = None
    tp1: Optional[float] = None
    tp2: Optional[float] = None
    tp3: Optional[float] = None


@dataclass
class Order:
    symbol: str
    side: str          # "BUY" ou "SELL"
    qty: float
    entry: float
    sl: float
    tp1: float
    tp2: float
    tp3: float
    risk_perc: float
    leverage: float
    created_at: float  # timestamp
    meta: Dict[str, Any]


# =====================================================================
#                      FONCTIONS D’INDICATEURS
# =====================================================================

def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)

    gain_series = pd.Series(gain, index=series.index)
    loss_series = pd.Series(loss, index=series.index)

    avg_gain = gain_series.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss_series.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / (avg_loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]

    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    return atr


def _bollinger_bands(series: pd.Series, period: int = 20, num_std: float = 2.0):
    ma = series.rolling(period).mean()
    std = series.rolling(period).std()
    upper = ma + num_std * std
    lower = ma - num_std * std
    return ma, upper, lower


def _macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = _ema(series, fast)
    ema_slow = _ema(series, slow)
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    hist = macd - signal_line
    return macd, signal_line, hist


def compute_indicators(candles: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    candles: liste de dicts avec au minimum les clés:
        - "open", "high", "low", "close", "volume"
        - "ts" ou "timestamp" (en ms ou s)
    Retourne un DataFrame avec toutes les colonnes nécessaires à la stratégie.
    """
    if not candles:
        raise ValueError("Liste de candles vide")

    df = pd.DataFrame(candles)

    # Normalisation des colonnes temps
    if "ts" in df.columns:
        df["timestamp"] = df["ts"]
    if "timestamp" not in df.columns:
        raise ValueError("Il manque une colonne 'timestamp' ou 'ts' dans les candles")

    # Conversion timestamp -> datetime (utile debug)
    if df["timestamp"].max() > 10_000_000_000:  # ms
        df["dt"] = pd.to_datetime(df["timestamp"], unit="ms")
    else:  # s
        df["dt"] = pd.to_datetime(df["timestamp"], unit="s")

    df = df.sort_values("timestamp").reset_index(drop=True)

    for col in ["open", "high", "low", "close", "volume"]:
        if col not in df.columns:
            raise ValueError(f"Colonne '{col}' manquante dans les candles")

    # Indicateurs de base
    df["ema20"] = _ema(df["close"], 20)
    df["ema50"] = _ema(df["close"], 50)

    df["atr14"] = _atr(df, 14)

    df["rsi14"] = _rsi(df["close"], 14)

    df["macd"], df["macd_signal"], df["macd_hist"] = _macd(df["close"], 12, 26, 9)

    df["bb_mid"], df["bb_upper"], df["bb_lower"] = _bollinger_bands(df["close"], 20, 2.0)

    df["hh_20"] = df["high"].rolling(20).max()
    df["ll_20"] = df["low"].rolling(20).min()

    df["vol_ma20"] = df["volume"].rolling(20).mean()

    return df


# =====================================================================
#                   LOGIQUE DE GÉNÉRATION DE SIGNAL
# =====================================================================

def _passes_filters(row: pd.Series, prev_row: pd.Series) -> (bool, str):
    """
    Filtre les conditions de marché défavorables.
    Retourne (ok, reason_if_not_ok).
    """
    close = row["close"]
    atr = row["atr14"]

    if pd.isna(atr) or close <= 0:
        return False, "Indicateurs insuffisants (ATR NaN ou close <= 0)."

    # 1) Volatilité minimale ~ 0.3%
    if atr / close < 0.003:
        return False, "Volatilité trop faible (ATR/close < 0.3%)."

    # 2) Pas de tendance si EMA20 ~ EMA50
    ema20 = row["ema20"]
    ema50 = row["ema50"]
    if pd.isna(ema20) or pd.isna(ema50):
        return False, "Indicateurs de tendance insuffisants (EMA NaN)."

    if abs(ema20 - ema50) / close < 0.001:
        return False, "Pas de direction claire (EMA20 ~ EMA50)."

    # 3) Volume très faible
    vol = row["volume"]
    vol_ma = row["vol_ma20"]
    if pd.isna(vol_ma) or vol_ma == 0:
        return False, "Volume moyen insuffisant."

    if vol < 0.5 * vol_ma:
        return False, "Volume trop faible (< 50% de la moyenne)."

    # 4) ATR doit être en expansion vs bougie précédente
    prev_atr = prev_row["atr14"]
    if not pd.isna(prev_atr) and atr <= prev_atr:
        return False, "Volatilité non croissante (ATR pas en expansion)."

    return True, ""


def _build_long_signal(symbol: str, timeframe: str, df: pd.DataFrame) -> Signal:
    row = df.iloc[-1]
    prev_row = df.iloc[-2]

    ok, reason = _passes_filters(row, prev_row)
    if not ok:
        return Signal(symbol, timeframe, "NONE", reason, "MOMENTUM_BREAKOUT", 0.0)

    close = row["close"]
    ema20 = row["ema20"]
    ema50 = row["ema50"]
    rsi = row["rsi14"]
    macd_hist = row["macd_hist"]
    hh_20 = row["hh_20"]
    vol = row["volume"]
    vol_ma = row["vol_ma20"]
    bb_upper = row["bb_upper"]
    atr = row["atr14"]

    # Tendances et conditions
    trend_up = ema20 > ema50
    breakout = (close > hh_20) and (vol > 1.2 * vol_ma) and (close > bb_upper)
    rsi_cond = rsi > 55
    macd_cond = (macd_hist > 0) and (macd_hist >= df["macd_hist"].iloc[-2])

    if not trend_up:
        return Signal(symbol, timeframe, "NONE", "Pas de tendance haussière claire.", "MOMENTUM_BREAKOUT", 0.0)

    if not breakout:
        return Signal(symbol, timeframe, "NONE", "Pas de breakout haussier valide.", "MOMENTUM_BREAKOUT", 0.0)

    if not rsi_cond:
        return Signal(symbol, timeframe, "NONE", "RSI pas assez fort pour un long (>55).", "MOMENTUM_BREAKOUT", 0.0)

    if not macd_cond:
        return Signal(symbol, timeframe, "NONE", "MACD histogram non haussier / non croissant.", "MOMENTUM_BREAKOUT", 0.0)

    entry = float(close)
    sl = float(hh_20 - 0.5 * atr)
    tp1 = float(entry + 1.0 * atr)
    tp2 = float(entry + 2.0 * atr)
    tp3 = float(entry + 3.0 * atr)

    if sl >= entry:
        return Signal(symbol, timeframe, "NONE", "SL calculé invalide (>= entry).", "MOMENTUM_BREAKOUT", 0.0)

    reason = "Long breakout haussier validé (trend, volume, RSI, MACD, ATR)."
    confidence = 0.8

    return Signal(
        symbol=symbol,
        timeframe=timeframe,
        action="LONG",
        reason=reason,
        mode="MOMENTUM_BREAKOUT",
        confidence=confidence,
        entry=entry,
        sl=sl,
        tp1=tp1,
        tp2=tp2,
        tp3=tp3,
    )


def _build_short_signal(symbol: str, timeframe: str, df: pd.DataFrame) -> Signal:
    row = df.iloc[-1]
    prev_row = df.iloc[-2]

    ok, reason = _passes_filters(row, prev_row)
    if not ok:
        return Signal(symbol, timeframe, "NONE", reason, "MOMENTUM_BREAKOUT", 0.0)

    close = row["close"]
    ema20 = row["ema20"]
    ema50 = row["ema50"]
    rsi = row["rsi14"]
    macd_hist = row["macd_hist"]
    ll_20 = row["ll_20"]
    vol = row["volume"]
    vol_ma = row["vol_ma20"]
    bb_lower = row["bb_lower"]
    atr = row["atr14"]

    trend_down = ema20 < ema50
    breakout = (close < ll_20) and (vol > 1.2 * vol_ma) and (close < bb_lower)
    rsi_cond = rsi < 45
    macd_cond = (macd_hist < 0) and (macd_hist <= df["macd_hist"].iloc[-2])

    if not trend_down:
        return Signal(symbol, timeframe, "NONE", "Pas de tendance baissière claire.", "MOMENTUM_BREAKOUT", 0.0)

    if not breakout:
        return Signal(symbol, timeframe, "NONE", "Pas de breakout baissier valide.", "MOMENTUM_BREAKOUT", 0.0)

    if not rsi_cond:
        return Signal(symbol, timeframe, "NONE", "RSI pas assez faible pour un short (<45).", "MOMENTUM_BREAKOUT", 0.0)

    if not macd_cond:
        return Signal(symbol, timeframe, "NONE", "MACD histogram non baissier / non décroissant.", "MOMENTUM_BREAKOUT", 0.0)

    entry = float(close)
    sl = float(ll_20 + 0.5 * atr)
    tp1 = float(entry - 1.0 * atr)
    tp2 = float(entry - 2.0 * atr)
    tp3 = float(entry - 3.0 * atr)

    if sl <= entry:
        return Signal(symbol, timeframe, "NONE", "SL calculé invalide (<= entry).", "MOMENTUM_BREAKOUT", 0.0)

    reason = "Short breakout baissier validé (trend, volume, RSI, MACD, ATR)."
    confidence = 0.8

    return Signal(
        symbol=symbol,
        timeframe=timeframe,
        action="SHORT",
        reason=reason,
        mode="MOMENTUM_BREAKOUT",
        confidence=confidence,
        entry=entry,
        sl=sl,
        tp1=tp1,
        tp2=tp2,
        tp3=tp3,
    )


def generate_signal(symbol: str, timeframe: str, df: pd.DataFrame) -> Signal:
    """
    Choisit entre signal LONG, SHORT ou NONE selon la dernière bougie.
    """
    if len(df) < MIN_CANDLES_REQUIRED:
        return Signal(
            symbol=symbol,
            timeframe=timeframe,
            action="NONE",
            reason=f"Pas assez d'historique ({len(df)} < {MIN_CANDLES_REQUIRED}).",
            mode="MOMENTUM_BREAKOUT",
            confidence=0.0,
        )

    row = df.iloc[-1]
    ema20 = row["ema20"]
    ema50 = row["ema50"]

    # Priorité à la tendance dominante
    if ema20 < ema50:
        short_sig = _build_short_signal(symbol, timeframe, df)
        if short_sig.action == "SHORT":
            return short_sig
        long_sig = _build_long_signal(symbol, timeframe, df)
        return long_sig
    else:
        long_sig = _build_long_signal(symbol, timeframe, df)
        if long_sig.action == "LONG":
            return long_sig
        short_sig = _build_short_signal(symbol, timeframe, df)
        return short_sig


# =====================================================================
#             SIZING / RISK & INTÉGRATION AVEC LE BACKEND
# =====================================================================

def _compute_position_size(equity: float, entry: float, sl: float) -> float:
    """
    risk_$ = equity * RISK_PER_TRADE = (entry - sl) * qty  => qty = risk_$ / distance
    """
    risk_usd = equity * RISK_PER_TRADE
    distance = abs(entry - sl)
    if distance <= 0:
        return 0.0

    qty = risk_usd / distance
    return float(max(qty, 0.0))


def _respect_leverage_constraints(equity: float, entry: float, qty: float) -> float:
    """
    S'assure que le notionnel = qty * entry ne dépasse pas equity * MAX_LEVERAGE.
    """
    notional = qty * entry
    max_notional = equity * MAX_LEVERAGE
    if notional <= max_notional:
        return qty
    if entry <= 0:
        return 0.0
    return max_notional / entry


def evaluate_and_maybe_trade(
    symbol: str,
    timeframe: str,
    candles: List[Dict[str, Any]],
    equity: float,
    daily_pnl: float = 0.0,
) -> Dict[str, Any]:
    """
    Fonction principale appelée par le backend à chaque rafraîchissement.

    Retour :
      {
        "decision": {...},  # dict décrivant le signal
        "order": {...} ou None
      }
    """
    global DAILY_PNL, DAILY_DATE

    now_date = datetime.utcnow().date()
    if DAILY_DATE is None or DAILY_DATE != now_date:
        DAILY_DATE = now_date
        DAILY_PNL = 0.0

    # Si ton moteur d'exécution fournit déjà le PnL jour, on le prend
    if daily_pnl is not None:
        DAILY_PNL = daily_pnl

    # Sécurité daily loss
    if DAILY_PNL <= -MAX_DAILY_LOSS * equity:
        decision = {
            "symbol": symbol,
            "timeframe": timeframe,
            "action": "NONE",
            "reason": f"Daily loss limit atteint ({DAILY_PNL:.2%}).",
            "mode": "RISK_STOP",
            "confidence": 0.0,
            "timestamp": datetime.utcnow().timestamp(),
        }
        DECISIONS.append(decision)
        return {"decision": decision, "order": None}

    # Calcul des indicateurs
    try:
        df = compute_indicators(candles)
    except Exception as e:
        decision = {
            "symbol": symbol,
            "timeframe": timeframe,
            "action": "NONE",
            "reason": f"Erreur compute_indicators: {e}",
            "mode": "ERROR",
            "confidence": 0.0,
            "timestamp": datetime.utcnow().timestamp(),
        }
        DECISIONS.append(decision)
        return {"decision": decision, "order": None}

    # Génération du signal technique
    sig = generate_signal(symbol, timeframe, df)
    decision_dict = asdict(sig)
    decision_dict["timestamp"] = float(df["timestamp"].iloc[-1])

    # Pas de trade si NONE ou niveaux incomplets
    if sig.action == "NONE" or sig.entry is None or sig.sl is None:
        DECISIONS.append(decision_dict)
        return {"decision": decision_dict, "order": None}

    # Sizing
    qty = _compute_position_size(equity, sig.entry, sig.sl)
    qty = _respect_leverage_constraints(equity, sig.entry, qty)

    if qty <= 0:
        decision_dict["reason"] += " | Taille calculée nulle (qty <= 0)."
        decision_dict["action"] = "NONE"
        DECISIONS.append(decision_dict)
        return {"decision": decision_dict, "order": None}

    side = "BUY" if sig.action == "LONG" else "SELL"
    now_ts = float(df["timestamp"].iloc[-1])

    order = Order(
        symbol=symbol,
        side=side,
        qty=qty,
        entry=sig.entry,
        sl=sig.sl,
        tp1=sig.tp1 if sig.tp1 is not None else sig.entry,
        tp2=sig.tp2 if sig.tp2 is not None else sig.entry,
        tp3=sig.tp3 if sig.tp3 is not None else sig.entry,
        risk_perc=RISK_PER_TRADE,
        leverage=float(MAX_LEVERAGE),
        created_at=now_ts,
        meta={
            "mode": sig.mode,
            "confidence": sig.confidence,
            "reason": sig.reason,
        },
    )

    order_dict = asdict(order)

    DECISIONS.append(decision_dict)
    ORDERS.append(order_dict)

    return {"decision": decision_dict, "order": order_dict}


# =====================================================================
#             FONCTIONS UTILITAIRES POUR BACKEND / DASHBOARD
# =====================================================================

def get_last_decision() -> Optional[Dict[str, Any]]:
    if not DECISIONS:
        return None
    return DECISIONS[-1]


def get_recent_decisions(limit: int = 100) -> List[Dict[str, Any]]:
    """
    Compatibilité avec ton main.py qui importe get_recent_decisions.
    Renvoie la liste des dernières décisions.
    """
    if limit <= 0:
        return []
    return list(DECISIONS)[-limit:]


def get_recent_orders(limit: int = 100) -> List[Dict[str, Any]]:
    if limit <= 0:
        return []
    return list(ORDERS)[-limit:]


def get_pnl_stats() -> Dict[str, Any]:
    """
    Stub minimal : idéalement ton moteur d'exécution doit calculer
    un PnL plus détaillé. Ici on renvoie juste le PnL jour local.
    """
    return {
        "daily_pnl": DAILY_PNL,
        "daily_date": DAILY_DATE.isoformat() if DAILY_DATE else None,
        "info": "PnL conseillé de le calculer côté execution engine.",
    }
