"""Authenticated, read-only bootstrap for explicitly configured local demo tenants."""

import json
from uuid import UUID

from fastapi import HTTPException

from .config import get_settings
from .expense_routes import rows
from .reporting_service import reporting_access


async def demo_context(db, ctx):
    await reporting_access(db, ctx)
    result = {
        "organization_id": str(ctx.organization.id),
        "available": False,
        "trip_count": 0,
        "filters": {},
        "timezone": ctx.organization.timezone,
        "date_basis": "Scheduled pickup date",
    }
    settings = get_settings()
    if settings.environment == "production":
        return result
    # Only the dedicated local launcher opts a tenant into automatic demo entry.
    # Persisted organization settings alone never change a business workspace's defaults.
    configured = json.loads(settings.reporting_synthetic_trips_json).get(
        str(ctx.organization.id), []
    )
    identifiers = sorted({UUID(value) for value in configured}, key=str)
    if not identifiers:
        return result
    cohort = (
        await rows(
            db,
            """SELECT count(*) AS trip_count,
        min((scheduled_pickup_at AT TIME ZONE :zone)::date) AS first_day,
        max((scheduled_pickup_at AT TIME ZONE :zone)::date) AS last_day
        FROM trips WHERE organization_id=:org AND id=ANY(CAST(:ids AS uuid[]))""",
            zone=ctx.organization.timezone,
            org=ctx.organization.id,
            ids=identifiers,
        )
    )[0]
    if cohort["trip_count"] != len(identifiers):
        raise HTTPException(
            409,
            "Configured sample trips are incomplete in this workspace. No data was recreated or substituted.",
        )
    if (cohort["last_day"] - cohort["first_day"]).days > 366:
        raise HTTPException(
            409, "Sample trips span more than one report period. Select an explicit date range."
        )
    return {
        **result,
        "available": True,
        "trip_count": cohort["trip_count"],
        "filters": {
            "dataset": "synthetic",
            "date_from": cohort["first_day"].isoformat(),
            "date_to": cohort["last_day"].isoformat(),
        },
    }
