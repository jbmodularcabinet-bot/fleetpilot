import { describe, expect, it } from "vitest";
import type { Identity, Permission } from "@fleetpilot/types";
import {
  buildExceptions,
  groupCustomers,
  groupDirectCosts,
  hasInsightAccess,
  summarizeAdvances,
  summarizeContribution,
  type ContributionRow,
} from "@/lib/mvp1-intelligence";

function identity(permissions: Permission[]): Identity {
  return { permissions } as Identity;
}

function row(
  overrides: Partial<ContributionRow> &
    Pick<ContributionRow, "trip_id" | "trip_number">,
): ContributionRow {
  const { trip_id, trip_number, ...rest } = overrides;
  return {
    trip_id,
    trip_number,
    customer_name: "Northstar Foods",
    current_status: "COMPLETED",
    scheduled_pickup_at: "2026-09-20T08:00:00+08:00",
    basis: "REVIEWED_EFFECTIVE",
    currency: "PHP",
    status: "FINAL",
    financial_review_status: "APPROVED",
    financial_review_blockers: [],
    unreviewed_count: 0,
    revenue: {
      effective_total: "40000.00",
      submitted_total: "40000.00",
      breakdown: [
        {
          category: "BASE_TRIP_CHARGE",
          submitted_total: "40000.00",
          reviewed_total: "40000.00",
        },
      ],
    },
    direct_cost: {
      effective_total: "20000.00",
      submitted_total: "20000.00",
      breakdown: [
        {
          category: "FUEL",
          submitted_total: "12000.00",
          reviewed_total: "12000.00",
        },
        {
          category: "TOLL",
          submitted_total: "8000.00",
          reviewed_total: "8000.00",
        },
      ],
    },
    contribution_amount: "20000.00",
    contribution_margin_percent: "50.00",
    excluded_cash_advances: "0.00",
    ...rest,
  };
}

describe("MVP1 intelligence presentation model", () => {
  it("aggregates authoritative contribution values exactly without recomputing trip financials", () => {
    const rows = [
      row({ trip_id: "1", trip_number: "FP-001" }),
      row({
        trip_id: "2",
        trip_number: "FP-002",
        customer_name: "Harbor Retail",
        revenue: {
          effective_total: "34000.00",
          submitted_total: "34000.00",
          breakdown: [
            {
              category: "BASE_TRIP_CHARGE",
              submitted_total: "34000.00",
              reviewed_total: "34000.00",
            },
          ],
        },
        direct_cost: {
          effective_total: "20250.00",
          submitted_total: "20250.00",
          breakdown: [
            {
              category: "FUEL",
              submitted_total: "12150.00",
              reviewed_total: "12150.00",
            },
            {
              category: "TOLL",
              submitted_total: "8100.00",
              reviewed_total: "8100.00",
            },
          ],
        },
        contribution_amount: "13750.00",
        contribution_margin_percent: "40.44",
      }),
    ];
    expect(summarizeContribution(rows)).toMatchObject({
      revenue: "74000.00",
      directCost: "40250.00",
      contribution: "33750.00",
      weightedMargin: "45.61",
      lossTrips: 0,
      needsReview: 0,
    });
    expect(groupDirectCosts(rows)[0]).toMatchObject({
      category: "FUEL",
      reviewedTotal: "24150.00",
      share: "60.00",
    });
    expect(groupCustomers(rows).map((item) => item.customer)).toEqual([
      "Northstar Foods",
      "Harbor Retail",
    ]);
  });

  it("uses explainable locked exception rules", () => {
    const exceptions = buildExceptions([
      row({
        trip_id: "3",
        trip_number: "FP-003",
        status: "PROVISIONAL",
        financial_review_status: "NEEDS_ATTENTION",
        financial_review_blockers: ["Cash advance is outstanding."],
        unreviewed_count: 1,
        revenue: {
          effective_total: "10000.00",
          submitted_total: "11000.00",
          breakdown: [
            {
              category: "BASE_TRIP_CHARGE",
              submitted_total: "11000.00",
              reviewed_total: "10000.00",
            },
          ],
        },
        direct_cost: {
          effective_total: "12000.00",
          submitted_total: "12000.00",
          breakdown: [
            {
              category: "FUEL",
              submitted_total: "9000.00",
              reviewed_total: "9000.00",
            },
            {
              category: "TOLL",
              submitted_total: "3000.00",
              reviewed_total: "3000.00",
            },
          ],
        },
        contribution_amount: "-2000.00",
        contribution_margin_percent: "-20.00",
      }),
    ]);
    expect(exceptions.map((item) => item.kind)).toEqual(
      expect.arrayContaining([
        "LOSS",
        "UNREVIEWED",
        "REVIEW_BLOCKER",
        "COST_CONCENTRATION",
      ]),
    );
  });
  it("does not broaden financial permissions", () => {
    const required: Permission[] = [
      "trip_financials.read",
      "trip_profitability.read",
      "expenses.read",
      "cash_advance.read",
      "financial_review.read",
    ];
    expect(hasInsightAccess(identity(required))).toBe(true);
    expect(hasInsightAccess(identity(required.slice(0, 4)))).toBe(false);
  });

  it("keeps cash advances separate from trip cost while summarizing settlement", () => {
    expect(
      summarizeAdvances([
        {
          id: "a1",
          amount_issued: "5000.00",
          applied: "3000.00",
          returned: "1000.00",
          outstanding: "1000.00",
          status: "PARTIALLY_SETTLED",
          issued_at: "2026-09-20T08:00:00+08:00",
        },
      ]),
    ).toMatchObject({
      issued: "5000.00",
      applied: "3000.00",
      returned: "1000.00",
      outstanding: "1000.00",
      unsettled: 1,
    });
  });
});
