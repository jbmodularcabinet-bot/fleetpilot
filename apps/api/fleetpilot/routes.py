import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .audit import record
from .auth import current_user
from .client_demo_access import CLIENT_DEMO_ACCESS_PROFILE, is_client_demo_membership
from .config import get_settings
from .db import get_db
from .models import AuditLog, Membership, Organization, User
from .schemas import (
    MembershipCreate,
    MembershipUpdate,
    OrganizationOut,
    OrganizationSelection,
    OrganizationUpdate,
)
from .tenancy import TenantContext, TenantRepository, memberships_for, resolve_tenant, tenant

router = APIRouter(prefix="/api/v1")


def organization_dict(org: Organization) -> dict:
    return OrganizationOut.model_validate(org).model_dump(mode="json")


@router.get("/me")
async def me(
    ctx: TenantContext = Depends(tenant), db: AsyncSession = Depends(get_db, scope="function")
):
    organizations = [organization_dict(org) for _, org in await memberships_for(db, ctx.user)]
    return {
        "user": {"id": str(ctx.user.id), "name": ctx.user.name, "email": ctx.user.email},
        "organization": organization_dict(ctx.organization),
        "membership": {
            "id": str(ctx.membership.id),
            "role": ctx.membership.role,
            "access_profile": CLIENT_DEMO_ACCESS_PROFILE
            if is_client_demo_membership(ctx.membership.permissions_json)
            else None,
        },
        "permissions": sorted(ctx.permissions),
        "organizations": organizations,
    }


