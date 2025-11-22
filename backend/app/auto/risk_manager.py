import time
from ..core.config import CFG

def embargo_active(state) -> (bool, str):
    if state.embargo_active:
        return True, state.embargo_reason or "embargo"
    return False, ""

def cooldown_ok(st, now) -> bool:
    return now >= st.cooldown_until

def hit_daily_cap(state) -> bool:
    return state.symbols[next(iter(state.symbols))].daily_pnl <= -CFG.DAILY_LOSS_CAP

def can_open_position(state, st, now) -> (bool, str):
    if hit_daily_cap(state):
        return False, "daily loss cap"
    if st.open_positions >= CFG.MAX_POSITIONS:
        return False, "max positions reached"
    return True, ""
