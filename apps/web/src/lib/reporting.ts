import { can } from "@fleetpilot/auth";
import type { Identity } from "@fleetpilot/types";
export const REPORTS = [
  [
    "executive-contribution",
    "Executive Contribution",
    "Reviewed portfolio results and review confidence",
  ],
  [
    "trip-contribution",
    "Trip Contribution",
    "Revenue, direct costs and contribution for each trip",
  ],
  [
    "customer-contribution",
    "Customer Contribution",
    "Contribution for the selected period, grouped by customer",
  ],
  [
    "direct-costs",
    "Direct Cost Analysis",
    "Cost categories, concentration and unreviewed inputs",
  ],
  [
    "financial-exceptions",
    "Financial Exceptions",
    "Explainable priorities and source-record review",
  ],
  [
    "cash-advances",
    "Cash Advance & Settlement",
    "Captured records, confirmed issuance and settlement",
  ],
] as const;
export type ReportName = (typeof REPORTS)[number][0];
export const FILTER_KEYS = [
  "date_from",
  "date_to",
  "dataset",
  "customer_id",
  "vehicle_id",
  "lifecycle",
  "financial_status",
  "trip_id",
] as const;
export function canReport(identity: Identity) {
  return (
    [
      "trip_financials.read",
      "trip_profitability.read",
      "expenses.read",
      "fuel.read",
      "cash_advance.read",
      "financial_review.read",
    ] as const
  ).every((p) => can(identity, p));
}
export type Summary = {
  revenue: string;
  direct_cost: string;
  contribution: string;
  weighted_margin_percent: string | null;
  trip_count: number;
  positive_count: number;
  negative_count: number;
  zero_count: number;
  insufficient_data_count: number;
  final_count: number;
  provisional_count: number;
  attention_trip_count: number;
};
export type Category = {
  category: string;
  reviewed_total: string;
  submitted_total: string;
  share_percent: string | null;
  unreviewed_count: number;
  trip_ids: string[];
};
export type Finding = {
  key: string;
  priority: string;
  rule_id: string;
  rule_version: string;
  title: string;
  explanation: string;
  supporting_values: Record<string, unknown>;
  comparison_basis: string;
  qualification: string;
  recommended_action: string;
  href: string;
  trip_id: string | null;
  source_event_id: string | null;
  calculated_at: string;
};
export type Customer = Summary & {
  customer_id: string;
  customer_name: string;
  provisional_contribution: string;
  href: string;
};
export type Trip = {
  id: string;
  version: number;
  trip_number: string;
  customer_id: string;
  customer_name: string;
  vehicle_name: string | null;
  scheduled_pickup_at: string;
  current_status: string;
  status: string;
  revenue: string;
  direct_cost: string;
  contribution: string;
  margin_percent: string | null;
  data_warnings: string[];
  financial_review_status: string;
  financial_review_blockers: string[];
  category_costs: Category[];
  review_href: string;
  contribution_class: string;
  submitted_revenue: string;
  submitted_direct_cost: string;
};
export type Advance = {
  record_kind: "CAPTURE" | "ISSUANCE";
  id: string;
  trip_id: string;
  status: string;
  amount?: string;
  amount_issued?: string;
  applied?: string;
  returned?: string;
  outstanding?: string;
  issuance_id?: string | null;
  source_expense_id?: string | null;
  unreconciled?: boolean;
  issued_at?: string;
};
export type Change = {
  id: string;
  trip_id: string;
  field_name: string;
  old_value: unknown;
  new_value: unknown;
  amount_delta: string | null;
  created_at: string;
};
export type ReportData = {
  report: ReportName;
  title: string;
  scope: {
    organization_id: string;
    organization_name: string;
    date_from: string;
    date_to: string;
    timezone: string;
    date_basis: string;
    lifecycle: string;
    financial_status: string;
    record_count: number;
    calculated_at: string;
    rule_version: string;
    fingerprint: string;
    qualification: string;
    warnings: string[];
    synthetic: boolean;
    demo_available: boolean;
    dataset: string;
    customer_id: string | null;
    vehicle_id: string | null;
    trip_id: string | null;
  };
  summary: Summary;
  owner_brief: string[];
  policy: Record<string, string>;
  advance_summary: Record<string, string | number>;
  category_summary: Category[];
  top_customers: Customer[];
  priority_findings: Finding[];
  finding_count: number;
  recent_changes: Change[];
  history_available: boolean;
  lifecycle_totals: (Summary & { lifecycle: string })[];
  filter_options: {
    customers: { id: string; name: string }[];
    vehicles: { id: string; name: string }[];
  };
  items: (
    | Trip
    | Customer
    | Category
    | Finding
    | Advance
    | (Summary & { lifecycle: string })
  )[];
  total: number;
  limit: number;
  offset: number;
};
export function reportQuery(
  values: Record<string, string>,
  extra: Record<string, string> = {},
) {
  const params = new URLSearchParams();
  FILTER_KEYS.forEach((key) => {
    if (values[key]) params.set(key, values[key]);
  });
  Object.entries(extra).forEach(([key, value]) => {
    if (value) params.set(key, value);
    else params.delete(key);
  });
  return params.toString();
}
export function periodToday(timezone: string) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}
