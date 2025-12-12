# app/api/routes_status.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter

router = APIRouter(prefix="/status", tags=["status"])

LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
ORDERS_FILE = LOG_DIR / "orders.json"
DECISIONS_FILE = LOG_DIR / "decisions.json"


def _read_json_safe(path: Path) -> list[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


@router.get("")
async def status() -> Dict[str, Any]:
    orders = _read_json_safe(ORDERS_FILE)
    decisions = _read_json_safe(DECISIONS_FILE)

    return {
        "orders_count": len(orders),
        "decisions_count": len(decisions),
        "last_order": orders[-1] if orders else None,
        "last_decision": decisions[-1] if decisions else None,
    }
