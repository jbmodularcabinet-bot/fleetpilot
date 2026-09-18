from enum import StrEnum


class Role(StrEnum):
    OWNER = "OWNER"
    MANAGER = "MANAGER"
    DISPATCHER = "DISPATCHER"
    DRIVER = "DRIVER"
    ACCOUNTING = "ACCOUNTING"
    MAINTENANCE = "MAINTENANCE"
    ADMIN = "ADMIN"


MASTER_PERMISSIONS = frozenset(
    {
        *(
            f"{domain}.{action}"
            for domain in ("customers", "vehicles", "drivers")
            for action in ("read", "create", "update", "deactivate")
        ),
        "vehicles.assign_driver",
        "assignments.read",
        "assignments.manage",
    }
)
TRIP_PERMISSIONS = frozenset(
    {
        *(
            f"trips.{action}"
            for action in (
                "read",
                "create",
                "update",
                "assign",
                "dispatch",
                "transition",
                "cancel",
                "complete",
            )
        ),
        "dispatch.read",
        "dispatch.manage",
    }
)
DRIVER_TRIP_PERMISSIONS = frozenset({"driver_trip.read_own", "driver_trip.transition_own"})
POD_PERMISSIONS = frozenset(
    {
        "pod.read",
        "pod.submit",
        "pod.review",
        "delivery_evidence.read",
        "delivery_evidence.upload",
        "delivery_exception.read",
        "delivery_exception.create",
        "delivery_exception.resolve",
    }
)
DRIVER_POD_PERMISSIONS = frozenset(
    {
        "driver_pod.read_own",
        "driver_pod.submit_own",
        "driver_evidence.read_own",
        "driver_evidence.upload_own",
        "driver_exception.create_own",
    }
)
EXPENSE_PERMISSIONS = frozenset(
    {
        *(f"expenses.{a}" for a in ("read", "create", "review", "correct", "void")),
        "fuel.read",
        "fuel.create",
        "fuel.review",
        "evidence.expense.read",
        "evidence.expense.upload",
    }
)
DRIVER_EXPENSE_PERMISSIONS = frozenset({"driver_expense.read_own", "driver_expense.create_own"})
ADJUSTMENT_PERMISSIONS = frozenset(
    f"closed_trip_adjustments.{a}" for a in ("read", "create", "reverse")
)
MAINTENANCE_PERMISSIONS = frozenset(
    {
        "maintenance.read",
        "maintenance.schedule.create",
        "maintenance.schedule.update",
        "maintenance.work_order.create",
        "maintenance.work_order.update",
        "maintenance.work_order.complete",
        "maintenance.cost.manage",
        "maintenance.evidence.read",
        "maintenance.evidence.upload",
        "defects.read",
        "defects.review",
        "defects.create_work_order",
    }
)
DRIVER_DEFECT_PERMISSIONS = frozenset({"driver_defect.create_own", "driver_defect.read_own"})
FINANCIAL_PERMISSIONS = frozenset(
    {
        "trip_financials.read",
        "trip_profitability.read",
        "trip_revenue.create",
        "trip_revenue.review",
        "trip_revenue.void",
    }
)
GOVERNANCE_PERMISSIONS = frozenset(
    {
        "cash_advance.read",
        "cash_advance.create",
        "cash_advance.settle",
        "cash_advance.void",
        "financial_review.read",
    }
)
REVIEW_PERMISSIONS = frozenset({"financial_review.approve"})
ALL_PERMISSIONS = (
    GOVERNANCE_PERMISSIONS
    | REVIEW_PERMISSIONS
    | FINANCIAL_PERMISSIONS
    | MAINTENANCE_PERMISSIONS
    | DRIVER_DEFECT_PERMISSIONS
    | ADJUSTMENT_PERMISSIONS
    | EXPENSE_PERMISSIONS
    | DRIVER_EXPENSE_PERMISSIONS
    | MASTER_PERMISSIONS
    | POD_PERMISSIONS
    | DRIVER_POD_PERMISSIONS
    | TRIP_PERMISSIONS
    | DRIVER_TRIP_PERMISSIONS
    | frozenset(
        {
            "organization.read",
            "organization.manage",
            "users.read",
            "users.manage",
            "audit.read",
            "owner_dashboard.view",
            "driver_app.view",
        }
    )
)
ROLE_PERMISSIONS = {
    Role.OWNER: ALL_PERMISSIONS
    - {"driver_app.view"}
    - DRIVER_TRIP_PERMISSIONS
    - DRIVER_POD_PERMISSIONS
    - DRIVER_EXPENSE_PERMISSIONS
    - DRIVER_DEFECT_PERMISSIONS,
    Role.ADMIN: ALL_PERMISSIONS
    - {"driver_app.view"}
    - DRIVER_TRIP_PERMISSIONS
    - DRIVER_POD_PERMISSIONS
    - DRIVER_EXPENSE_PERMISSIONS
    - DRIVER_DEFECT_PERMISSIONS,
    Role.MANAGER: GOVERNANCE_PERMISSIONS
    | FINANCIAL_PERMISSIONS
    | MAINTENANCE_PERMISSIONS
    | EXPENSE_PERMISSIONS
    | MASTER_PERMISSIONS
    | POD_PERMISSIONS
    | TRIP_PERMISSIONS
    | frozenset({"organization.read", "users.read", "audit.read", "owner_dashboard.view"}),
    Role.DRIVER: DRIVER_DEFECT_PERMISSIONS
    | DRIVER_EXPENSE_PERMISSIONS
    | DRIVER_TRIP_PERMISSIONS
    | DRIVER_POD_PERMISSIONS
    | frozenset({"organization.read", "driver_app.view"}),
    Role.DISPATCHER: (EXPENSE_PERMISSIONS - {"expenses.correct", "expenses.void"})
    | TRIP_PERMISSIONS
    | POD_PERMISSIONS
    | frozenset(
        {"organization.read", "customers.read", "vehicles.read", "drivers.read", "assignments.read"}
    ),
    Role.ACCOUNTING: GOVERNANCE_PERMISSIONS
    | FINANCIAL_PERMISSIONS
    | EXPENSE_PERMISSIONS
    | frozenset({"organization.read", "customers.read"}),
    Role.MAINTENANCE: MAINTENANCE_PERMISSIONS | frozenset({"organization.read", "vehicles.read"}),
}


def resolve_permissions(role: str, overrides: dict | None = None) -> frozenset[str]:
    try:
        granted = ROLE_PERMISSIONS[Role(role)]
    except ValueError:
        return frozenset()
    # Batch 2 permits restrictive overrides only, never silent privilege expansion.
    denied = set((overrides or {}).get("deny", []))
    return granted - denied
