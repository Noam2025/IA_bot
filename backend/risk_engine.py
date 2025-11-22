def check_risk_limits(risk: dict):
    max_daily_loss = 3.0
    risk_per_trade = risk.get("risk_per_trade_pct", 1.0)
    return risk_per_trade <= max_daily_loss

def compute_position_size(quantity_usdt: float, price: float):
    return round(quantity_usdt / price, 6)
