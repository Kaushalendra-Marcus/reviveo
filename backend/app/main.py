"""Reviveo FastAPI application entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .config import settings
from .logging_config import get_logger
from .seed import ensure_seed

logger = get_logger("reviveo.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    ensure_seed()
    logger.info(
        "reviveo started",
        extra={"context": {"run_mode": settings.run_mode.value,
                           "razorpay": settings.razorpay_configured,
                           "ai": settings.ai_configured}},
    )
    yield


app = FastAPI(title="Reviveo API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "run_mode": settings.run_mode.value,
        "razorpay_configured": settings.razorpay_configured,
        "ai_configured": settings.ai_configured,
    }


# Routers are registered here as they are built.
from .api.routes import router as api_router  # noqa: E402
from .webhooks.webhook import router as webhook_router  # noqa: E402

app.include_router(api_router)
app.include_router(webhook_router)
