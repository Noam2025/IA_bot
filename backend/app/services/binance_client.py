# app/services/binance_client.py
# -*- coding: utf-8 -*-
"""
Binance Futures (USDⓈ-M) market streams via WebSocket.
- Testnet host:  wss://stream.binancefuture.com
- Prod host:     wss://fstream.binance.com
We multiplex multiple streams with the /stream?streams=... endpoint.

Yields parsed JSON messages:
  {"stream": "<symbol>@aggTrade" | "<symbol>@kline_<interval>", "data": {...}}

Dependencies: websockets, asyncio
"""

import asyncio
import json
import logging
import random
from typing import AsyncIterator, Dict, Iterable, List

import websockets

try:
    # Optionnel : lire la conf globale si dispo
    from ..core.config import CFG
    DEFAULT_INTERVAL = getattr(CFG, "KLINE_INTERVAL", "1m")
except Exception:
    DEFAULT_INTERVAL = "1m"

log = logging.getLogger("binance_ws")
if not log.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# ————————————————————————————————————————————————————————————————
# Helpers
# ————————————————————————————————————————————————————————————————

_ALLOWED_KLINES = {"1m","3m","5m","15m","30m","1h","2h","4h","6h","8h","12h","1d","3d","1w","1M"}

def _normalize_interval(iv: str) -> str:
    iv = (iv or "1m").strip()
    return iv if iv in _ALLOWED_KLINES else "1m"

def _host_for(testnet: bool) -> str:
    """
    Correct USDⓈ-M Futures market stream hosts.
    testnet=True  -> wss://stream.binancefuture.com
    testnet=False -> wss://fstream.binance.com
    """
    return "wss://stream.binancefuture.com" if testnet else "wss://fstream.binance.com"

def _build_streams(symbols: Iterable[str], kline_interval: str, use_aggtrade: bool) -> List[str]:
    streams: List[str] = []
    for s in symbols:
        s_low = s.lower()
        if use_aggtrade:
            streams.append(f"{s_low}@aggTrade")
        streams.append(f"{s_low}@kline_{kline_interval}")
    return streams

def _build_url(symbols: Iterable[str], testnet: bool, kline_interval: str, use_aggtrade: bool) -> str:
    host = _host_for(testnet)
    streams = _build_streams(symbols, kline_interval, use_aggtrade)
    return f"{host}/stream?streams={'/'.join(streams)}"


# ————————————————————————————————————————————————————————————————
# Public Client
# ————————————————————————————————————————————————————————————————

class BinanceWs:
    """
    Simple WS client with auto-reconnect.
    Usage:
        ws = BinanceWs(["BTCUSDT","ETHUSDT"], testnet=True, kline_interval="1m")
        async for msg in ws.stream():
            print(msg["stream"], msg["data"])
    """
    def __init__(
        self,
        symbols: Iterable[str],
        testnet: bool = True,
        kline_interval: str = None,
        use_aggtrade: bool = True,
        ping_interval: int = 20,
        ping_timeout: int = 20,
    ):
        self.symbols = [s.upper().strip() for s in symbols if s and s.strip()]
        self.testnet = testnet
        self.kline_interval = _normalize_interval(kline_interval or DEFAULT_INTERVAL)
        self.use_aggtrade = use_aggtrade
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout

        self.url = _build_url(self.symbols, self.testnet, self.kline_interval, self.use_aggtrade)
        log.info(f"[BinanceWs] URL: {self.url}")

    async def stream(self) -> AsyncIterator[Dict]:
        """
        Async generator. Reconnects with exponential backoff on errors.
        """
        backoff = 1.0
        while True:
            try:
                async with websockets.connect(
                    self.url,
                    ping_interval=self.ping_interval,
                    ping_timeout=self.ping_timeout,
                    close_timeout=5,
                    max_size=None,
                ) as ws:
                    log.info("[BinanceWs] Connected.")
                    backoff = 1.0  # reset after successful connect
                    while True:
                        raw = await ws.recv()
                        try:
                            msg = json.loads(raw)
                        except Exception:
                            log.warning("[BinanceWs] JSON parse error, skipping frame.")
                            continue
                        # Provide a consistent shape
                        if "data" in msg and "stream" in msg:
                            yield msg
                        else:
                            # Some control frames may appear; forward anyway
                            yield msg
            except (websockets.ConnectionClosed, websockets.InvalidStatusCode) as e:
                log.warning(f"[BinanceWs] Connection closed: {e}. Reconnecting...")
            except Exception as e:
                log.error(f"[BinanceWs] Error: {e}. Reconnecting...")

            # Exponential backoff with jitter (max ~30s)
            sleep_s = min(30.0, backoff * (1.5 + random.random()))
            await asyncio.sleep(sleep_s)
            backoff = min(30.0, backoff * 2)

    # Optional: allow refreshing the URL if config changes at runtime
    def refresh(self, *, symbols: Iterable[str] = None, kline_interval: str = None, use_aggtrade: bool = None):
        if symbols is not None:
            self.symbols = [s.upper().strip() for s in symbols if s and s.strip()]
        if kline_interval is not None:
            self.kline_interval = _normalize_interval(kline_interval)
        if use_aggtrade is not None:
            self.use_aggtrade = bool(use_aggtrade)
        self.url = _build_url(self.symbols, self.testnet, self.kline_interval, self.use_aggtrade)
        log.info(f"[BinanceWs] URL refreshed: {self.url}")