@router.post("/organization-selection")
async def select_organization(
    payload: OrganizationSelection,
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    ctx = await resolve_tenant(db, user, str(payload.organization_id))
    response.set_cookie(
        "fp_organization",
        str(ctx.organization.id),
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="lax",
        max_age=get_settings().session_lifetime_seconds,
    )
    return {"organization": organization_dict(ctx.organization)}


@router.get("/organizations/{organization_id}")
async def read_organization(organization_id: uuid.UUID, ctx: TenantContext = Depends(tenant)):
    ctx.require("organization.read")
    if organization_id != ctx.organization.id:
        raise HTTPException(404, "Organization not found.")
    return organization_dict(ctx.organization)


@router.patch("/organizations/{organization_id}")
async def update_organization(
    organization_id: uuid.UUID,
    payload: OrganizationUpdate,
    request: Request,
    ctx: TenantContext = Depends(tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    ctx.require("organization.manage")
    if organization_id != ctx.organization.id:
        raise HTTPException(404, "Organization not found.")
    org = await db.scalar(
        select(Organization)
        .where(Organization.id == organization_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    before = organization_dict(org)
    for key, value in payload.model_dump().items():
        setattr(org, key, value)
    record(
        db,
        ctx,
        "organization.updated",
        "organization",
        org.id,
        before,
        organization_dict(org),
        request.client.host if request.client else None,
    )
    await db.flush()
    return organization_dict(org)


@router.get("/memberships")
async def list_memberships(
    ctx: TenantContext = Depends(tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    ctx.require("users.read")
    rows = (
        await db.execute(
            select(Membership, User)
            .join(User, Membership.user_id == User.id)
            .where(Membership.organization_id == ctx.organization.id)
            .order_by(User.name, Membership.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [
        {
            "id": str(m.id),
            "user_id": str(u.id),
            "email": u.email,
            "name": u.name,
            "role": m.role,
            "active": m.active,
        }
        for m, u in rows
    ]


async def lock_organization(db: AsyncSession, ctx: TenantContext):
    # Serializes membership administration, including concurrent last-owner changes.
    await db.execute(
        select(Organization.id).where(Organization.id == ctx.organization.id).with_for_update()
    )
    await db.refresh(ctx.membership)
    if not ctx.membership.active or ctx.membership.role not in ("OWNER", "ADMIN"):
        raise HTTPException(403, "Membership administration is no longer permitted.")


@router.post("/memberships", status_code=201)
async def add_membership(
    payload: MembershipCreate,
    ctx: TenantContext = Depends(tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    ctx.require("users.manage")
    await lock_organization(db, ctx)
    if payload.role in ("OWNER", "ADMIN") and ctx.membership.role != "OWNER":
        raise HTTPException(403, "Only an owner can grant owner or admin access.")
    user = await db.scalar(
        select(User).where(
            User.email == payload.email.lower(), User.is_active.is_(True), User.status == "ACTIVE"
        )
    )
    if user is None:
        raise HTTPException(
            422,
            "This account is not provisioned. Ask the system administrator to provision it first.",
        )
    existing = await db.scalar(
        TenantRepository(db, ctx).memberships().where(Membership.user_id == user.id)
    )
    if existing:
        raise HTTPException(409, "Membership already exists. Edit the existing membership.")
    member = Membership(
        organization_id=ctx.organization.id, user_id=user.id, role=payload.role.value
    )
    db.add(member)
    await db.flush()
    record(
        db,
        ctx,
        "membership.created",
        "membership",
        member.id,
        None,
        {"role": member.role, "active": True, "user_id": str(user.id)},
    )
    return {"id": str(member.id)}


@router.patch("/memberships/{membership_id}")
async def update_membership(
    membership_id: uuid.UUID,
    payload: MembershipUpdate,
    ctx: TenantContext = Depends(tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    ctx.require("users.manage")
    await lock_organization(db, ctx)
    member = await TenantRepository(db, ctx).member(membership_id)
    if ctx.membership.role != "OWNER" and (
        member.role in ("OWNER", "ADMIN") or payload.role in ("OWNER", "ADMIN")
    ):
        raise HTTPException(403, "Only an owner can change owner or admin access.")
    if member.user_id == ctx.user.id and (payload.role.value != member.role or not payload.active):
        raise HTTPException(409, "Ask another owner to change your access.")
    if member.role == "OWNER" and member.active and (payload.role != "OWNER" or not payload.active):
        other = await db.scalar(
            TenantRepository(db, ctx)
            .memberships()
            .where(
                Membership.role == "OWNER", Membership.active.is_(True), Membership.id != member.id
            )
        )
        if other is None:
            raise HTTPException(409, "An organization must retain an active owner.")
    before = {"role": member.role, "active": member.active}
    after = {"role": payload.role.value, "active": payload.active}
    if before["role"] != after["role"]:
        record(db, ctx, "membership.role_changed", "membership", member.id, before, after)
    if before["active"] != after["active"]:
        record(
            db,
            ctx,
            "membership.enabled" if payload.active else "membership.disabled",
            "membership",
            member.id,
            before,
            after,
        )
    member.role, member.active = payload.role.value, payload.active
    await db.flush()
    return {"id": str(member.id), **after}


@router.get("/audit-logs")
async def audit_logs(
    ctx: TenantContext = Depends(tenant),
    db: AsyncSession = Depends(get_db, scope="function"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    entity_type: str | None = Query(None, max_length=40),
    entity_id: uuid.UUID | None = None,
):
    ctx.require("audit.read")
    query = select(AuditLog).where(AuditLog.organization_id == ctx.organization.id)
    if entity_type in {"vehicle", "driver"} and entity_id:
        query = query.where(
            or_(
                and_(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id),
                and_(
                    AuditLog.entity_type == "assignment",
                    AuditLog.after_json[f"{entity_type}_id"].astext == str(entity_id),
                ),
            )
        )
    else:
        if entity_type:
            query = query.where(AuditLog.entity_type == entity_type)
        if entity_id:
            query = query.where(AuditLog.entity_id == entity_id)
    rows = (
        await db.scalars(
            query.order_by(AuditLog.created_at.desc(), AuditLog.id).limit(limit).offset(offset)
        )
    ).all()
    return [
        {
            "id": str(row.id),
            "action": row.action,
            "entity_type": row.entity_type,
            "entity_id": str(row.entity_id),
            "actor_user_id": str(row.actor_user_id),
            "created_at": row.created_at.isoformat(),
            "before": row.before_json,
            "after": row.after_json,
        }
        for row in rows
    ]
