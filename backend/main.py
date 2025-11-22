# -*- coding: utf-8 -*-
"""
Backend FastAPI pour l'IA Trading Bot.

Exposé pour le dashboard Streamlit :
- GET  /api/status
- GET  /api/live
- POST /api/live/start
- POST /api/live/stop
- GET  /api/live/status
- GET  /api/decisions
- GET  /api/orders
- GET  /api/orders/range
- GET  /api/pnl
"""

import time
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import logging

from app.auto.decision_engine import (  # type: ignore
    evaluate_and_maybe_trade,
    get_last_decision,
    get_pnl_stats,
    get_recent_decisions,
    get_recent_orders,
)

# ============================================================
#                           LOGGER
# ============================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ia_trading_backend")


# ============================================================
#                    ETAT GLOBAL SIMPLE
# ============================================================

LIVE_STATE: Dict[str, Any] = {
    "running": False,
    "symbol": "BTCUSDT",
    "tf": "1m",
    "since": None,  # timestamp float de démarrage
}

# ============================================================
#                 MODELES Pydantic
# ============================================================


class LiveParams(BaseModel):
    symbol: str = "BTCUSDT"
    tf: str = "1m"
    limit: int = 200


class LiveStartPayload(BaseModel):
    symbol: str = "BTCUSDT"
    tf: str = "1m"


# ============================================================
#                 GENERATION MOCK OHLCV
# ============================================================


def generate_mock_ohlcv(symbol: str, tf: str, limit: int = 200) -> Dict[str, Any]:
    """
    Génère des bougies OHLCV + quelques indicateurs fake pour alimenter le dashboard.
    """
    now = datetime.now(timezone.utc)
    candles: List[Dict[str, Any]] = []

    price = 30000.0

    if tf.endswith("m"):
        tf_seconds = int(tf.replace("m", "")) * 60
    elif tf.endswith("h"):
        tf_seconds = int(tf.replace("h", "")) * 3600
    else:
        tf_seconds = 60

    for i in range(limit):
        ts = now - timedelta(seconds=tf_seconds * (limit - i))
        ts_float = ts.timestamp()

        change = random.uniform(-15.0, 15.0)
        open_price = price
        close_price = max(price + change, 10.0)
        high_price = max(open_price, close_price) + random.uniform(0, 5)
        low_price = min(open_price, close_price) - random.uniform(0, 5)
        volume = random.uniform(5, 50)

        price = close_price

        candles.append(
            {
                "ts": ts_float * 1000,  # ms
                "open": round(open_price, 2),
                "high": round(high_price, 2),
                "low": round(low_price, 2),
                "close": round(close_price, 2),
                "volume": round(volume, 3),
                # champs indicateurs legacy pour compat front, non utilisés par le moteur v3
                "ema_fast": round(close_price * 0.999, 2),
                "ema_slow": round(close_price * 1.001, 2),
                "rsi": random.uniform(30, 70),
                "atr": random.uniform(50, 150),
            }
        )

    return {
        "symbol": symbol,
        "tf": tf,
        "candles": candles,
    }


# ============================================================
#                     APP + CORS
# ============================================================

app = FastAPI(title="IA Trading Backend", version="1.1.1")

