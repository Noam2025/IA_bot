# business/IA_bot/backend/app/auto/order_exec.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import os, time, hmac, hashlib
from typing import Dict, Any
import httpx

BINANCE_FUTURES_URL = os.getenv("BINANCE_FUTURES_URL") or "https://fapi.binance.com"
API_KEY = os.getenv("BINANCE_API_KEY", "")
API_SECRET = os.getenv("BINANCE_API_SECRET", "")

def _ts() -> int:
    return int(time.time() * 1000)

def _sign(params: Dict[str, Any]) -> str:
    q = "&".join(f"{k}={params[k]}" for k in sorted(params))
    return hmac.new(API_SECRET.encode(), q.encode(), hashlib.sha256).hexdigest()

def _headers() -> Dict[str, str]:
    return {"X-MBX-APIKEY": API_KEY}

async def _post(client: httpx.AsyncClient, path: str, params: Dict[str, Any], signed: bool = True) -> Dict[str, Any]:
    p = dict(params)
    if signed:
        p["timestamp"] = _ts()
        p["recvWindow"] = p.get("recvWindow", 5000)
        p["signature"] = _sign(p)
    r = await client.post(f"{BINANCE_FUTURES_URL}{path}", params=p, headers=_headers(), timeout=30)
    r.raise_for_status()
    return r.json()

async def set_leverage_and_mode(symbol: str, leverage: int = 5) -> None:
    async with httpx.AsyncClient() as client:
        # One-way mode
        await _post(client, "/fapi/v1/positionSide/dual", {"dualSidePosition": "false"})
        # Set leverage
        await _post(client, "/fapi/v1/leverage", {"symbol": symbol, "leverage": leverage})

async def market_open(symbol: str, side: str, quantity: float, leverage: int = 5) -> Dict[str, Any]:
    params = {"symbol": symbol, "side": side.upper(), "type": "MARKET", "quantity": quantity}
    async with httpx.AsyncClient() as client:
        await set_leverage_and_mode(symbol, leverage=leverage)
        data = await _post(client, "/fapi/v1/order", params)
    return {
        "ok": True,
        "action": "OPEN",
        "symbol": symbol,
        "side": side.upper(),
        "order": data,
        "price": float(data.get("avgPrice") or 0),
        "qty": float(data.get("origQty") or 0),
        "orderId": data.get("orderId"),
        "ts": time.time(),
    }

async def attach_tp_sl(symbol: str, side: str, take_profit: float, stop_loss: float, quantity: float) -> Dict[str, Any]:
    close_side = "SELL" if side.upper() == "BUY" else "BUY"
    async with httpx.AsyncClient() as client:
        tp = await _post(client, "/fapi/v1/order", {
            "symbol": symbol,
            "side": close_side,
            "type": "TAKE_PROFIT_MARKET",
            "stopPrice": f"{take_profit}",
            "closePosition": "true",
            "reduceOnly": "true",
        })
        sl = await _post(client, "/fapi/v1/order", {
            "symbol": symbol,
            "side": close_side,
            "type": "STOP_MARKET",
            "stopPrice": f"{stop_loss}",
            "closePosition": "true",
            "reduceOnly": "true",
        })
    return {"ok": True, "tp": tp, "sl": sl, "ts": time.time()}

async def market_close(symbol: str, side: str, quantity: float) -> Dict[str, Any]:
    close_side = "SELL" if side.upper() == "BUY" else "BUY"
    async with httpx.AsyncClient() as client:
        data = await _post(client, "/fapi/v1/order", {
            "symbol": symbol,
            "side": close_side,
            "type": "MARKET",
            "quantity": quantity,
            "reduceOnly": "true",
        })
    return {"ok": True, "action": "CLOSE", "symbol": symbol, "order": data, "ts": time.time()}

# Facultatif : petit wrapper unifié
async def place_order(symbol: str, side: str, qty: float, price: float | None = None) -> Dict[str, Any]:
    if price is None:
        return await market_open(symbol, "BUY" if side.upper()=="LONG" else "SELL", qty)
    raise NotImplementedError("place_limit pas encore implémenté")
