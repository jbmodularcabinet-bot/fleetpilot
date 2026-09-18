"""One server calculation layer; only reviewed effective operational values count."""

from collections import defaultdict
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from .expense_routes import rows, safe

ZERO = Decimal("0.00")


def calculate(trip, revenue, costs, governance=None):
    def totals(items):
        return sum((r["reviewed_total"] for r in items), ZERO)

    direct = [r for r in costs if r["category"] != "DRIVER_CASH_ADVANCE"]
    rev, cost = totals(revenue), totals(direct)
    contribution = rev - cost
    pending = sum(r["unreviewed_count"] for r in revenue + direct)
    return safe(
        {
            "trip_id": trip["id"],
            "currency": "PHP",
            "basis": "REVIEWED_EFFECTIVE",
            "revenue": {
                "effective_total": rev,
                "submitted_total": sum((r["submitted_total"] for r in revenue), ZERO),
                "breakdown": revenue,
            },
            "direct_cost": {
                "effective_total": cost,
                "submitted_total": sum((r["submitted_total"] for r in direct), ZERO),
                "breakdown": direct,
            },
            "excluded_cash_advances": sum(
                (r["submitted_total"] for r in costs if r["category"] == "DRIVER_CASH_ADVANCE"),
                ZERO,
            ),
            "contribution_amount": contribution,
            "contribution_margin_percent": (contribution / rev * 100).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if rev
            else None,
            "status": "FINAL"
            if trip["current_status"] == "COMPLETED"
            and pending == 0
            and any(r["reviewed_count"] for r in revenue)
            and governance is not None
            and governance["review_status"] == "APPROVED"
            and not governance["blockers"]
            else "PROVISIONAL",
            "financial_review_status": governance["review_status"] if governance else "NOT_READY",
            "financial_review_blockers": governance["blockers"] if governance else [],
            "unreviewed_count": pending,
            "calculated_at": datetime.now(timezone.utc),
        }
    )


async def calculate_many(db, ctx, trips):
    if not trips:
        return []
    params = dict(org=ctx.organization.id, ids=[t["id"] for t in trips])
    revenue = await rows(
        db,
        """SELECT r.trip_id,r.revenue_type AS category,
      coalesce(sum(coalesce(p.amount,r.amount)),0) AS submitted_total,
      coalesce(sum(coalesce(p.amount,r.amount)) FILTER(WHERE r.status='REVIEWED'),0) AS reviewed_total,
      count(*) FILTER(WHERE r.status='SUBMITTED') AS unreviewed_count,
      count(*) FILTER(WHERE r.status='REVIEWED') AS reviewed_count
      FROM trip_revenue r LEFT JOIN revenue_effective_values p ON p.organization_id=r.organization_id AND p.revenue_id=r.id
      WHERE r.organization_id=:org AND r.trip_id=ANY(CAST(:ids AS uuid[])) AND r.status<>'VOIDED' AND NOT coalesce(p.voided,false)
      GROUP BY r.trip_id,r.revenue_type""",
        **params,
    )
    costs = await rows(
        db,
        """SELECT e.trip_id,r.category,
      coalesce(sum(coalesce(p.amount,r.amount)),0) AS submitted_total,
      coalesce(sum(coalesce(p.amount,r.amount)) FILTER(WHERE e.status='REVIEWED' OR l.id IS NOT NULL),0) AS reviewed_total,
      count(*) FILTER(WHERE e.status='SUBMITTED' AND l.id IS NULL) AS unreviewed_count,
      count(*) FILTER(WHERE e.status='REVIEWED' OR l.id IS NOT NULL) AS reviewed_count
      FROM trip_expenses e JOIN expense_revisions r ON r.organization_id=e.organization_id AND r.expense_id=e.id AND r.revision_number=e.current_revision
      LEFT JOIN expense_effective_values p ON p.organization_id=e.organization_id AND p.expense_id=e.id
      LEFT JOIN legacy_expense_review_events l ON l.organization_id=e.organization_id AND l.expense_id=e.id AND l.action='ACCEPTED'
      WHERE e.organization_id=:org AND e.trip_id=ANY(CAST(:ids AS uuid[])) AND e.status<>'VOIDED' AND NOT coalesce(p.voided,false)
      GROUP BY e.trip_id,r.category""",
        **params,
    )
    revs, expenses = defaultdict(list), defaultdict(list)
    for r in revenue:
        revs[r["trip_id"]].append(r)
    for r in costs:
        expenses[r["trip_id"]].append(r)
    governance = await rows(
        db,
        """SELECT t.id,financial_review_blockers(t.id) AS blockers,
      coalesce((SELECT status FROM trip_financial_review_events e WHERE e.organization_id=t.organization_id AND e.trip_id=t.id ORDER BY sequence DESC LIMIT 1),'READY_FOR_REVIEW') AS review_status
      FROM trips t WHERE t.organization_id=:org AND t.id=ANY(CAST(:ids AS uuid[]))""",
        **params,
    )
    states = {g["id"]: g for g in governance}
    for g in governance:
        if g["blockers"]:
            g["review_status"] = "NEEDS_ATTENTION"
        elif g["review_status"] == "NEEDS_ATTENTION":
            g["review_status"] = "READY_FOR_REVIEW"
    return [calculate(t, revs[t["id"]], expenses[t["id"]], states[t["id"]]) for t in trips]
