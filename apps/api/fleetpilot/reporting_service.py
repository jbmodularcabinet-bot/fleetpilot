"""One bounded, locked report calculation for dashboard, reports and exports."""

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlencode
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text

from .config import get_settings
from .expense_routes import rows, safe
from .financial_routes import financial_access
from .permissions import resolve_permissions
from .profitability import calculate_many
from .reporting_contract import (
    MAX_COHORT,
    MAX_EXPORT_ROWS,
    QUALIFICATION,
    REQUIRED_ACCESS,
    VERSION,
    ZERO,
    ReportingPolicy,
    money,
    percent,
)
from .reporting_rules import findings_for


async def reporting_access(db, ctx):
    for capability in REQUIRED_ACCESS:
        ctx.require(capability)
    await db.execute(
        text(
            "SELECT set_config('lock_timeout','2000ms',true), set_config('statement_timeout','8000ms',true)"
        )
    )
    await financial_access(db, ctx)
    await db.refresh(ctx.membership)
    await db.refresh(ctx.organization)
    await db.refresh(ctx.user)
    permissions = resolve_permissions(ctx.membership.role, ctx.membership.permissions_json)
    if (
        not ctx.membership.active
        or not ctx.user.is_active
        or ctx.user.status != "ACTIVE"
        or ctx.organization.status != "ACTIVE"
        or not set(REQUIRED_ACCESS) <= permissions
    ):
        raise HTTPException(403, "Complete financial reporting access is required.")
    return permissions


def policy_for(org):
    try:
        return ReportingPolicy.model_validate((org.settings_json or {}).get("reporting_policy", {}))
    except ValueError as exc:
        raise HTTPException(409, "Reporting policy needs administrator review.") from exc


async def bounded_rows(db, sql, params):
    result = await rows(
        db, sql + " LIMIT :record_limit", **params, record_limit=MAX_EXPORT_ROWS + 1
    )
    if len(result) > MAX_EXPORT_ROWS:
        raise HTTPException(
            413,
            f"Report exceeds {MAX_EXPORT_ROWS} source rows; narrow the filters. No partial report was produced.",
        )
    return result


def aggregate(trips):
    rev = sum((Decimal(t["revenue"]) for t in trips), ZERO)
    cost = sum((Decimal(t["direct_cost"]) for t in trips), ZERO)
    classes = {
        label: sum(t["contribution_class"] == label for t in trips)
        for label in ("POSITIVE", "NEGATIVE", "ZERO", "INSUFFICIENT_DATA")
    }
    return {
        "revenue": money(rev),
        "direct_cost": money(cost),
        "contribution": money(rev - cost),
        "weighted_margin_percent": percent(rev - cost, rev),
        "trip_count": len(trips),
        "positive_count": classes["POSITIVE"],
        "negative_count": classes["NEGATIVE"],
        "zero_count": classes["ZERO"],
        "insufficient_data_count": classes["INSUFFICIENT_DATA"],
        "final_count": sum(t["status"] == "FINAL" for t in trips),
        "provisional_count": sum(t["status"] == "PROVISIONAL" for t in trips),
        "attention_trip_count": sum(
            t["status"] != "FINAL" or bool(t["data_warnings"]) or Decimal(t["contribution"]) < ZERO
            for t in trips
        ),
    }


