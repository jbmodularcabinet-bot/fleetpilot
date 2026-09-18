import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import current_user
from .db import get_db, set_context
from .models import Membership, Organization, User
from .permissions import resolve_permissions


@dataclass(frozen=True)
class TenantContext:
    user: User
    organization: Organization
    membership: Membership
    permissions: frozenset[str]

    def require(self, permission: str) -> None:
        if permission not in self.permissions:
            raise HTTPException(403, "You do not have permission for this action.")


async def memberships_for(db: AsyncSession, user: User):
    await set_context(db, str(user.id))
    return (
        await db.execute(
            select(Membership, Organization)
            .join(Organization, Membership.organization_id == Organization.id)
            .where(
                Membership.user_id == user.id,
                Membership.active.is_(True),
                Organization.status == "ACTIVE",
            )
            .order_by(Organization.name)
        )
    ).all()


async def resolve_tenant(db: AsyncSession, user: User, selection: str | None) -> TenantContext:
    if user.status != "ACTIVE":
        raise HTTPException(403, "Account is inactive.")
    choices = await memberships_for(db, user)
    if not choices:
        raise HTTPException(403, "No active organization membership. Contact your administrator.")
    try:
        selected_id = uuid.UUID(selection) if selection else choices[0][1].id
    except ValueError as exc:
        raise HTTPException(403, "Organization access denied.") from exc
    selected = next((row for row in choices if row[1].id == selected_id), None)
    if selected is None:
        raise HTTPException(403, "Organization access denied.")
    membership, organization = selected
    await set_context(db, str(user.id), str(organization.id))
    return TenantContext(
        user,
        organization,
        membership,
        resolve_permissions(membership.role, membership.permissions_json),
    )


async def tenant(
    request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> TenantContext:
    return await resolve_tenant(db, user, request.cookies.get("fp_organization"))


class TenantRepository:
    """All future tenant repositories must require this validated context."""

    def __init__(self, db: AsyncSession, context: TenantContext):
        self.db = db
        self.context = context

    def memberships(self):
        return select(Membership).where(Membership.organization_id == self.context.organization.id)

    async def member(self, member_id: uuid.UUID) -> Membership:
        member = await self.db.scalar(
            self.memberships().where(Membership.id == member_id).with_for_update()
        )
        if member is None:
            raise HTTPException(404, "Membership not found.")
        return member
