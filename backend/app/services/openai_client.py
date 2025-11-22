import httpx, os
from ..core.config import CFG

async def ask_llm(context: dict) -> dict:
    """Appelle l'IA seulement sur pré-signal fort pour valider/affiner."""
    if not CFG.OPENAI_API_KEY:
        return {"ai_ok": True, "reason":"LLM disabled (no key)"}
    payload = {
        "model": CFG.LLM_MODEL,
        "messages":[
            {"role":"system","content":"You are a trading risk-aware co-pilot. Respond with JSON."},
            {"role":"user","content":(
                "Given the technical snapshot (RSI/EMA/ATR/momentum) and risk limits, "
                "should we take a trade now? Reply JSON: {ai_ok: bool, reason: str}.\n"
                f"Snapshot: {context}"
            )}
        ]
    }
    headers={"Authorization":f"Bearer {CFG.OPENAI_API_KEY}"}
    # Remplace par l’endpoint OpenAI que tu utilises:
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers)
        j = r.json()
        try:
            txt = j["choices"][0]["message"]["content"]
        except Exception:
            return {"ai_ok": False, "reason":"LLM error"}
    # Très simple: on “parse” naïvement; à durcir si besoin
    ai_ok = "true" in txt.lower() or "\"ai_ok\": true" in txt.lower()
    return {"ai_ok": ai_ok, "reason": txt[:200]}
