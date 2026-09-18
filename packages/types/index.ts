export type Role =
  | "OWNER"
  | "MANAGER"
  | "DISPATCHER"
  | "DRIVER"
  | "ACCOUNTING"
  | "MAINTENANCE"
  | "ADMIN";
export type Permission =
  | "cash_advance.read"
  | "cash_advance.create"
  | "cash_advance.settle"
  | "cash_advance.void"
  | "financial_review.read"
  | "financial_review.approve"
  | "trip_financials.read"
  | "trip_profitability.read"
  | `trip_revenue.${"create" | "review" | "void"}`
  | "maintenance.read"
  | `maintenance.schedule.${"create" | "update"}`
  | `maintenance.work_order.${"create" | "update" | "complete"}`
  | "maintenance.cost.manage"
  | `maintenance.evidence.${"read" | "upload"}`
  | `defects.${"read" | "review" | "create_work_order"}`
  | `driver_defect.${"read_own" | "create_own"}`
  | `closed_trip_adjustments.${"read" | "create" | "reverse"}`
  | `expenses.${"read" | "create" | "review" | "correct" | "void"}`
  | `fuel.${"read" | "create" | "review"}`
  | `driver_expense.${"read_own" | "create_own"}`
  | `evidence.expense.${"read" | "upload"}`
  | `pod.${"read" | "submit" | "review"}`
  | `delivery_evidence.${"read" | "upload"}`
  | `delivery_exception.${"read" | "create" | "resolve"}`
  | `driver_pod.${"read_own" | "submit_own"}`
  | `driver_evidence.${"read_own" | "upload_own"}`
  | "driver_exception.create_own"
  | `trips.${"read" | "create" | "update" | "assign" | "dispatch" | "transition" | "cancel" | "complete"}`
  | `dispatch.${"read" | "manage"}`
  | `driver_trip.${"read_own" | "transition_own"}`
  | `${"customers" | "vehicles" | "drivers"}.${"read" | "create" | "update" | "deactivate"}`
  | "vehicles.assign_driver"
  | "assignments.read"
  | "assignments.manage"
  | "organization.read"
  | "organization.manage"
  | "users.read"
  | "users.manage"
  | "audit.read"
  | "owner_dashboard.view"
  | "driver_app.view";
export interface Organization {
  id: string;
  name: string;
  legal_name: string | null;
  slug: string;
  timezone: string;
  currency: string;
  country: string;
  status: string;
}
export interface Membership {
  id: string;
  user_id: string;
  name: string;
  email: string;
  role: Role;
  active: boolean;
}
export interface Identity {
  user: { id: string; name: string; email: string };
  organization: Organization;
  membership: { id: string; role: Role };
  permissions: Permission[];
  organizations: Organization[];
}
