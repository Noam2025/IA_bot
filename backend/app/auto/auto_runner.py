# auto_runner.py (compléter ta boucle)
from collections import defaultdict
backoff = defaultdict(int)        # secondes
last_trade_at = defaultdict(float)

async def decision_loop(state: GlobalState):
    while True:
        await asyncio.sleep(1.5)
        now = time.time()
        for s, st in state.symbols.items():
            if not st.klines:
                continue

            # backoff par symbole
            if backoff[s] > 0:
                backoff[s] -= 1
                continue

            try:
                # balance configurable
                balance = getattr(CFG, "BALANCE_USDT", 1000.0)
                res = await evaluate_and_maybe_trade(state, st, balance_usdt=balance)

                # cooldown si un ordre vient d’être exécuté
                if res.get("order"):
                    last_trade_at[s] = now

                # option: impose un cooldown 90s
                if now - last_trade_at.get(s, 0) < getattr(CFG, "COOLDOWN_SEC", 90):
                    pass  # la logique de sizing/execution peut vérifier aussi

            except Exception as e:
                print(f"[ERROR] decision {s}: {e}")
                backoff[s] = min(60, max(5, backoff[s]*2 or 5))  # 5→10→20→40→60
