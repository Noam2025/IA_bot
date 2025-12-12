# app/logs/logger.py
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

LOG_DIR = Path(__file__).resolve().parent
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


def _append_json(path: Path, payload: Dict[str, Any]) -> None:
    data = []
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = []

    data.append(payload)

    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def log_decision(decision: Dict[str, Any]) -> None:
    decision["logged_at"] = datetime.utcnow().isoformat()
    _append_json(LOG_DIR / "decisions.json", decision)


def log_order(order: Dict[str, Any]) -> None:
    order["logged_at"] = datetime.utcnow().isoformat()
    _append_json(LOG_DIR / "orders.json", order)
