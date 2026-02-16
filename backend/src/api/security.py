"""API security dependencies."""

from __future__ import annotations

import hmac
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
from fastapi import Header, HTTPException, Request, status
from jwt import InvalidTokenError, PyJWKClient

from ..config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthPrincipal:
    """Normalized authenticated principal extracted from a bearer token."""

    subject: str
    roles: frozenset[str]
    scopes: frozenset[str]
    claims: dict[str, Any]


def get_request_principal(request: Request) -> AuthPrincipal | None:
    """Return principal cached on request state by auth dependencies."""
    principal = getattr(request.state, "auth_principal", None)
    if isinstance(principal, AuthPrincipal):
        return principal
    return None


def _extract_bearer_token(authorization: str | None) -> str | None:
    """Extract bearer token from Authorization header."""
    if not authorization:
        return None
    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2:
        return None
    scheme, token = parts
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _resolve_entra_runtime_config() -> tuple[str, str, tuple[str, ...]]:
    """Resolve issuer/jwks/audience settings for Entra token validation."""
    settings = get_settings()
    tenant_id = settings.entra_tenant_id.strip()
    client_id = settings.entra_client_id.strip()

    issuer = settings.entra_issuer.strip()
    if not issuer and tenant_id:
        issuer = f"https://login.microsoftonline.com/{tenant_id}/v2.0"

    jwks_url = settings.entra_jwks_url.strip()
    if not jwks_url and tenant_id:
        jwks_url = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"

    audiences = tuple(audience.strip() for audience in settings.entra_allowed_audiences if audience.strip())
    if not audiences and client_id:
        audiences = (f"api://{client_id}", client_id)

    if not issuer or not jwks_url or not audiences:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Entra auth is enabled but missing configuration. "
                "Set ENTRA_TENANT_ID + ENTRA_CLIENT_ID (or explicit ENTRA_ISSUER, "
                "ENTRA_JWKS_URL, ENTRA_ALLOWED_AUDIENCES)."
            ),
        )

    return issuer, jwks_url, audiences


@lru_cache(maxsize=8)
def _get_jwk_client(jwks_url: str) -> PyJWKClient:
    """Cache JWK client instances by URL."""
    return PyJWKClient(jwks_url)


def _validate_bearer_token(authorization: str | None) -> AuthPrincipal:
    """Validate Entra bearer token and return principal."""
    token = _extract_bearer_token(authorization)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bearer token",
        )

    issuer, jwks_url, audiences = _resolve_entra_runtime_config()
    jwk_client = _get_jwk_client(jwks_url)

    try:
        signing_key = jwk_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=list(audiences),
            issuer=issuer,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Bearer token validation failed unexpectedly: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
        ) from exc

    roles_raw = claims.get("roles")
    roles: set[str] = set()
    if isinstance(roles_raw, str) and roles_raw.strip():
        roles.add(roles_raw.strip())
    elif isinstance(roles_raw, list):
        for role in roles_raw:
            text = str(role).strip()
            if text:
                roles.add(text)

    scope_raw = claims.get("scp")
    scopes: set[str] = set()
    if isinstance(scope_raw, str):
        scopes = {scope for scope in scope_raw.split() if scope}

    subject = str(claims.get("oid") or claims.get("sub") or "").strip()
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token: missing subject",
        )

    return AuthPrincipal(
        subject=subject,
        roles=frozenset(roles),
        scopes=frozenset(scopes),
        claims=claims,
    )


def _validate_api_key_header(x_api_key: str | None) -> None:
    """Validate legacy API key header."""
    settings = get_settings()
    if not settings.api_auth_key:
        logger.error("API auth key not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API auth is not configured",
        )
    if not x_api_key or not hmac.compare_digest(x_api_key, settings.api_auth_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


def _validate_admin_key_header(x_admin_key: str | None) -> None:
    """Validate legacy admin key header."""
    settings = get_settings()
    if not settings.admin_api_key:
        logger.error("Admin API key not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Admin access is not configured",
        )
    if not x_admin_key or not hmac.compare_digest(x_admin_key, settings.admin_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin API key",
        )


def _require_admin_role(principal: AuthPrincipal) -> None:
    """Require configured Entra admin role/scope on principal."""
    settings = get_settings()
    required = {role.strip() for role in settings.entra_admin_roles if role.strip()}
    if not required:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Entra admin roles are not configured",
        )

    if required.isdisjoint(principal.roles) and required.isdisjoint(principal.scopes):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient role for admin endpoint",
        )


async def require_api_key(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    """Authenticate /api requests based on configured auth mode."""
    settings = get_settings()
    mode = settings.auth_mode

    # Preserve current local-development behavior for legacy key mode.
    if mode == "api_key" and settings.environment == "development":
        return

    if mode == "api_key":
        _validate_api_key_header(x_api_key)
        return

    if mode == "entra":
        request.state.auth_principal = _validate_bearer_token(authorization)
        return

    if mode == "hybrid":
        if _extract_bearer_token(authorization):
            request.state.auth_principal = _validate_bearer_token(authorization)
            return
        if x_api_key:
            _validate_api_key_header(x_api_key)
            return
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing credentials: provide Bearer token or X-API-Key",
        )

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Invalid auth mode configuration",
    )


async def require_admin_key(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
) -> None:
    """Authorize admin settings routes by key, role, or both in hybrid mode."""
    settings = get_settings()
    mode = settings.auth_mode

    if mode == "api_key":
        _validate_admin_key_header(x_admin_key)
        return

    if mode == "entra":
        principal = get_request_principal(request) or _validate_bearer_token(authorization)
        _require_admin_role(principal)
        request.state.auth_principal = principal
        return

    if mode == "hybrid":
        if _extract_bearer_token(authorization):
            principal = get_request_principal(request) or _validate_bearer_token(authorization)
            _require_admin_role(principal)
            request.state.auth_principal = principal
            return
        _validate_admin_key_header(x_admin_key)
        return

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Invalid auth mode configuration",
    )
