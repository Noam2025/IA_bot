# backend/app/logs/logger.py
# -*- coding: utf-8 -*-
import os
import json
import logging
from logging.handlers import RotatingFileHandler

# --- dossier logs
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
LOG_DIR = os.getenv("LOG_DIR", os.path.join(PROJECT_ROOT, "logs"))
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "app.log")

# --- logger global
logger = logging.getLogger("alpha")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    fh = RotatingFileHandler(LOG_FILE, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

# --- helpers utilisés par le backend
def log_decision(d: dict) -> None:
    try:
        logger.info("decision %s", json.dumps(d, ensure_ascii=False))
    except Exception as e:
        logger.warning("log_decision failed: %s", e)

def log_order(o: dict) -> None:
    try:
        logger.info("order %s", json.dumps(o, ensure_ascii=False))
    except Exception as e:
        logger.warning("log_order failed: %s", e)
