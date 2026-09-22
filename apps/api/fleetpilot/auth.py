import hashlib
import uuid

from fastapi import Depends
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import AuthenticationBackend, CookieTransport
from fastapi_users.authentication.strategy.db import DatabaseStrategy
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyAccessTokenDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .db import get_db
from .models import AccessToken, User

settings = get_settings()


class HashedTokenDatabase(SQLAlchemyAccessTokenDatabase[AccessToken]):
    """Keep the library's opaque session lifecycle; store only token digests."""

    async def get_by_token(self, token, max_age=None):
        return await super().get_by_token(hashlib.sha256(token.encode()).hexdigest(), max_age)

    async def create(self, create_dict):
        raw_token = create_dict["token"]
        record = await super().create(
            {**create_dict, "token": hashlib.sha256(raw_token.encode()).hexdigest()}
        )
        # The strategy must send the original token, never its stored digest.
        self.session.expunge(record)
        record.token = raw_token
        return record


async def get_user_db(db: AsyncSession = Depends(get_db, scope="function")):
    return SQLAlchemyUserDatabase(db, User)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    pass


async def get_user_manager(user_db=Depends(get_user_db)):
    return UserManager(user_db)


async def get_strategy(db: AsyncSession = Depends(get_db, scope="function")):
    return DatabaseStrategy(
        HashedTokenDatabase(db, AccessToken), lifetime_seconds=settings.session_lifetime_seconds
    )


class FleetPilotCookieTransport(CookieTransport):
    async def get_login_response(self, token: str):
        response = await super().get_login_response(token)
        response.delete_cookie(
            "fp_organization", secure=settings.cookie_secure, httponly=True, samesite="lax"
        )
        return response

    async def get_logout_response(self):
        response = await super().get_logout_response()
        response.delete_cookie(
            "fp_organization", secure=settings.cookie_secure, httponly=True, samesite="lax"
        )
        return response


transport = FleetPilotCookieTransport(
    cookie_name="fp_session",
    cookie_max_age=settings.session_lifetime_seconds,
    cookie_secure=settings.cookie_secure,
    cookie_httponly=True,
    cookie_samesite="lax",
)
backend = AuthenticationBackend(name="session", transport=transport, get_strategy=get_strategy)
auth = FastAPIUsers[User, uuid.UUID](get_user_manager, [backend])
current_user = auth.current_user(active=True)
