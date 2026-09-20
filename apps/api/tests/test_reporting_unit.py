import csv
import io
from datetime import datetime, timezone
from decimal import ROUND_DOWN, Decimal, localcontext

import pytest
from pydantic import ValidationError

from fleetpilot.permissions import resolve_permissions
from fleetpilot.profitability import calculate
from fleetpilot.reporting_contract import (
    QUALIFICATION,
    REQUIRED_ACCESS,
    ReportFilters,
    ReportingPolicy,
    money,
    percent,
)
from fleetpilot.reporting_exports import Numeric, cell, export_report
from fleetpilot.reporting_rules import findings_for
from fleetpilot.reporting_service import aggregate


def row(revenue="22000.00", cost="9850.00", identifier="A", has_rev=True, has_cost=True):
    def part(category, value, reviewed):
        return {
            "category": category,
            "reviewed_total": Decimal(value),
            "submitted_total": Decimal(value),
            "reviewed_count": int(reviewed),
            "unreviewed_count": 0,
        }

    f = calculate(
        {"id": identifier, "current_status": "DISPATCHED"},
        [part("BASE_TRIP_CHARGE", revenue, has_rev)] if has_rev else [],
        [part("FUEL", cost, has_cost)] if has_cost else [],
        {"review_status": "NEEDS_ATTENTION", "blockers": ["Trip must be completed."]},
    )
    r, c = Decimal(revenue), Decimal(cost)
    return {
        "id": identifier,
        "trip_number": identifier,
        "revenue": money(r),
        "direct_cost": money(c),
        "contribution": f["contribution_amount"],
        "margin_percent": f["contribution_margin_percent"],
        "status": f["status"],
        "has_reviewed_revenue": has_rev,
        "has_reviewed_cost": has_cost,
        "contribution_class": "INSUFFICIENT_DATA"
        if not (has_rev and has_cost)
        else "NEGATIVE"
        if r < c
        else "POSITIVE"
        if r > c
        else "ZERO",
        "data_warnings": [] if has_rev and has_cost else ["Missing reviewed inputs"],
        "financial_review_status": f["financial_review_status"],
        "financial_review_blockers": f["financial_review_blockers"],
        "review_href": "/trips/" + identifier,
        "advance": {"unreconciled_capture_count": 0, "outstanding": "0.00", "conflicts": []},
    }


def test_four_trip_golden_weighted_contribution():
    trips = [
        row(),
        row("18000.00", "12000.00", "B"),
        row("14000.00", "15200.00", "C"),
        row("20000.00", "3200.00", "D"),
    ]
    assert [t["contribution"] for t in trips] == ["12150.00", "6000.00", "-1200.00", "16800.00"]
    assert [t["margin_percent"] for t in trips] == ["55.23", "33.33", "-8.57", "84.00"]
    s = aggregate(trips)
    assert (s["revenue"], s["direct_cost"], s["contribution"], s["weighted_margin_percent"]) == (
        "74000.00",
        "40250.00",
        "33750.00",
        "45.61",
    )
    assert (s["positive_count"], s["negative_count"], s["final_count"], s["provisional_count"]) == (
        3,
        1,
        0,
        4,
    )
    assert s["weighted_margin_percent"] != money(
        sum(Decimal(t["margin_percent"]) for t in trips) / 4
    )


def test_money_precision_and_explicit_rounding():
    with localcontext() as c:
        c.rounding = ROUND_DOWN
        assert money(Decimal("1.005")) == "1.01"
        assert money(Decimal("-1.005")) == "-1.01"
        assert money(Decimal("0.30") - Decimal("0.10")) == "0.20"
        assert percent(Decimal("24150"), Decimal("40250")) == "60.00"
    assert percent(Decimal("-100"), Decimal("0")) is None


def test_missing_records_are_not_break_even_or_confirmed_zero_cost():
    s = aggregate(
        [
            row("0.00", "0.00", "missing", False, False),
            row("200.00", "0.00", "no-cost", True, False),
        ]
    )
    assert s["insufficient_data_count"] == 2
    assert s["zero_count"] == s["positive_count"] == 0


