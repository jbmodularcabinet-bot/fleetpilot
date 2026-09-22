"""Restrictive, deny-only access profile for temporary client demonstrations."""

from .permissions import ROLE_PERMISSIONS, Role

CLIENT_DEMO_ACCESS_PROFILE = "CLIENT_DEMO_READONLY"
CLIENT_DEMO_EMAIL = "client.demo@fleetpilot.ph"
CLIENT_DEMO_ROLE = Role.MANAGER

CLIENT_DEMO_ALLOWED_PERMISSIONS = frozenset(
    {
        "organization.read",
        "owner_dashboard.view",
        "trips.read",
        "trip_financials.read",
        "trip_profitability.read",
        "expenses.read",
        "fuel.read",
        "cash_advance.read",
        "financial_review.read",
    }
)


def client_demo_overrides() -> dict[str, object]:
    """Return restrictive overrides only; this can never expand the base Manager role."""
    base = ROLE_PERMISSIONS[CLIENT_DEMO_ROLE]
    if not CLIENT_DEMO_ALLOWED_PERMISSIONS <= base:
        raise RuntimeError("Client-demo permissions exceed the Manager base role")
    return {
        "profile": CLIENT_DEMO_ACCESS_PROFILE,
        "deny": sorted(base - CLIENT_DEMO_ALLOWED_PERMISSIONS),
    }


def is_client_demo_membership(permissions_json: dict | None) -> bool:
    return (permissions_json or {}).get("profile") == CLIENT_DEMO_ACCESS_PROFILE
