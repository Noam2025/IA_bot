import os
from dotenv import load_dotenv
load_dotenv()

def _bool(v: str, default=False):
    if v is None: return default
    return v.lower() in ("1","true","yes","on")

class CFG:
    BINANCE_API_KEY = os.getenv("BINANCE_API_KEY","")
    BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET","")
    TESTNET = _bool(os.getenv("BINANCE_FUTURES_TESTNET","true"))
    SYMBOLS = [s.strip().upper() for s in os.getenv("SYMBOLS","BTCUSDT").split(",") if s.strip()]
    KLINE_INTERVAL = os.getenv("KLINE_INTERVAL","1m")

    AUTO_MODE = _bool(os.getenv("AUTO_MODE","false"))
    RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE","0.002"))
    MAX_POSITIONS = int(os.getenv("MAX_POSITIONS","1"))
    DAILY_LOSS_CAP = float(os.getenv("DAILY_LOSS_CAP","0.03"))
    EMBARGO_NEWS_MIN = int(os.getenv("EMBARGO_NEWS_MIN","30"))
    COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS","15"))
    MAX_TRADES_PER_MIN = int(os.getenv("MAX_TRADES_PER_MIN","6"))

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY","")
    LLM_MODEL = os.getenv("LLM_MODEL","gpt-4o-mini")
    LLM_MIN_SIGNAL_SCORE = float(os.getenv("LLM_MIN_SIGNAL_SCORE","0.75"))
