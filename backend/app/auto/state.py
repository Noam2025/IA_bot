import time
from collections import deque, defaultdict

class SymbolState:
    def __init__(self, symbol: str, max_len=600):
        self.symbol = symbol
        self.trades = deque(maxlen=max_len)      # ticks/aggTrades
        self.klines = deque(maxlen=max_len)      # (t_open, open, high, low, close, volume)
        self.last_decision_ts = 0.0
        self.open_positions = 0
        self.daily_pnl = 0.0
        self.cooldown_until = 0.0

class GlobalState:
    def __init__(self, symbols):
        self.symbols = {s: SymbolState(s) for s in symbols}
        self.last_trade_times = deque(maxlen=60)
        self.embargo_active = False
        self.embargo_reason = ""
        self.meta = defaultdict(dict)  # pour stocker des indicateurs calculés
