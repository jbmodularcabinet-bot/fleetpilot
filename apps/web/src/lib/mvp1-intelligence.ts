import { can } from "@fleetpilot/auth";
import type { Identity, Permission } from "@fleetpilot/types";

export type Breakdown = {
  category: string;
  submitted_total: string;
  reviewed_total: string;
  unreviewed_count?: number;
  reviewed_count?: number;
};

export type ContributionRow = {
  trip_id: string;
  trip_number: string;
  customer_name: string;
  current_status: string;
  scheduled_pickup_at: string;
  basis: string;
  currency: string;
  status: string;
  financial_review_status: string;
  financial_review_blockers?: string[];
  unreviewed_count: number;
  revenue: {
    effective_total: string;
    submitted_total: string;
    breakdown: Breakdown[];
  };
  direct_cost: {
    effective_total: string;
    submitted_total: string;
    breakdown: Breakdown[];
  };
  contribution_amount: string;
  contribution_margin_percent: string | null;
  excluded_cash_advances: string;
  calculated_at?: string;
};
export type CashAdvance = {
  id: string;
  amount_issued: string;
  applied: string;
  returned: string;
  outstanding: string;
  status: string;
  issued_at: string;
  trip_id?: string;
  trip_number?: string;
};

export type AuditEvent = {
  id: string;
  action: string;
  entity_type: string;
  entity_id: string;
  actor_user_id: string;
  created_at: string;
  before?: unknown;
  after?: unknown;
};

export type ExceptionTone = "critical" | "warning" | "active";

export type IntelligenceException = {
  key: string;
  tone: ExceptionTone;
  kind: string;
  title: string;
  detail: string;
  recommendation: string;
  trip: ContributionRow;
};
const INSIGHT_PERMISSIONS: Permission[] = [
  "trip_financials.read",
  "trip_profitability.read",
  "expenses.read",
  "cash_advance.read",
  "financial_review.read",
];

export function hasInsightAccess(identity: Identity): boolean {
  return INSIGHT_PERMISSIONS.every((permission) => can(identity, permission));
}

export function moneyCents(value: string): bigint {
  const normalized = String(value ?? "0").trim();
  const match = normalized.match(/^(-?)(\d+)(?:\.(\d{0,2}))?$/);
  if (!match) throw new Error(`Invalid money value: ${value}`);
  const [, sign, whole, fraction = ""] = match;
  const cents = BigInt(whole) * 100n + BigInt((fraction + "00").slice(0, 2));
  return sign === "-" ? -cents : cents;
}

export function moneyString(value: bigint): string {
  const sign = value < 0n ? "-" : "";
  const absolute = value < 0n ? -value : value;
  const whole = absolute / 100n;
  const cents = String(absolute % 100n).padStart(2, "0");
  return `${sign}${whole}.${cents}`;
}
export function percentString(
  numerator: bigint,
  denominator: bigint,
): string | null {
  if (denominator === 0n) return null;
  const scaled = numerator * 10000n;
  const adjustment = scaled >= 0n ? denominator / 2n : -(denominator / 2n);
  const hundredths = (scaled + adjustment) / denominator;
  const sign = hundredths < 0n ? "-" : "";
  const absolute = hundredths < 0n ? -hundredths : hundredths;
  return `${sign}${absolute / 100n}.${String(absolute % 100n).padStart(2, "0")}`;
}

export function summarizeContribution(rows: ContributionRow[]) {
  let revenue = 0n;
  let directCost = 0n;
  let contribution = 0n;
  let unreviewed = 0;
  let lossTrips = 0;
  let needsReview = 0;
  for (const row of rows) {
    revenue += moneyCents(row.revenue.effective_total);
    directCost += moneyCents(row.direct_cost.effective_total);
    const rowContribution = moneyCents(row.contribution_amount);
    contribution += rowContribution;
    unreviewed += row.unreviewed_count;
    if (rowContribution < 0n) lossTrips += 1;
    if (row.current_status === "COMPLETED" && row.status !== "FINAL")
      needsReview += 1;
  }
  return {
    revenue: moneyString(revenue),
    directCost: moneyString(directCost),
    contribution: moneyString(contribution),
    weightedMargin: percentString(contribution, revenue),
    lossTrips,
    needsReview,
    unreviewed,
    tripCount: rows.length,
  };
}
export type CustomerContribution = {
  customer: string;
  trips: number;
  revenue: string;
  directCost: string;
  contribution: string;
  margin: string | null;
};

export function groupCustomers(
  rows: ContributionRow[],
): CustomerContribution[] {
  const grouped = new Map<
    string,
    { trips: number; revenue: bigint; cost: bigint; contribution: bigint }
  >();
  for (const row of rows) {
    const current = grouped.get(row.customer_name) ?? {
      trips: 0,
      revenue: 0n,
      cost: 0n,
      contribution: 0n,
    };
    current.trips += 1;
    current.revenue += moneyCents(row.revenue.effective_total);
    current.cost += moneyCents(row.direct_cost.effective_total);
    current.contribution += moneyCents(row.contribution_amount);
    grouped.set(row.customer_name, current);
  }
  return [...grouped.entries()]
    .map(([customer, value]) => ({
      customer,
      trips: value.trips,
      revenue: moneyString(value.revenue),
      directCost: moneyString(value.cost),
      contribution: moneyString(value.contribution),
      margin: percentString(value.contribution, value.revenue),
    }))
    .sort((a, b) => {
      const left = moneyCents(a.contribution);
      const right = moneyCents(b.contribution);
      return right > left ? 1 : right < left ? -1 : 0;
    });
}

