"""Read-only intelligence/reporting endpoints; policy changes are separately audited."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy.exc import DBAPIError

from .audit import record
from .delivery_routes import Context, Database
from .master_routes import write_lock
from .reporting_contract import REPORTS, ReportFilters, ReportingPolicy
from .reporting_exports import TITLES, export_report
from .reporting_service import build_report, policy_for, reporting_access

router = APIRouter(prefix="/api/v1", tags=["Owner intelligence and contribution reports"])


@router.get("/reports/policy")
async def get_policy(ctx: Context, db: Database):
    await reporting_access(db, ctx)
    return {
        "policy": policy_for(ctx.organization).model_dump(mode="json"),
        "basis": "Configurable product defaults, not industry benchmarks",
    }


@router.patch("/reports/policy")
async def update_policy(payload: ReportingPolicy, ctx: Context, db: Database):
    await write_lock(db, ctx, "organization.manage")
    if ctx.membership.role not in {"OWNER", "ADMIN"}:
        raise HTTPException(403, "Only an authorized owner or admin may change reporting policy.")
    before = policy_for(ctx.organization).model_dump(mode="json")
    after = payload.model_dump(mode="json")
    ctx.organization.settings_json = {
        **(ctx.organization.settings_json or {}),
        "reporting_policy": after,
    }
    record(db, ctx, "reporting_policy.updated", "organization", ctx.organization.id, before, after)
    await db.flush()
    return {"policy": after}


async def calculate(ctx, db, filters):
    try:
        async with asyncio.timeout(15):
            return await build_report(db, ctx, filters)
    except TimeoutError as exc:
        raise HTTPException(
            503,
            "Report calculation timed out. Narrow the filters and retry; no zero totals were substituted.",
        ) from exc
    except DBAPIError as exc:
        code = getattr(exc.orig, "sqlstate", None)
        if code in {"55P03", "57014"}:
            raise HTTPException(
                503,
                "Financial records are busy. Retry the report; no partial totals were returned.",
            ) from exc
        raise


def public_result(result, report, filters):
    datasets = {
        "trip-contribution": result["trips"],
        "customer-contribution": result["customers"],
        "direct-costs": result["categories"],
        "financial-exceptions": result["findings"],
        "cash-advances": [{"record_kind": "CAPTURE", **c} for c in result["captures"]]
        + [{"record_kind": "ISSUANCE", **a} for a in result["advances"]],
        "executive-contribution": result["lifecycle_totals"],
    }
    items = datasets[report]
    material_events = {
        f["source_event_id"]
        for f in result["findings"]
        if f["rule_id"] == "MATERIAL_FINANCIAL_CHANGE"
    }
    return {
        "report": report,
        "title": TITLES[report],
        "scope": result["scope"],
        "summary": result["summary"],
        "policy": result["policy"],
        "owner_brief": result["owner_brief"],
        "advance_summary": result["advance_summary"],
        "category_summary": result["categories"],
        "top_customers": result["customers"][:5],
        "priority_findings": result["findings"][:8],
        "finding_count": len(result["findings"]),
        "recent_changes": [c for c in result["changes"] if c["id"] in material_events][:10],
        "history_available": result["history_available"],
        "lifecycle_totals": result["lifecycle_totals"],
        "filter_options": result["filter_options"],
        "items": items[filters.offset : filters.offset + filters.limit],
        "total": len(items),
        "limit": filters.limit,
        "offset": filters.offset,
    }


@router.get("/intelligence/overview")
async def overview(ctx: Context, db: Database, filters: Annotated[ReportFilters, Query()]):
    return public_result(await calculate(ctx, db, filters), "executive-contribution", filters)


@router.get("/intelligence/exceptions")
async def exceptions(ctx: Context, db: Database, filters: Annotated[ReportFilters, Query()]):
    return public_result(await calculate(ctx, db, filters), "financial-exceptions", filters)


@router.get("/reports/{report_name}")
async def report(
    report_name: str, ctx: Context, db: Database, filters: Annotated[ReportFilters, Query()]
):
    if report_name not in REPORTS:
        raise HTTPException(404, "Report not found.")
    result = await calculate(ctx, db, filters)
    if filters.format == "json":
        return public_result(result, report_name, filters)
    output = export_report(report_name, result, filters.format)
    headers = {
        "Cache-Control": "private, no-store",
        "X-Report-Fingerprint": result["scope"]["fingerprint"],
    }
    if filters.format == "csv":
        headers["Content-Disposition"] = (
            f'attachment; filename="fleetpilot-{report_name}-{result["scope"]["date_from"]}.csv"'
        )
    else:
        headers["Content-Security-Policy"] = (
            "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'"
        )
    return Response(
        output, media_type="text/csv" if filters.format == "csv" else "text/html", headers=headers
    )