app.add_middleware(
    CORSMiddleware(
        allow_origins=["*"],  # à restreindre plus tard si besoin
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
)


# ============================================================
#                    ENDPOINTS DE BASE
# ============================================================


@app.get("/api/status")
def status() -> Dict[str, Any]:
    """
    Endpoint de santé simple appelé par le dashboard.
    """
    return {
        "ok": True,
        "ts": time.time(),
        "live_state": LIVE_STATE,
        "last_decision": get_last_decision(),
    }


# ============================================================
#                   ENDPOINT LIVE MARCHE
# ============================================================


@app.get("/api/live")
def live_market(
    symbol: str = Query("BTCUSDT"),
    tf: str = Query("1m"),
    limit: int = Query(200, ge=10, le=2000),
) -> Dict[str, Any]:
    """
    Renvoyer un flux OHLCV + indicateurs (mock ou réel plus tard).
    """
    logger.info("GET /api/live symbol=%s tf=%s limit=%s", symbol, tf, limit)
    data = generate_mock_ohlcv(symbol, tf, limit)
    return data


@app.post("/api/live/start")
def live_start(payload: LiveStartPayload = Body(...)) -> Dict[str, Any]:
    """
    Active le mode auto (vu par le dashboard).
    Le véritable trading auto sera ensuite géré par un runner séparé.
    """
    LIVE_STATE["running"] = True
    LIVE_STATE["symbol"] = payload.symbol
    LIVE_STATE["tf"] = payload.tf
    LIVE_STATE["since"] = time.time()

    logger.info("Live mode started: %s", LIVE_STATE)

    # on force une première décision pour initialiser les listes
    mock = generate_mock_ohlcv(payload.symbol, payload.tf, limit=200)
    candles = mock.get("candles", [])
    # TODO: brancher ici l'equity réelle (compte Binance ou autre source)
    equity = 10_000.0
    res = evaluate_and_maybe_trade(
        symbol=payload.symbol,
        timeframe=payload.tf,
        candles=candles,
        equity=equity,
    )

    return {
        "ok": True,
        "live_state": LIVE_STATE,
        "first_decision": res.get("decision"),
    }


@app.post("/api/live/stop")
def live_stop() -> Dict[str, Any]:
    """
    Désactive le flag de mode auto.
    """
    LIVE_STATE["running"] = False
    LIVE_STATE["since"] = None
    logger.info("Live mode stopped")
    return {"ok": True, "live_state": LIVE_STATE}


@app.get("/api/live/status")
def live_status() -> Dict[str, Any]:
    """
    Retourne le flag actuel de mode auto.
    """
    return {
        "status": "running" if LIVE_STATE.get("running") else "stopped",
        "live_state": LIVE_STATE,
    }


# ============================================================
#              ENDPOINTS DÉCISIONS / ORDRES / PNL
# ============================================================


@app.get("/api/decisions")
def decisions(
    limit: int = Query(100, ge=1, le=500),
) -> Dict[str, Any]:
    """
    Renvoie les dernières décisions IA.
    """
    try:
        decisions = get_recent_decisions(limit=limit)
        if not decisions:
            # on déclenche une décision mock pour ne pas renvoyer une liste vide
            mock = generate_mock_ohlcv(LIVE_STATE["symbol"], LIVE_STATE["tf"], limit=200)
            candles = mock.get("candles", [])
            equity = 10_000.0  # equity simulée pour initialiser le moteur
            evaluate_and_maybe_trade(
                symbol=LIVE_STATE["symbol"],
                timeframe=LIVE_STATE["tf"],
                candles=candles,
                equity=equity,
            )
            decisions = get_recent_decisions(limit=limit)
        return {"decisions": decisions}
    except Exception as e:  # pragma: no cover
        logger.exception("Error in /api/decisions")
        return {"decisions": [], "error": str(e)}


@app.get("/api/orders")
def orders(
    limit: int = Query(200, ge=1, le=1000),
) -> Dict[str, Any]:
    """
    Renvoie les derniers ordres.
    """
    try:
        orders = get_recent_orders(limit=limit)
        return {"orders": orders}
    except Exception as e:  # pragma: no cover
        logger.exception("Error in /api/orders")
        return {"orders": [], "error": str(e)}


@app.get("/api/orders/range")
def orders_range(
    date_from: str = Query(..., alias="from"),
    date_to: str = Query(..., alias="to"),
) -> Dict[str, Any]:
    """
    Endpoint placeholder : pour l'instant retourne juste tous les
    ordres, le filtrage par date pourra être implémenté plus tard.
    """
    try:
        orders = get_recent_orders(limit=1000)
        return {"orders": orders, "from": date_from, "to": date_to}
    except Exception as e:  # pragma: no cover
        logger.exception("Error in /api/orders/range")
        return {"orders": [], "error": str(e)}


@app.get("/api/pnl")
def pnl_stats(
    period: str = Query("all"),
) -> Dict[str, Any]:
    """
    Retourne les stats de PNL agrégées à partir des ordres en mémoire.

    `period` est prévu pour évoluer (day|week|month|all), mais pour l'instant
    il sert surtout à filtrer côté front.
    """
    try:
        stats = get_pnl_stats()
        return {
            "period": period,
            **stats,
        }
    except Exception as e:  # pragma: no cover
        logger.exception("Error in /api/pnl")
        return {
            "period": period,
            "total": 0.0,
            "by_date": [],
            "fees": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
            "avg_rr": 0.0,
            "error": str(e),
        }
