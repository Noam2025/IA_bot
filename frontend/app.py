# -*- coding: utf-8 -*-
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
import streamlit as st

# Optionnel mais conseillé pour un rendu pro
try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

# ============================================================
#                   CONFIG GÉNÉRALE STREAMLIT
# ============================================================

st.set_page_config(
    page_title="IA Trading – Dashboard",
    page_icon="🤖",
    layout="wide",
)

st.markdown(
    "<h1 style='margin-bottom:0'>🤖 IA Trading – Dashboard analytique</h1>",
    unsafe_allow_html=True,
)
st.caption("Vue type CryptoQuant / Glassnode : marché, décisions IA, ordres, PNL.")

# ============================================================
#                   CONFIG BACKEND / API
# ============================================================

API_BASE: str = "http://127.0.0.1:8000"


def ep(path: str) -> str:
    """Construit l'URL complète vers le backend."""
    return f"{API_BASE.rstrip('/')}/{path.lstrip('/')}"


def get_json(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    method: str = "GET",
    timeout: int = 10,
    json: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[Any], Optional[str]]:
    """
    Appel HTTP robuste qui renvoie (data, error).
    error = None si tout va bien.
    """
    try:
        method = method.upper()
        if method == "GET":
            r = requests.get(url, params=params, timeout=timeout)
        elif method == "POST":
            r = requests.post(url, params=params, json=json, timeout=timeout)
        else:
            return None, f"Méthode HTTP non supportée: {method}"

        if not r.ok:
            return None, f"HTTP {r.status_code}: {r.text}"

        return r.json(), None
    except Exception as e:
        return None, str(e)


# ============================================================
#                   PARAMÈTRES GLOBAUX – SIDEBAR
# ============================================================

default_symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
default_tfs = ["1m", "5m", "15m", "1h"]

with st.sidebar:
    st.header("Paramètres globaux")

    symbol = st.selectbox("Symbole", default_symbols, index=0)
    tf = st.selectbox("Timeframe", default_tfs, index=1)
    live_limit = st.slider("Nb. de bougies (live)", 50, 1000, 200, 50)

    st.markdown("---")
    auto_refresh = st.checkbox("Auto-refresh Live (10s)", value=False)
    st.caption("Active uniquement sur l’onglet Market Analytics.")

# ============================================================
#                   TABS
# ============================================================

tabs = st.tabs(
    [
        "Statut & Contrôle",
        "Market Analytics",
        "Décisions IA",
        "Ordres",
        "PNL & Stats",
    ]
)

# ============================================================
#                   TAB 1 – STATUT & CONTRÔLE
# ============================================================
with tabs[0]:
    st.subheader("Statut backend & contrôle auto-trading")

    col_status, col_auto = st.columns([1, 1])

    # Statut backend
    with col_status:
        st.markdown("### Statut backend")

        status_data, status_err = get_json(ep("/api/status"))
        if status_err:
            st.error(f"Erreur de connexion au backend: {status_err}")
        else:
            st.success("Backend en ligne ✅")
            st.json(status_data)

    # Contrôle live/auto
    with col_auto:
        st.markdown("### Contrôle du moteur auto / live")

        # Statut live
        live_status, live_err = get_json(ep("/api/live/status"))
        if live_err:
            st.warning(f"Impossible de récupérer /api/live/status : {live_err}")
        else:
            st.write("Statut live courant :")
            st.json(live_status)

        st.markdown("---")

        col_start, col_stop = st.columns(2)
        with col_start:
            if st.button("Démarrer le live / auto-trading", type="primary"):
                payload = {
                    "symbol": symbol,
                    "timeframe": tf,
                    "limit": live_limit,
                }
                resp, err = get_json(
                    ep("/api/live/start"), method="POST", json=payload, timeout=5
                )
                if err:
                    st.error(f"Erreur /api/live/start : {err}")
                else:
                    st.success("Live / auto-trading démarré.")
                    st.json(resp)

        with col_stop:
            if st.button("Arrêter le live / auto-trading"):
                resp, err = get_json(ep("/api/live/stop"), method="POST", timeout=5)
                if err:
                    st.error(f"Erreur /api/live/stop : {err}")
                else:
                    st.warning("Live / auto-trading arrêté.")
                    st.json(resp)