export type CostCategory = {
  category: string;
  reviewedTotal: string;
  share: string | null;
};

export function groupDirectCosts(rows: ContributionRow[]): CostCategory[] {
  const grouped = new Map<string, bigint>();
  let total = 0n;
  for (const row of rows) {
    for (const item of row.direct_cost.breakdown) {
      const amount = moneyCents(item.reviewed_total);
      grouped.set(item.category, (grouped.get(item.category) ?? 0n) + amount);
      total += amount;
    }
  }
  return [...grouped.entries()]
    .map(([category, amount]) => ({
      category,
      reviewedTotal: moneyString(amount),
      share: percentString(amount, total),
    }))
    .sort((a, b) => {
      const left = moneyCents(a.reviewedTotal);
      const right = moneyCents(b.reviewedTotal);
      return right > left ? 1 : right < left ? -1 : 0;
    });
}

function addException(
  list: IntelligenceException[],
  row: ContributionRow,
  kind: string,
  tone: ExceptionTone,
  title: string,
  detail: string,
  recommendation: string,
) {
  list.push({
    key: `${row.trip_id}:${kind}`,
    tone,
    kind,
    title,
    detail,
    recommendation,
    trip: row,
  });
}
export function buildExceptions(
  rows: ContributionRow[],
): IntelligenceException[] {
  const list: IntelligenceException[] = [];
  for (const row of rows) {
    const revenue = moneyCents(row.revenue.effective_total);
    const cost = moneyCents(row.direct_cost.effective_total);
    const contribution = moneyCents(row.contribution_amount);
    const margin =
      row.contribution_margin_percent === null
        ? null
        : Number(row.contribution_margin_percent);

    if (contribution < 0n) {
      addException(
        list,
        row,
        "LOSS",
        "critical",
        `${row.trip_number} is contribution-negative`,
        `Reviewed contribution is ${row.contribution_amount} PHP on ${row.revenue.effective_total} PHP reviewed revenue.`,
        "Review trip pricing and direct-cost records before the next similar dispatch.",
      );
    } else if (margin !== null && margin < 15) {
      addException(
        list,
        row,
        "LOW_MARGIN",
        "warning",
        `${row.trip_number} is below the 15% contribution watch threshold`,
        `Reviewed contribution margin is ${row.contribution_margin_percent}%.`,
        "Review the rate and dominant direct-cost categories.",
      );
    }

    if (row.unreviewed_count > 0) {
      addException(
        list,
        row,
        "UNREVIEWED",
        "warning",
        `${row.trip_number} has unreviewed financial inputs`,
        `${row.unreviewed_count} revenue or direct-cost record(s) remain outside reviewed effective totals.`,
        "Complete financial review before treating the trip as final.",
      );
    }
    if (revenue === 0n && row.current_status !== "CANCELLED") {
      addException(
        list,
        row,
        "MISSING_REVENUE",
        "active",
        `${row.trip_number} has no reviewed revenue`,
        "The authoritative profitability response currently reports 0.00 PHP reviewed revenue.",
        "Confirm revenue submission and review status.",
      );
    }

    if (
      row.financial_review_status === "NEEDS_ATTENTION" ||
      (row.financial_review_blockers?.length ?? 0) > 0
    ) {
      addException(
        list,
        row,
        "REVIEW_BLOCKER",
        "critical",
        `${row.trip_number} has financial-review blockers`,
        (row.financial_review_blockers ?? []).join(" ") ||
          "The financial review state requires attention.",
        "Open the trip financial review and resolve the recorded blockers.",
      );
    }

    if (cost > 0n) {
      const largest = row.direct_cost.breakdown
        .map((item) => ({
          category: item.category,
          amount: moneyCents(item.reviewed_total),
        }))
        .sort((a, b) => Number(b.amount - a.amount))[0];
      if (largest && largest.amount * 2n >= cost) {
        const share = percentString(largest.amount, cost);
        addException(
          list,
          row,
          "COST_CONCENTRATION",
          "active",
          `${row.trip_number} has concentrated direct cost`,
          `${largest.category} represents ${share ?? "N/A"}% of reviewed direct trip cost.`,
          "Review the underlying category records for rate, quantity, and supporting evidence.",
        );
      }
    }
  }
  const weight = { critical: 0, warning: 1, active: 2 } as const;
  return list.sort((a, b) => weight[a.tone] - weight[b.tone]);
}
export function isFinancialAudit(event: AuditEvent): boolean {
  return /^(trip_revenue|expense|closed_trip_adjustment|cash_advance|financial_review|trip_financial_review)/.test(
    event.action,
  );
}

export function summarizeAdvances(items: CashAdvance[]) {
  let issued = 0n;
  let applied = 0n;
  let returned = 0n;
  let outstanding = 0n;
  let unsettled = 0;
  for (const item of items) {
    issued += moneyCents(item.amount_issued);
    applied += moneyCents(item.applied);
    returned += moneyCents(item.returned);
    outstanding += moneyCents(item.outstanding);
    if (item.status !== "SETTLED" && item.status !== "VOIDED") unsettled += 1;
  }
  return {
    issued: moneyString(issued),
    applied: moneyString(applied),
    returned: moneyString(returned),
    outstanding: moneyString(outstanding),
    unsettled,
    count: items.length,
  };
}
