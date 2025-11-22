import time, math
import numpy as np

def ema(series: np.ndarray, period: int):
    if series.size < period: return None
    alpha = 2/(period+1)
    ema_val = series[0]
    for x in series[1:]:
        ema_val = alpha*x + (1-alpha)*ema_val
    return ema_val

def rsi(closes: np.ndarray, period=14):
    if closes.size < period+1: return None
    diff = np.diff(closes)
    up = np.where(diff>0, diff, 0.0)
    dn = np.where(diff<0, -diff, 0.0)
    rs = (up[-period:].mean() + 1e-9) / (dn[-period:].mean() + 1e-9)
    return 100 - 100/(1+rs)

def atr(ohlc: np.ndarray, period=14):
    # ohlc: [[o,h,l,c], ...]
    if ohlc.shape[0] < period+1: return None
    tr_list = []
    prev_close = ohlc[-period-1,3]
    for row in ohlc[-period:]:
        o,h,l,c = row
        tr = max(h-l, abs(h-prev_close), abs(l-prev_close))
        tr_list.append(tr); prev_close = c
    return np.mean(tr_list)

def pre_signal_from_state(st) -> dict:
    """Retourne un score de setup + direction; n'appelle pas l'IA ici."""
    if len(st.klines) < 60: 
        return {"score":0.0,"bias":"NONE","info":"warmup"}

    closes = np.array([k[4] for k in st.klines], dtype=float)
    ohlc = np.array([[k[1],k[2],k[3],k[4]] for k in st.klines], dtype=float)

    ema8  = ema(closes[-50:], 8)
    ema21 = ema(closes[-100:],21)
    rsi14 = rsi(closes,14)
    atr14 = atr(ohlc,14)
    last = closes[-1]

    bias = "NONE"
    score = 0.0
    info = {}

    if ema8 and ema21 and rsi14 and atr14:
        # Simple logique: croisement + RSI hors neutre + mouvement relatif à l’ATR
        trend_up   = ema8 > ema21 and rsi14 > 55
        trend_down = ema8 < ema21 and rsi14 < 45
        rng = atr14 / last
        momentum = abs((closes[-1]-closes[-5]) / last)
        strong = momentum > 0.0008 and rng > 0.001

        if trend_up and strong:
            bias, score = "LONG", min(1.0, 0.5 + momentum*500)
        elif trend_down and strong:
            bias, score = "SHORT", min(1.0, 0.5 + momentum*500)

        info = {"ema8":ema8,"ema21":ema21,"rsi":rsi14,"atrp":rng,"mom":momentum}

    return {"score":float(score), "bias":bias, "info":info}
