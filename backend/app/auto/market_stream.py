import time
from typing import Dict, Any
from .state import GlobalState
from ..services.binance_client import BinanceWs

async def run_market_stream(state: GlobalState, testnet: bool):
    ws = BinanceWs(list(state.symbols.keys()), testnet=testnet)
    async for msg in ws.stream():
        data = msg.get("data", {})
        stream = msg.get("stream","")
        if "@aggTrade" in stream:
            s = stream.split("@")[0].upper()
            price = float(data["p"]); qty = float(data["q"]); ts = data["T"]/1000
            st = state.symbols[s]
            st.trades.append((ts, price, qty))
        elif "@kline_" in stream:
            s = stream.split("@")[0].upper()
            k = data["k"]
            if k["x"] is False:  # kline en formation, on peut mettre à jour le dernier
                pass
            ts = k["t"]/1000
            o,h,l,c,v = map(float, (k["o"],k["h"],k["l"],k["c"],k["v"]))
            st = state.symbols[s]
            st.klines.append((ts,o,h,l,c,v))