def test_advance_is_excluded_by_original_financial_engine():
    def part(cat, value):
        return {
            "category": cat,
            "reviewed_total": Decimal(value),
            "submitted_total": Decimal(value),
            "reviewed_count": 1,
            "unreviewed_count": 0,
        }

    f = calculate(
        {"id": "D", "current_status": "DISPATCHED"},
        [part("BASE_TRIP_CHARGE", "20000")],
        [part("FUEL", "2500"), part("TOLL", "700"), part("DRIVER_CASH_ADVANCE", "5000")],
    )
    assert (
        f["direct_cost"]["effective_total"],
        f["contribution_amount"],
        f["excluded_cash_advances"],
    ) == ("3200.00", "16800.00", "5000.00")


def rules(trips, policy=None, categories=None, changes=None):
    return findings_for(
        trips, categories or [], changes or [], policy or ReportingPolicy(), "2026-09-20T00:00:00Z"
    )


@pytest.mark.parametrize(
    "cost,low,pressure",
    [
        ("85.00", False, True),
        ("85.01", True, True),
        ("70.00", False, False),
        ("70.01", False, True),
        ("101.00", False, True),
    ],
)
def test_exact_rule_thresholds(cost, low, pressure):
    names = {f["rule_id"] for f in rules([row("100.00", cost)])}
    assert ("LOW_CONTRIBUTION_MARGIN" in names) == low
    assert ("DIRECT_COST_PRESSURE" in names) == pressure


def test_missing_revenue_priority_and_unique_findings():
    r = rules([row("0.00", "100.00", "C", False, True)])
    assert r[0]["rule_id"] == "MISSING_REVIEWED_REVENUE"
    assert "NEGATIVE_CONTRIBUTION" in {f["rule_id"] for f in r}
    assert len({f["key"] for f in r}) == len(r)
    assert all(f["href"] and f["comparison_basis"] and f["recommended_action"] for f in r)


def test_cost_concentration_explains_no_fraud_claim():
    result = rules(
        [],
        categories=[
            {"category": "FUEL", "reviewed_total": "24150.00"},
            {"category": "TOLL", "reviewed_total": "16100.00"},
        ],
    )
    assert len(result) == 1
    assert result[0]["supporting_values"]["share_percent"] == "60.00"
    assert "does not establish" in result[0]["explanation"]
    assert not any(f["rule_id"] in ("FUEL_THEFT", "DRIVER_PERFORMANCE") for f in result)


def test_material_change_requires_supported_amount_history():
    t = row()
    no_delta = {"id": "x", "trip_id": "A", "amount_delta": None}
    assert not any(
        f["rule_id"] == "MATERIAL_FINANCIAL_CHANGE" for f in rules([t], changes=[no_delta])
    )
    e = {
        "id": "x",
        "trip_id": "A",
        "amount_delta": "1000.00",
        "old_value": "1000.00",
        "new_value": "2000.00",
        "revenue_id": None,
        "created_at": "2026-09-19T00:00:00Z",
    }
    f = next(f for f in rules([t], changes=[e]) if f["rule_id"] == "MATERIAL_FINANCIAL_CHANGE")
    assert (
        f["source_event_id"] == "x"
        and f["supporting_values"]["contribution_direction_if_reviewed"] == "-1000.00"
    )


def test_advance_capture_does_not_invent_outstanding():
    t = row()
    t["advance"]["unreconciled_capture_count"] = 1
    f = next(f for f in rules([t]) if f["rule_id"] == "ADVANCE_ATTENTION")
    assert f["supporting_values"]["outstanding"] == "0.00"
    assert "not confirmed issuance" in f["explanation"]


def test_manila_inclusive_exclusive_boundaries_and_future_fixture():
    a, b, start, end = ReportFilters(date_from="2026-09-21", date_to="2026-09-24").bounds(
        "Asia/Manila"
    )
    assert str(a) == "2026-09-21" and str(b) == "2026-09-24"
    assert start == datetime(2026, 9, 20, 16, tzinfo=timezone.utc)
    assert end == datetime(2026, 9, 24, 16, tzinfo=timezone.utc)
    assert start < datetime(2026, 9, 24, 15, 59, tzinfo=timezone.utc) < end


