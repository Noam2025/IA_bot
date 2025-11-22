# app/services/binance_rest.py
# -*- coding: utf-8 -*-
import time, hmac, hashlib, httpx
from typing import Dict, Any, List
from ..core.config import CFG

BASE_URL = "https://testnet.binancefuture.com" if CFG.TESTNET else "https://fapi.binance.com"
API_KEY = CFG.BINANCE_API_KEY or ""
API_SECRET = (CFG.BINANCE_API_SECRET or "").encode()
RECV_WINDOW = "5000"
_TIME_OFFSET_MS = 0

def _ts_ms() -> int:
    return int(time.time() * 1000) + _TIME_OFFSET_MS

async def _sync_time():
    global _TIME_OFFSET_MS
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{BASE_URL}/fapi/v1/time")
        srv = r.json()["serverTime"]
    _TIME_OFFSET_MS = int(srv) - int(time.time() * 1000)

def _sign(params: Dict[str, Any]) -> str:
    q = "&".join([f"{k}={params[k]}" for k in sorted(params.keys()) if params[k] is not None])
    return hmac.new(API_SECRET, q.encode(), hashlib.sha256).hexdigest()

async def rest(method: str, path: str, params: Dict[str, Any] = None, signed: bool = False):
    params = params or {}
    headers = {"X-MBX-APIKEY": API_KEY} if API_KEY else {}
    if signed:
        params.update({"timestamp": _ts_ms(), "recvWindow": RECV_WINDOW})
        params["signature"] = _sign(params)

    async with httpx.AsyncClient(timeout=15) as c:
        if method == "GET":
            r = await c.get(f"{BASE_URL}{path}", params=params, headers=headers)
        else:
            raise ValueError("Only GET used here")
    if r.status_code >= 400:
        raise RuntimeError(f"REST {path} {r.status_code}: {r.text}")
    try:
        return r.json()
    except Exception:
        return {"raw": r.text}

async def get_income_pnl(start_ms: int, end_ms: int) -> List[Dict[str, Any]]:
    """REALIZED_PNL rows within range."""
    await _sync_time()
    params = {
        "incomeType": "REALIZED_PNL",
        "startTime": start_ms,
        "endTime": end_ms,
        "limit": 1000,
    }
    data = await rest("GET", "/fapi/v1/income", params=params, signed=True)
    # rows: [{symbol, incomeType, income, time, ...}]
    return data