async def build_report(db, ctx, filters):
    permissions = await reporting_access(db, ctx)
    policy = policy_for(ctx.organization)
    try:
        first, last, start, end = filters.bounds(ctx.organization.timezone)
        configured = json.loads(get_settings().reporting_synthetic_trips_json).get(
            str(ctx.organization.id), []
        )
        synthetic_ids = sorted(
            {
                UUID(str(x))
                for x in [
                    *(ctx.organization.settings_json or {}).get("reporting_synthetic_trip_ids", []),
                    *configured,
                ]
            },
            key=str,
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            422, "Invalid date range, timezone, or synthetic-dataset configuration."
        ) from exc
    synthetic = filters.dataset == "synthetic"
    if synthetic and get_settings().environment == "production":
        raise HTTPException(403, "Synthetic validation reporting is disabled in production.")
    params = {
        "org": ctx.organization.id,
        "start": start,
        "end": end,
        "synthetic_ids": synthetic_ids,
    }
    clauses = [
        "t.organization_id=:org",
        "t.scheduled_pickup_at>=:start",
        "t.scheduled_pickup_at<:end",
        ("" if synthetic else "NOT ") + "(t.id=ANY(CAST(:synthetic_ids AS uuid[])))",
    ]
    for field, value, table in (
        ("customer_id", filters.customer_id, "customers"),
        ("vehicle_id", filters.vehicle_id, "vehicles"),
        ("id", filters.trip_id, "trips"),
    ):
        if value is not None:
            if not await db.scalar(
                text(f"SELECT id FROM {table} WHERE organization_id=:org AND id=:id"),
                {"org": ctx.organization.id, "id": value},
            ):
                raise HTTPException(404, "Filter entity is not available in this organization.")
            key = "filter_" + field
            clauses.append(f"t.{field}=:{key}")
            params[key] = value
    if filters.lifecycle:
        clauses.append("t.current_status=:lifecycle")
        params["lifecycle"] = filters.lifecycle
    selected = await rows(
        db,
        "SELECT t.id,t.version,t.trip_number,t.current_status,t.scheduled_pickup_at,t.customer_id,t.vehicle_id,t.reference_number,"
        "c.company_name AS customer_name,v.unit_number AS vehicle_name FROM trips t "
        "JOIN customers c ON c.organization_id=t.organization_id AND c.id=t.customer_id "
        "LEFT JOIN vehicles v ON v.organization_id=t.organization_id AND v.id=t.vehicle_id WHERE "
        + " AND ".join(clauses)
        + " ORDER BY t.scheduled_pickup_at,t.id LIMIT :max_trips",
        **params,
        max_trips=MAX_COHORT + 1,
    )
    if len(selected) > MAX_COHORT:
        raise HTTPException(
            413,
            f"Report exceeds {MAX_COHORT} trips before the financial-status filter. Narrow the dates; no partial totals were returned.",
        )
    calculated = await calculate_many(db, ctx, selected)
    pairs = [
        (t, f)
        for t, f in zip(selected, calculated, strict=True)
        if not filters.financial_status or f["status"] == filters.financial_status
    ]
    ids = [t["id"] for t, _ in pairs]
    p = {"org": ctx.organization.id, "ids": ids}
    advances, captures, changes = [], [], []
    if ids:
        advances = await bounded_rows(
            db,
            """WITH active AS (
            SELECT e.* FROM cash_advance_settlement_entries e
            WHERE e.organization_id=:org AND NOT EXISTS (
              SELECT 1 FROM cash_advance_settlement_entries r WHERE r.organization_id=e.organization_id AND r.reverses_id=e.id))
            SELECT a.id,a.trip_id,a.source_expense_id,a.amount_issued,a.issued_at,
              coalesce(sum(e.amount) FILTER (WHERE e.entry_type='EXPENSE_APPLIED'),0) AS applied,
              coalesce(sum(e.amount) FILTER (WHERE e.entry_type='CASH_RETURNED'),0) AS returned,
              coalesce(bool_or(e.entry_type='VOID'),false) AS voided
            FROM cash_advances a LEFT JOIN active e ON e.organization_id=a.organization_id AND e.cash_advance_id=a.id
            WHERE a.organization_id=:org AND a.trip_id=ANY(CAST(:ids AS uuid[]))
            GROUP BY a.id,a.trip_id,a.source_expense_id,a.amount_issued,a.issued_at ORDER BY a.issued_at,a.id""",
            p,
        )
        captures = await bounded_rows(
            db,
            """SELECT e.id,e.trip_id,e.status,coalesce(p.amount,r.amount) AS amount,
            a.id AS issuance_id,EXISTS(SELECT 1 FROM cash_advance_settlement_entries s WHERE s.organization_id=e.organization_id AND s.cash_advance_id=a.id AND s.entry_type='VOID') AS issuance_voided
            FROM trip_expenses e JOIN expense_revisions r ON r.organization_id=e.organization_id AND r.expense_id=e.id AND r.revision_number=e.current_revision
            LEFT JOIN expense_effective_values p ON p.organization_id=e.organization_id AND p.expense_id=e.id
            LEFT JOIN cash_advances a ON a.organization_id=e.organization_id AND a.source_expense_id=e.id
            WHERE e.organization_id=:org AND e.trip_id=ANY(CAST(:ids AS uuid[])) AND r.category='DRIVER_CASH_ADVANCE'
              AND e.status<>'VOIDED' AND NOT coalesce(p.voided,false) ORDER BY e.trip_id,e.id""",
            p,
        )
        if "closed_trip_adjustments.read" in permissions:
            changes = await bounded_rows(
                db,
                """SELECT id,trip_id,revenue_id,expense_id,field_name,old_value,new_value,amount_delta,created_at,reverses_id
                FROM closed_trip_adjustments WHERE organization_id=:org AND trip_id=ANY(CAST(:ids AS uuid[]))
                ORDER BY created_at DESC,id""",
                p,
            )
    advances_by_trip, captures_by_trip = defaultdict(list), defaultdict(list)
    for a in advances:
        a["outstanding"] = (
            ZERO if a["voided"] else a["amount_issued"] - a["applied"] - a["returned"]
        )
        a["status"] = (
            "VOIDED"
            if a["voided"]
            else "SETTLED"
            if a["outstanding"] == ZERO
            else "PARTIALLY_SETTLED"
            if a["applied"] + a["returned"]
            else "ISSUED"
        )
        advances_by_trip[a["trip_id"]].append(a)
    for c in captures:
        c["unreconciled"] = not c["issuance_id"] or c["issuance_voided"]
        captures_by_trip[c["trip_id"]].append(c)
    trips, categories = [], {}
    drill_filters = {"dataset": filters.dataset, "date_from": str(first), "date_to": str(last)}
    for t, f in pairs:
        rev = Decimal(f["revenue"]["effective_total"])
        cost = Decimal(f["direct_cost"]["effective_total"])
        has_rev = any(b["reviewed_count"] > 0 for b in f["revenue"]["breakdown"])
        has_cost = any(b["reviewed_count"] > 0 for b in f["direct_cost"]["breakdown"])
        warnings = []
        if not has_rev:
            warnings.append("No reviewed revenue records; revenue is incomplete.")
        if not has_cost:
            warnings.append("No reviewed direct expenses; zero cost has not been confirmed.")
        if f["unreviewed_count"]:
            warnings.append(f"{f['unreviewed_count']} financial inputs remain unreviewed.")
        for b in f["direct_cost"]["breakdown"]:
            category = categories.setdefault(
                b["category"],
                {
                    "category": b["category"],
                    "reviewed_total": ZERO,
                    "submitted_total": ZERO,
                    "unreviewed_count": 0,
                    "trip_ids": [],
                },
            )
            category["reviewed_total"] += Decimal(b["reviewed_total"])
            category["submitted_total"] += Decimal(b["submitted_total"])
            category["unreviewed_count"] += b["unreviewed_count"]
            category["trip_ids"].append(str(t["id"]))
        aa, cc = advances_by_trip[t["id"]], captures_by_trip[t["id"]]
        blockers = f["financial_review_blockers"]
        advance = {
            "captured_amount": money(sum((c["amount"] for c in cc), ZERO)),
            "captured_count": len(cc),
            "unreconciled_capture_count": sum(bool(c["unreconciled"]) for c in cc),
            "issued": money(sum((a["amount_issued"] for a in aa if not a["voided"]), ZERO)),
            "voided_issued": money(sum((a["amount_issued"] for a in aa if a["voided"]), ZERO)),
            "applied": money(sum((a["applied"] for a in aa), ZERO)),
            "returned": money(sum((a["returned"] for a in aa), ZERO)),
            "outstanding": money(sum((a["outstanding"] for a in aa), ZERO)),
            "conflicts": [
                b
                for b in blockers
                if any(
                    k in str(b).upper()
                    for k in ("ADVANCE", "SETTLEMENT", "RECONCIL", "APPLICATION")
                )
            ],
        }
        trip = {
            **safe(t),
            "revenue": money(rev),
            "direct_cost": money(cost),
            "contribution": f["contribution_amount"],
            "margin_percent": f["contribution_margin_percent"],
            "submitted_revenue": f["revenue"]["submitted_total"],
            "submitted_direct_cost": f["direct_cost"]["submitted_total"],
            "category_costs": f["direct_cost"]["breakdown"],
            "status": f["status"],
            "has_reviewed_revenue": has_rev,
            "has_reviewed_cost": has_cost,
            "data_warnings": warnings,
            "contribution_class": "INSUFFICIENT_DATA"
            if not (has_rev and has_cost)
            else "POSITIVE"
            if rev > cost
            else "NEGATIVE"
            if rev < cost
            else "ZERO",
            "financial_review_status": f["financial_review_status"],
            "financial_review_blockers": blockers,
            "advance": advance,
            "review_href": f"/trips/{t['id']}"
            if "trips.read" in permissions
            else "/reports/trip-contribution?"
            + urlencode({**drill_filters, "trip_id": str(t["id"])}),
        }
        trips.append(trip)
    summary = aggregate(trips)
    total_cost = Decimal(summary["direct_cost"])
    category_rows = [
        {**safe(c), "share_percent": percent(c["reviewed_total"], total_cost)}
        for c in sorted(categories.values(), key=lambda c: (-c["reviewed_total"], c["category"]))
    ]
    grouped = defaultdict(list)
    for t in trips:
        grouped[t["customer_id"]].append(t)
    customers = [
        {
            "customer_id": k,
            "customer_name": v[0]["customer_name"],
            **aggregate(v),
            "provisional_contribution": money(
                sum((Decimal(t["contribution"]) for t in v if t["status"] == "PROVISIONAL"), ZERO)
            ),
            "href": "/reports/trip-contribution?" + urlencode({**drill_filters, "customer_id": k}),
        }
        for k, v in grouped.items()
    ]
    customers.sort(key=lambda c: (-Decimal(c["contribution"]), c["customer_id"]))
    lifecycle_totals = [
        {"lifecycle": status, **aggregate([t for t in trips if t["current_status"] == status])}
        for status in sorted({t["current_status"] for t in trips})
    ]
    now = datetime.now(timezone.utc).isoformat()
    findings = findings_for(trips, category_rows, safe(changes), policy, now)
    advance_summary = {
        k: money(sum((Decimal(t["advance"][k]) for t in trips), ZERO))
        for k in (
            "captured_amount",
            "issued",
            "voided_issued",
            "applied",
            "returned",
            "outstanding",
        )
    }
    advance_summary.update(
        {
            "unreconciled_capture_count": sum(
                t["advance"]["unreconciled_capture_count"] for t in trips
            ),
            "attention_trip_count": sum(
                bool(
                    t["advance"]["unreconciled_capture_count"]
                    or Decimal(t["advance"]["outstanding"]) > ZERO
                    or t["advance"]["conflicts"]
                )
                for t in trips
            ),
        }
    )
    warnings = [
        "Values are current effective values of the selected scheduled-pickup cohort, not historical accounting balances."
    ]
    if synthetic:
        warnings.append(
            "SYNTHETIC VALIDATION DATA. These scheduled-pickup examples are not verified deliveries completed today."
        )
    if summary["insufficient_data_count"]:
        warnings.append(
            f"{summary['insufficient_data_count']} trips have insufficient reviewed financial inputs; zero values are not confirmed break-even results."
        )
    if summary["provisional_count"]:
        warnings.append(
            f"{summary['provisional_count']} trips remain PROVISIONAL under the existing financial-review policy."
        )
    history_available = "closed_trip_adjustments.read" in permissions
    if not history_available:
        warnings.append(
            "Material-change history is unavailable with current permissions; no complete-history certification is implied."
        )
    scope = {
        "organization_id": str(ctx.organization.id),
        "organization_name": ctx.organization.name,
        "date_from": str(first),
        "date_to": str(last),
        "date_basis": "Scheduled pickup date",
        "timezone": ctx.organization.timezone,
        "start_inclusive": start.isoformat(),
        "end_exclusive": end.isoformat(),
        "lifecycle": filters.lifecycle or "ALL (including cancelled)",
        "financial_status": filters.financial_status or "ALL",
        "customer_id": str(filters.customer_id) if filters.customer_id else None,
        "vehicle_id": str(filters.vehicle_id) if filters.vehicle_id else None,
        "trip_id": str(filters.trip_id) if filters.trip_id else None,
        "dataset": filters.dataset,
        "synthetic": synthetic,
        "record_count": len(trips),
        "calculated_at": now,
        "rule_version": VERSION,
        "qualification": QUALIFICATION,
        "warnings": warnings,
        "demo_available": bool(synthetic_ids) and get_settings().environment != "production",
    }
    brief = (
        [
            f"{summary['trip_count']} selected trips report PHP {summary['contribution']} contribution on PHP {summary['revenue']} reviewed revenue."
        ]
        if trips
        else ["No trips match this scope. No business performance conclusion is available."]
    )
    if trips:
        brief.append(
            f"{summary['provisional_count']} provisional trips and {summary['insufficient_data_count']} trips with insufficient inputs require careful interpretation."
        )
        brief.extend(f["explanation"] for f in findings[:3])
    result = {
        "scope": scope,
        "summary": summary,
        "policy": policy.model_dump(mode="json"),
        "trips": trips,
        "customers": customers,
        "categories": category_rows,
        "findings": findings,
        "owner_brief": brief,
        "advance_summary": advance_summary,
        "advances": safe(advances),
        "captures": safe(captures),
        "changes": safe(changes),
        "history_available": history_available,
        "lifecycle_totals": lifecycle_totals,
        "filter_options": {
            "customers": [{"id": k, "name": v[0]["customer_name"]} for k, v in grouped.items()],
            "vehicles": list(
                {
                    t["vehicle_id"]: {"id": t["vehicle_id"], "name": t["vehicle_name"]}
                    for t in trips
                    if t["vehicle_id"]
                }.values()
            ),
        },
    }
    fingerprint_value = {
        **result,
        "scope": {k: v for k, v in scope.items() if k != "calculated_at"},
        "findings": [{k: v for k, v in f.items() if k != "calculated_at"} for f in findings],
    }
    scope["fingerprint"] = hashlib.sha256(
        json.dumps(fingerprint_value, sort_keys=True, default=str).encode()
    ).hexdigest()
    return result