def test_dst_boundaries_use_two_local_midnights():
    *_, start, end = ReportFilters(date_from="2026-03-08", date_to="2026-03-08").bounds(
        "America/New_York"
    )
    assert (end - start).total_seconds() == 23 * 3600


@pytest.mark.parametrize(
    "args",
    [
        {"date_from": "2026-09-24", "date_to": "2026-09-21"},
        {"lifecycle": "x' OR 1=1"},
        {"customer_id": "bad"},
        {"limit": 101},
        {"offset": -1},
        {"financial_status": "APPROVED"},
        {"dataset": "all"},
        {"extra": "x"},
    ],
)
def test_invalid_filters(args):
    with pytest.raises(ValidationError):
        ReportFilters(**args)


@pytest.mark.parametrize("value", [15.1, True, "1e2", "NaN", "-1", "100.01", "15.001", " 15"])
def test_policy_rejects_inexact_or_out_of_bounds(value):
    with pytest.raises(ValidationError):
        ReportingPolicy(low_margin_percent=value)


@pytest.mark.parametrize(
    "role,allowed",
    [
        ("OWNER", True),
        ("ADMIN", True),
        ("MANAGER", True),
        ("ACCOUNTING", True),
        ("DRIVER", False),
        ("DISPATCHER", False),
        ("MAINTENANCE", False),
    ],
)
def test_actual_permission_sets(role, allowed):
    assert (set(REQUIRED_ACCESS) <= resolve_permissions(role)) == allowed


@pytest.mark.parametrize("denied", REQUIRED_ACCESS)
def test_restrictive_override_requires_complete_financial_visibility(denied):
    assert not set(REQUIRED_ACCESS) <= resolve_permissions("OWNER", {"deny": [denied]})


@pytest.mark.parametrize(
    "value",
    [
        "=1+2",
        "+SUM(1)",
        "-CMD()",
        "@SUM(1)",
        "\t=1",
        "\r=1",
        "\n=1",
        "  =1",
        'x";=1,=2',
        "＝1+2",
        "\x00=1",
        "ordinary customer",
    ],
)
def test_csv_text_cells_and_delimiter_quotes(value):
    stream = io.StringIO()
    csv.writer(stream, quoting=csv.QUOTE_ALL).writerow([cell(value), cell("next")])
    fields = next(csv.reader(io.StringIO(stream.getvalue())))
    assert len(fields) == 2 and fields[0].startswith("'") and fields[1] == "'next"
    assert not any(ord(c) < 32 for c in fields[0])


def test_negative_money_is_numeric_not_text_or_formula():
    assert cell(Numeric("-1200.00")) == "-1200.00"
    with pytest.raises(ValueError):
        Numeric("-1200+SUM(A1)")


def test_print_export_escapes_untrusted_scope_and_empty_reports():
    r = {
        "scope": {
            "organization_name": "<script>alert(1)</script>",
            "organization_id": "x",
            "date_from": "2026-09-21",
            "date_to": "2026-09-24",
            "date_basis": "Scheduled pickup date",
            "timezone": "Asia/Manila",
            "lifecycle": "ALL",
            "financial_status": "ALL",
            "customer_id": None,
            "vehicle_id": None,
            "trip_id": None,
            "record_count": 0,
            "calculated_at": "2026-09-20T00:00:00Z",
            "rule_version": "v1",
            "fingerprint": "hash",
            "synthetic": True,
            "qualification": QUALIFICATION,
            "warnings": [],
        },
        "summary": aggregate([]),
        "lifecycle_totals": [],
        "advance_summary": {},
        "trips": [],
        "customers": [],
        "categories": [],
        "findings": [],
        "captures": [],
        "advances": [],
    }
    for name in (
        "executive-contribution",
        "trip-contribution",
        "customer-contribution",
        "direct-costs",
        "financial-exceptions",
        "cash-advances",
    ):
        if name == "direct-costs":
            r["advance_summary"] = {"captured_amount": "0.00", "issued": "0.00"}
        output = export_report(name, r, "print")
        assert "<script>" not in output and "&lt;script&gt;" in output
        assert "SYNTHETIC VALIDATION DATA" in output and "not net profit" in output
        assert "Scheduled pickup date" in output and "newly calculated" in output
