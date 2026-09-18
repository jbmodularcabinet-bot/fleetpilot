import "server-only";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import type { Identity, Permission } from "@fleetpilot/types";
import { can, homeFor } from "@fleetpilot/auth";

export async function getIdentity(permission?: Permission): Promise<Identity> {
  const cookieStore = await cookies();
  if (!cookieStore.has("fp_session")) redirect("/login");
  const response = await fetch(
    `${process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000"}/api/v1/me`,
    { headers: { cookie: cookieStore.toString() }, cache: "no-store" },
  );
  if (response.status === 401) redirect("/login?expired=1");
  if (response.status === 403) redirect("/access-denied");
  if (!response.ok)
    throw new Error("Your workspace is temporarily unavailable. Please retry.");
  const identity: Identity = await response.json();
  if (permission && !can(identity, permission)) redirect(homeFor(identity));
  return identity;
}
