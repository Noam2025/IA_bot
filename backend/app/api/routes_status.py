# app/api/routes_status.py
# -*- coding: utf-8 -*-
from fastapi import APIRouter, Query
from typing import Literal, Dict, Any, List
import time, datetime as dt

from ..core.config import CFG
from ..logs.logger import read_orders, read_decisions
from ..services.binance_rest import get_income_pnl

router = APIRouter()

@router.get("/status")
async def status():
    return {
        "ok": True,
        "auto_mode": CFG.AUTO_MODE,
        "symbols": CFG.SYMBOLS,
        "testnet": CFG.TESTNET,
        "ts": time.time()
    }

@router.get("/orders")
async def orders(limit: int = Query(200, ge=1, le=2000)):
    return {"orders": read_orders(limit), "count": min(limit, len(read_orders(limit)))}

@router.get("/decisions")
async def decisions(limit: int = Query(200, ge=1, le=2000)):
    return {"decisions": read_decisions(limit), "count": min(limit, len(read_decisions(limit)))}

def _floor_day_ms(ts: float) -> int:
    d = dt.datetime.utcfromtimestamp(ts).date()
    return int(dt.datetime(d.year, d.month, d.day).timestamp() * 1000)

def _range_ms(range_key: str) -> (int, int):
    now = int(time.time() * 1000)
    if range_key == "1w":
        start = now - 7*24*3600*1000
    elif range_key == "1m":
        start = now - 30*24*3600*1000
    elif range_key == "3m":
        start = now - 90*24*3600*1000
    else:  # "1d"
        start = now - 24*3600*1000
    return start, now

@router.get("/pnl")
async def pnl(range_key: Literal["1d","1w","1m","3m"]="1m"):
    start_ms, end_ms = _range_ms(range_key)
    rows = await get_income_pnl(start_ms, end_ms)
    # Agrégation
    by_day = {}
    total = 0.0
    for r in rows:
        ts = int(r["time"])/1000
        day = dt.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
        val = float(r.get("income", 0.0))
        total += val
        by_day[day] = by_day.get(day, 0.0) + val

    # semaine/mois
    by_week = {}
    by_month = {}
    for d, v in by_day.items():
        y, m, dd = map(int, d.split("-"))
        date_obj = dt.date(y, m, dd)
        year_week = f"{date_obj.isocalendar().year}-W{date_obj.isocalendar().week:02d}"
        year_month = f"{y}-{m:02d}"
        by_week[year_week] = by_week.get(year_week, 0.0) + v
        by_month[year_month] = by_month.get(year_month, 0.0) + v

    # Série triée pour le graphique (jour)
    series = sorted([{"date": d, "pnl": v} for d, v in by_day.items()], key=lambda x: x["date"])
    return {
        "range": range_key,
        "total": total,
        "by_day": by_day,
        "by_week": by_week,
        "by_month": by_month,
        "series": series
    }
