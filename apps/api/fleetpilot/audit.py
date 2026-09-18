from sqlalchemy.ext.asyncio import AsyncSession

from .models import AuditLog
from .tenancy import TenantContext


def record(
    db: AsyncSession,
    context: TenantContext,
    action: str,
    entity_type: str,
    entity_id,
    before: dict | None,
    after: dict | None,
    ip: str | None = None,
) -> None:
    # Callers supply allowlisted business fields only. Never serialize User/session objects.
    db.add(
        AuditLog(
            organization_id=context.organization.id,
            actor_user_id=context.user.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before_json=before,
            after_json=after,
            ip_address=ip,
        )
    )
