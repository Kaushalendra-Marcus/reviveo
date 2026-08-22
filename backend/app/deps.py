"""Shared FastAPI dependencies."""
from __future__ import annotations

from fastapi import Header, HTTPException, status

from .config import settings


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Minimum-viable auth (doc §A4): a single shared key in the X-API-Key header.
    This is an explicit hackathon-scope limitation, stated in the README."""
    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API key"
        )
