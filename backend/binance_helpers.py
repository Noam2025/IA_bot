def format_price_qty(client, symbol, qty):
    info = client.futures_exchange_info()
    symbol_info = next(s for s in info["symbols"] if s["symbol"] == symbol)
    lot_filter = next(f for f in symbol_info["filters"] if f["filterType"] == "LOT_SIZE")
    step_size = float(lot_filter["stepSize"])
    qty = (qty // step_size) * step_size
    return float(qty)

def place_tp_sl_orders(client, symbol, side, risk, qty):
    opposite = "SELL" if side == "BUY" else "BUY"
    for tp in risk["take_profits"]:
        client.futures_create_order(
            symbol=symbol,
            side=opposite,
            type="TAKE_PROFIT_MARKET",
            stopPrice=tp["price"],
            closePosition=True,
            reduceOnly=True
        )
    client.futures_create_order(
        symbol=symbol,
        side=opposite,
        type="STOP_MARKET",
        stopPrice=risk["stop_loss"],
        closePosition=True
    )