# ============================================================
#                   TAB 2 – MARKET ANALYTICS
# ============================================================
with tabs[1]:
    st.subheader("Market analytics temps réel")

    st.markdown(
        f"**Symbole :** `{symbol}` – **Timeframe :** `{tf}` – **Bougies :** {live_limit}"
    )

    # Auto-refresh (uniquement visuel, ne stoppe pas le backend)
    if auto_refresh:
        # 10 secondes de délai entre refresh
        st_autorefresh = st.empty()
        # On met un compteur mais sans l'exploiter, juste pour forcer le refresh
        st_autorefresh.write(
            f"Dernier rafraîchissement: {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC"
        )
        time.sleep(0.1)

    # Récupération candles + indicateurs depuis /api/live
    params = {"symbol": symbol, "tf": tf, "limit": live_limit}
    candles, live_err = get_json(ep("/api/live"), params=params)

    if live_err:
        st.error(f"Erreur /api/live : {live_err}")
    else:
        if not isinstance(candles, list) or len(candles) == 0:
            st.info("Aucune donnée de marché renvoyée pour l’instant.")
        else:
            df = pd.DataFrame(candles)

            # Normalisation colonnes possibles
            rename_map = {}
            if "open_time" in df.columns and "ts" not in df.columns:
                rename_map["open_time"] = "ts"
            if "Open" in df.columns and "open" not in df.columns:
                rename_map["Open"] = "open"
            if "High" in df.columns and "high" not in df.columns:
                rename_map["High"] = "high"
            if "Low" in df.columns and "low" not in df.columns:
                rename_map["Low"] = "low"
            if "Close" in df.columns and "close" not in df.columns:
                rename_map["Close"] = "close"
            if rename_map:
                df = df.rename(columns=rename_map)

            # Conversion temps
            if "ts" in df.columns:
                try:
                    ts_col = df["ts"]
                    if pd.api.types.is_numeric_dtype(ts_col):
                        non_na = ts_col.dropna()
                        if not non_na.empty:
                            sample = float(non_na.iloc[0])
                            if sample > 1e12:
                                df["ts"] = pd.to_datetime(ts_col, unit="ms")
                            else:
                                df["ts"] = pd.to_datetime(ts_col, unit="s")
                    else:
                        df["ts"] = pd.to_datetime(df["ts"])
                except Exception:
                    pass

            df = df.sort_values("ts")

            # Affichage de la table brute
            with st.expander("Voir les données brutes"):
                st.dataframe(df, height=300)

            # Graphique principal : prix + éventuellement indicateurs
            if HAS_PLOTLY:
                # Détection des colonnes possibles pour les indicateurs
                price_col = "close" if "close" in df.columns else None
                volume_col = "volume" if "volume" in df.columns else None

                has_rsi_panel = "rsi" in df.columns
                has_macd_panel = "macd" in df.columns

                nrows = 1
                if volume_col is not None:
                    nrows += 1
                if has_rsi_panel or has_macd_panel:
                    nrows += 1

                row_idx_price = 1
                row_idx_volume = 2 if volume_col is not None else None
                row_idx_rsi_macd = nrows if nrows > (row_idx_volume or 1) else None

                shared_x = True

                titles = ["Prix"]
                if volume_col is not None:
                    titles.append("Volume")
                if has_rsi_panel or has_macd_panel:
                    titles.append("RSI / MACD")

                fig = make_subplots(
                    rows=nrows,
                    cols=1,
                    shared_xaxes=shared_x,
                    vertical_spacing=0.03,
                    subplot_titles=titles,
                    row_heights=[
                        0.6 if nrows >= 2 else 1.0,
                        0.2 if nrows >= 3 else 0.4,
                        0.2 if nrows == 3 else 0.0,
                    ][:nrows],
                )

                # Prix : chandeliers ou lignes
                if price_col is not None:
                    if {"open", "high", "low", "close"}.issubset(df.columns):
                        fig.add_trace(
                            go.Candlestick(
                                x=df["ts"],
                                open=df["open"],
                                high=df["high"],
                                low=df["low"],
                                close=df["close"],
                                name="OHLC",
                            ),
                            row=row_idx_price,
                            col=1,
                        )
                    else:
                        fig.add_trace(
                            go.Scatter(
                                x=df["ts"],
                                y=df[price_col],
                                mode="lines",
                                name="Prix",
                            ),
                            row=row_idx_price,
                            col=1,
                        )

                    # EMA éventuelles
                    ema_cols = [c for c in df.columns if c.lower().startswith("ema")]
                    for ema_col in ema_cols:
                        fig.add_trace(
                            go.Scatter(
                                x=df["ts"],
                                y=df[ema_col],
                                mode="lines",
                                name=ema_col,
                            ),
                            row=row_idx_price,
                            col=1,
                        )

                # Volume
                if volume_col is not None:
                    fig.add_trace(
                        go.Bar(
                            x=df["ts"],
                            y=df["volume"],
                            name="Volume",
                        ),
                        row=row_idx_volume,
                        col=1,
                    )

                # RSI / MACD
                if row_idx_rsi_macd is not None:
                    if "rsi" in df.columns:
                        fig.add_trace(
                            go.Scatter(
                                x=df["ts"],
                                y=df["rsi"],
                                mode="lines",
                                name="RSI",
                            ),
                            row=row_idx_rsi_macd,
                            col=1,
                        )
                    if "macd" in df.columns:
                        fig.add_trace(
                            go.Scatter(
                                x=df["ts"],
                                y=df["macd"],
                                mode="lines",
                                name="MACD",
                            ),
                            row=row_idx_rsi_macd,
                            col=1,
                        )

                fig.update_layout(
                    height=700,
                    margin=dict(l=20, r=20, t=40, b=40),
                    xaxis_rangeslider_visible=False,
                    legend=dict(orientation="h"),
                    showlegend=True,
                )

                st.plotly_chart(fig, use_container_width=True)
            else:
                st.line_chart(
                    df.set_index("ts")["close"] if "close" in df.columns else df["ts"]
                )

