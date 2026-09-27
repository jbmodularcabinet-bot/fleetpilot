"""Request-scoped Sites identity assertions. No browser or persistent bridge token."""

import hashlib
import time
import uuid

import jwt
from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .models import User


def provider_id(issuer: str, subject: str) -> str:
    return "sites:" + hashlib.sha256((issuer + "\n" + subject).encode()).hexdigest()


async def principal(request: Request, db: AsyncSession) -> User:
    settings = get_settings()
    denied = HTTPException(401, "Invalid Sites identity assertion.")
    secret = settings.sites_bridge_secret
    if (
        not secret
        or len(secret) < 48
        or not settings.sites_bridge_issuer
        or not settings.sites_bridge_audience
        or not settings.sites_bridge_organization_id
        or request.method != "GET"
        or request.url.path != "/api/v1/me"
        or request.url.query
    ):
        raise denied
    value = request.headers.get("authorization", "")
    if not value.startswith("Bearer ") or len(value) > 4096:
        raise denied
    try:
        claims = jwt.decode(
            value[7:],
            secret,
            algorithms=["HS256"],
            issuer=settings.sites_bridge_issuer,
            audience=settings.sites_bridge_audience,
            options={
                "require": ["iss", "aud", "sub", "iat", "nbf", "exp", "jti", "scope"],
                "strict_aud": True,
            },
        )
        now = int(time.time())
        if (
            any(type(claims[k]) is not int for k in ("iat", "nbf", "exp"))
            or not 0 < claims["exp"] - claims["iat"] <= 30
            or now - claims["iat"] > 30
            or claims["nbf"] != claims["iat"]
            or claims["scope"] != "parent:me"
            or not isinstance(claims["sub"], str)
            or not 1 <= len(claims["sub"]) <= 200
            or len(claims["jti"]) != 32
        ):
            raise denied
        uuid.UUID(hex=claims["jti"])
        organization_id = str(uuid.UUID(settings.sites_bridge_organization_id))
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        raise denied from None
    user = await db.scalar(
        select(User).where(
            User.auth_provider_id == provider_id(settings.sites_bridge_issuer, claims["sub"]),
            User.is_active.is_(True),
            User.status == "ACTIVE",
        )
    )
    if user is None:
        raise denied
    request.state.sites_bridge_organization_id = organization_id
    return user
