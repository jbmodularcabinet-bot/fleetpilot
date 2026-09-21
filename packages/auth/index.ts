import type { Identity, Permission } from "@fleetpilot/types";
// Display helpers only. FastAPI is the authorization authority.
export function can(identity: Identity, permission: Permission): boolean {
  return identity.permissions.includes(permission);
}
export function isClientDemo(identity: Identity): boolean {
  return identity.membership.access_profile === "CLIENT_DEMO_READONLY";
}
export function homeFor(identity: Identity): string {
  if (can(identity, "owner_dashboard.view")) return "/dashboard";
  if (can(identity, "driver_app.view")) return "/driver";
  if (can(identity, "dispatch.read")) return "/dispatch";
  return "/settings/organization";
}
