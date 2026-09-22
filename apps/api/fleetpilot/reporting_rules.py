"""Explainable, deterministic findings over authorized reviewed financial values."""

from decimal import Decimal

from .reporting_contract import VERSION, ZERO, money, percent


def findings_for(trips, categories, changes, policy, calculated_at):
    findings = []

    def add(rule, priority, title, explanation, values, threshold, trip=None, event=None):
        entity = str(trip["id"]) if trip else "cohort"
        key = f"{VERSION}:{rule}:{entity}:{event or ''}"
        findings.append(
            {
                "key": key,
                "rule_id": rule,
                "rule_version": VERSION,
                "priority": priority,
                "title": title,
                "explanation": explanation,
                "supporting_values": values,
                "comparison_basis": threshold,
                "trip_id": str(trip["id"]) if trip else None,
                "affected_entity_ids": [str(trip["id"])] if trip else [],
                "source_event_id": str(event) if event else None,
                "qualification": "Current reviewed operational values; provisional inputs may be incomplete.",
                "recommended_action": "Review the supporting source records; no financial action has been performed.",
                "href": trip["review_href"] if trip else "/reports/direct-costs",
                "calculated_at": calculated_at,
            }
        )

    for t in trips:
        rev, cost, contribution = (
            Decimal(t[k]) for k in ("revenue", "direct_cost", "contribution")
        )
        if not t["has_reviewed_revenue"] and t["has_reviewed_cost"]:
            add(
                "MISSING_REVIEWED_REVENUE",
                "CRITICAL",
                "Reviewed revenue is missing",
                f"{t['trip_number']} has reviewed costs of PHP {money(cost)} without reviewed revenue. Confirm missing revenue before interpreting the reported deficit.",
                {"reviewed_revenue": money(rev), "reviewed_direct_cost": money(cost)},
                "Reviewed cost records exist; reviewed revenue records do not.",
                t,
            )
        if contribution < ZERO:
            add(
                "NEGATIVE_CONTRIBUTION",
                "HIGH",
                "Negative reported contribution",
                f"{t['trip_number']} reports PHP {money(contribution)} contribution: PHP {money(rev)} reviewed revenue less PHP {money(cost)} direct costs. This is not net profit.",
                {
                    "revenue": money(rev),
                    "direct_cost": money(cost),
                    "contribution": money(contribution),
                },
                "Contribution < PHP 0.00",
                t,
            )
        if (
            rev > ZERO
            and contribution >= ZERO
            and contribution * 100 < policy.low_margin_percent * rev
        ):
            add(
                "LOW_CONTRIBUTION_MARGIN",
                "MEDIUM",
                "Contribution margin below policy",
                f"{t['trip_number']} reports {percent(contribution, rev)}% contribution margin, below the configured {money(policy.low_margin_percent)}%. It is not a claim of net loss.",
                {"margin_percent": percent(contribution, rev)},
                f"Non-negative margin < {money(policy.low_margin_percent)}% (product policy, not industry benchmark)",
                t,
            )
        if rev > ZERO and cost * 100 > policy.direct_cost_pressure_percent * rev:
            add(
                "DIRECT_COST_PRESSURE",
                "MEDIUM",
                "Direct costs exceed the policy share",
                f"{t['trip_number']} direct costs are {percent(cost, rev)}% of reviewed revenue.",
                {"direct_cost_percent_of_revenue": percent(cost, rev)},
                f"Cost share > {money(policy.direct_cost_pressure_percent)}%",
                t,
            )
        if t["status"] != "FINAL" or t["data_warnings"]:
            reasons = list(t["financial_review_blockers"]) + list(t["data_warnings"])
            if t["financial_review_status"] != "APPROVED":
                reasons.append("Explicit financial approval is not current.")
            add(
                "FINANCIAL_REVIEW_INCOMPLETE",
                "HIGH" if t["data_warnings"] else "MEDIUM",
                "Financial review remains incomplete",
                f"{t['trip_number']}: " + "; ".join(str(x) for x in dict.fromkeys(reasons)),
                {
                    "financial_status": t["status"],
                    "review_status": t["financial_review_status"],
                    "blockers": reasons,
                },
                "Existing financial-governance policy",
                t,
            )
        a = t["advance"]
        if a["unreconciled_capture_count"] or Decimal(a["outstanding"]) > ZERO or a["conflicts"]:
            add(
                "ADVANCE_ATTENTION",
                "HIGH",
                "Cash advance review required",
                f"{t['trip_number']}: {a['unreconciled_capture_count']} unreconciled captured records; PHP {a['outstanding']} confirmed issuance outstanding. Captures are not confirmed issuance or settlement balances.",
                a,
                "Unreconciled capture, positive outstanding issuance or governance conflict",
                t,
            )
    by_id = {str(t["id"]): t for t in trips}
    for event in changes:
        if event.get("amount_delta") is None:
            continue
        delta = Decimal(str(event["amount_delta"]))
        trip = by_id.get(str(event["trip_id"]))
        if trip and abs(delta) >= policy.material_change_php:
            direction = delta if event.get("revenue_id") else -delta
            add(
                "MATERIAL_FINANCIAL_CHANGE",
                "MEDIUM",
                "Material source-amount change",
                f"{trip['trip_number']} source amount changed from PHP {event['old_value']} to PHP {event['new_value']} (delta PHP {money(delta)}). The event is historical; current contribution already uses effective reviewed records. Do not sum past events as a forecast.",
                {
                    "before": event["old_value"],
                    "after": event["new_value"],
                    "amount_delta": money(delta),
                    "contribution_direction_if_reviewed": money(direction),
                    "occurred_at": event["created_at"],
                },
                f"Absolute source-amount delta >= PHP {money(policy.material_change_php)}; current review eligibility must be checked",
                trip,
                event["id"],
            )
    total_cost = sum((Decimal(c["reviewed_total"]) for c in categories), ZERO)
    for category in categories:
        amount = Decimal(category["reviewed_total"])
        if (
            total_cost > ZERO
            and amount > ZERO
            and amount * 100 >= policy.cost_concentration_percent * total_cost
        ):
            add(
                "COST_CONCENTRATION:" + category["category"],
                "LOW",
                "Direct-cost concentration",
                f"{category['category'].replace('_', ' ').title()} represents {percent(amount, total_cost)}% of reviewed direct costs. Concentration does not establish waste, fuel theft, consumption efficiency, or driver performance.",
                {
                    "category": category["category"],
                    "amount": money(amount),
                    "direct_cost_total": money(total_cost),
                    "share_percent": percent(amount, total_cost),
                },
                f"Category share >= {money(policy.cost_concentration_percent)}%",
            )
    rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    return sorted(
        {f["key"]: f for f in findings}.values(),
        key=lambda f: (rank[f["priority"]], f["rule_id"], f["key"]),
    )
