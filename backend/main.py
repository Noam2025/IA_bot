# backend/main.py
from __future__ import annotations

import importlib
import logging
import os
from typing import Optional, Sequence

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware


def _setup_logging() -> None:
    """
    Logging simple et stable (VPS-friendly).
    Si tu as déjà un structured logger ailleurs, garde-le et supprime ce bloc.
    """
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def _include_router_smart(app: FastAPI, router: APIRouter, desired_prefix: str, tags: Optional[list[str]] = None) -> None:
    """
    Inclut un APIRouter en évitant le double prefix.
    - Si router.prefix est déjà égal au desired_prefix, on inclut sans re-prefixer.
    - Sinon, on inclut avec desired_prefix.
    """
    try:
        router_prefix = getattr(router, "prefix", "") or ""
        if router_prefix == desired_prefix:
            app.include_router(router, tags=tags)
        else:
            app.include_router(router, prefix=desired_prefix, tags=tags)
    except Exception:
        logging.exception("Router include failed (desired_prefix=%s)", desired_prefix)


def _try_import_router(module_path: str) -> Optional[APIRouter]:
    """
    Importe un module et retourne un APIRouter depuis:
    - module.router
    - module.api_router
    Sinon None.
    """
    try:
        mod = importlib.import_module(module_path)
    except Exception as e:
        logging.error("Cannot import module '%s': %s", module_path, e, exc_info=True)
        return None

    router = getattr(mod, "router", None) or getattr(mod, "api_router", None)
    if router is None:
        logging.error("Module '%s' imported but no 'router' or 'api_router' found.", module_path)
        return None

    return router


def _mount_routers(app: FastAPI) -> None:
    """
    Monte les routers si présents. Zéro dépendance sur app/api/__init__.py
    => élimine les ImportError 'cannot import name X from app.api'.
    """
    targets: Sequence[tuple[str, str, str]] = (
        # (module_path, desired_prefix, tag)
        ("app.api.live", "/api/live", "live"),
        ("app.api.decisions", "/api/decisions", "decisions"),
        ("app.api.orders", "/api/orders", "orders"),
        ("app.api.pnl", "/api/pnl", "pnl"),
        ("app.api.auto", "/api/auto", "auto"),
        ("app.api.routes_status", "/api/status", "status"),
    )

    for module_path, prefix, tag in targets:
        router = _try_import_router(module_path)
        if router is None:
            continue
        _include_router_smart(app, router, desired_prefix=prefix, tags=[tag])
        logging.info("Mounted router: %s -> %s", module_path, prefix)


def create_app() -> FastAPI:
    _setup_logging()

    app = FastAPI(
        title="IA Trading Backend",
        version="0.1.0",
    )

    # CORS (dashboard Streamlit)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # à restreindre en prod
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    _mount_routers(app)

    # Healthcheck simple
    @app.get("/health", tags=["health"])
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