# ============================================================
#                   TAB 3 – DÉCISIONS IA
# ============================================================
with tabs[2]:
    st.subheader("Décisions IA récentes")

    params = {"limit": 200}
    decisions, dec_err = get_json(ep("/api/decisions"), params=params)

    if dec_err:
        st.error(f"Erreur /api/decisions : {dec_err}")
    else:
        if not isinstance(decisions, list) or len(decisions) == 0:
            st.info("Aucune décision IA enregistrée.")
        else:
            df_dec = pd.DataFrame(decisions)

            # Normalisation
            if "ts" in df_dec.columns:
                try:
                    ts_col = df_dec["ts"]
                    if pd.api.types.is_numeric_dtype(ts_col):
                        non_na = ts_col.dropna()
                        if not non_na.empty:
                            sample = float(non_na.iloc[0])
                            if sample > 1e12:
                                df_dec["ts"] = pd.to_datetime(ts_col, unit="ms")
                            else:
                                df_dec["ts"] = pd.to_datetime(ts_col, unit="s")
                    else:
                        df_dec["ts"] = pd.to_datetime(df_dec["ts"])
                except Exception:
                    pass

            df_dec = df_dec.sort_values("ts", ascending=False)

            with st.expander("Tableau brut des décisions IA"):
                st.dataframe(df_dec, height=300)

            # Quelques stats rapides
            st.markdown("### Statistiques rapides")

            total_decisions = len(df_dec)
            by_side = df_dec["side"].value_counts(dropna=False).to_dict(
            ) if "side" in df_dec.columns else {}
            by_reason = df_dec["reason"].value_counts(dropna=False).to_dict(
            ) if "reason" in df_dec.columns else {}

            c1, c2 = st.columns(2)
            with c1:
                st.metric("Nombre total de décisions", total_decisions)
                if by_side:
                    st.write("Par côté (long/short/flat) :")
                    st.json(by_side)

            with c2:
                if by_reason:
                    st.write("Par raison / motif :")
                    st.json(by_reason)

# ============================================================
#                   TAB 4 – ORDRES
# ============================================================
with tabs[3]:
    st.subheader("Ordres exécutés")

    params = {"limit": 500}
    orders, ord_err = get_json(ep("/api/orders"), params=params)

    if ord_err:
        st.error(f"Erreur /api/orders : {ord_err}")
    else:
        if not isinstance(orders, list) or len(orders) == 0:
            st.info("Aucun ordre enregistré.")
        else:
            df_ord = pd.DataFrame(orders)

            # Normalisation colonnes temporelles
            for col_time in ["created_at", "closed_at", "ts"]:
                if col_time in df_ord.columns:
                    try:
                        df_ord[col_time] = pd.to_datetime(df_ord[col_time])
                    except Exception:
                        pass

            df_ord = df_ord.sort_values(
                "created_at" if "created_at" in df_ord.columns else df_ord.index,
                ascending=False,
            )

            with st.expander("Tableau brut des ordres"):
                st.dataframe(df_ord, height=300)

            # Stats rapides
            st.markdown("### Statistiques ordres")

            if "pnl" in df_ord.columns:
                total_pnl = df_ord["pnl"].sum()
                win_trades = (df_ord["pnl"] > 0).sum()
                loss_trades = (df_ord["pnl"] <= 0).sum()
                nb_trades = len(df_ord)
                win_rate = (win_trades / nb_trades * 100) if nb_trades > 0 else 0.0

                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    st.metric("PNL total (brut)", f"{total_pnl:.4f}")
                with c2:
                    st.metric("Nombre de trades", nb_trades)
                with c3:
                    st.metric("Trades gagnants", win_trades)
                with c4:
                    st.metric("Win rate (%)", f"{win_rate:.1f}")
            else:
                st.info("La colonne 'pnl' n'est pas présente dans les ordres renvoyés.")

