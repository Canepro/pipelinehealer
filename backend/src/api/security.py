"""API security dependencies."""

import hmac
import logging

from fastapi import Header, HTTPException, status

from ..config import get_settings

logger = logging.getLogger(__name__)


async def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    """Require X-API-Key for `/api/*` routes outside development."""
    settings = get_settings()
    if settings.environment == "development":
        return

    if not settings.api_auth_key:
        logger.error("API auth key not configured for non-development environment")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API auth is not configured",
        )

    if not x_api_key or not hmac.compare_digest(x_api_key, settings.api_auth_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


async def require_admin_key(
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
) -> None:
    """Require X-Admin-Key for admin-only settings endpoints."""
    settings = get_settings()

    if not settings.admin_api_key:
        logger.error("Admin API key not configured for admin settings access")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Admin access is not configured",
        )

    if not x_admin_key or not hmac.compare_digest(x_admin_key, settings.admin_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin API key",
        )