# ============================================================
#                   TAB 5 – PNL & STATS GLOBAL
# ============================================================
with tabs[4]:
    st.subheader("PNL global & statistiques")

    period = st.selectbox("Période", ["day", "week", "month", "all"], index=1)

    params = {"period": period} if period != "all" else {}

    pnl_data, pnl_err = get_json(ep("/api/pnl"), params=params)

    if pnl_err:
        st.error(f"Erreur /api/pnl : {pnl_err}")
    else:
        if not isinstance(pnl_data, dict) or not pnl_data:
            st.info("Aucune donnée PNL disponible.")
        else:
            # Récupération robuste des champs renvoyés par le backend
            # Backend actuel : "total", "win_rate", "max_drawdown", "equity_curve", ...
            pnl_total = pnl_data.get("total")
            if pnl_total is None:
                pnl_total = pnl_data.get("pnl_total")

            nb_trades = pnl_data.get("nb_trades")

            win_rate = pnl_data.get("win_rate")
            dd_max = pnl_data.get("max_drawdown")

            col1, col2, col3 = st.columns(3)
            with col1:
                if pnl_total is not None:
                    st.metric("PNL total", f"{pnl_total:.4f}")
            with col2:
                if win_rate is not None:
                    st.metric("Win rate (%)", f"{win_rate:.1f}")
            with col3:
                if dd_max is not None:
                    st.metric("Max Drawdown", f"{dd_max:.4f}")

            st.markdown("---")

            # Courbe PNL / equity_curve si dispo
            equity_curve = pnl_data.get("equity_curve") or pnl_data.get("pnl_points")
            if isinstance(equity_curve, list) and len(equity_curve) > 0:
                df_curve = pd.DataFrame(equity_curve)

                # Recherche colonne temps / valeur
                time_col = None
                for candidate in ["ts", "time", "datetime"]:
                    if candidate in df_curve.columns:
                        time_col = candidate
                        break

                value_col = None
                for candidate in ["pnl", "cum_pnl", "value", "equity"]:
                    if candidate in df_curve.columns:
                        value_col = candidate
                        break

                if time_col is not None and value_col is not None:
                    # Normalisation temps
                    try:
                        if pd.api.types.is_numeric_dtype(df_curve[time_col]):
                            non_na = df_curve[time_col].dropna()
                            if not non_na.empty:
                                sample = float(non_na.iloc[0])
                                if sample > 1e12:
                                    df_curve[time_col] = pd.to_datetime(
                                        df_curve[time_col], unit="ms"
                                    )
                                else:
                                    df_curve[time_col] = pd.to_datetime(
                                        df_curve[time_col], unit="s"
                                    )
                        else:
                            df_curve[time_col] = pd.to_datetime(
                                df_curve[time_col], errors="coerce"
                            )
                    except Exception:
                        pass
                    df_curve = df_curve.sort_values(time_col)

                    if HAS_PLOTLY:
                        fig_pnl = go.Figure()
                        fig_pnl.add_trace(
                            go.Scatter(
                                x=df_curve[time_col],
                                y=df_curve[value_col],
                                mode="lines",
                                name="Equity / PNL cumulé",
                            )
                        )
                        fig_pnl.update_layout(
                            margin=dict(l=0, r=0, t=20, b=0),
                            showlegend=False,
                        )
                        st.plotly_chart(fig_pnl, use_container_width=True)
                    else:
                        st.line_chart(
                            df_curve.set_index(time_col)[value_col],
                            height=350,
                        )

                    with st.expander("Détail des points de PNL"):
                        st.dataframe(df_curve, height=300)
                else:
                    st.caption(
                        "Le backend ne fournit pas de colonnes temps/valeur standard pour la courbe."
                    )
            else:
                st.info("Pas de courbe PNL détaillée renvoyée par l’API.")
