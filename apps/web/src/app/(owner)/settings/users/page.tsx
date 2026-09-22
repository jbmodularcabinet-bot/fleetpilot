import { PageHeader } from "@fleetpilot/ui";
import { getIdentity } from "@/lib/server";
import { SettingsNav } from "@/components/navigation";
import { MembershipSettings } from "@/components/settings";
import { isClientDemo } from "@fleetpilot/auth";
import { redirect } from "next/navigation";
export default async function UsersSettings() {
  const identity = await getIdentity("organization.read");
  if (isClientDemo(identity)) redirect("/access-denied");
  if (!identity.permissions.includes("users.read")) redirect("/dashboard");
  return (
    <>
      <PageHeader
        title="Settings"
        description="The right access for every person on your team."
      />
      <SettingsNav identity={identity} />
      <MembershipSettings identity={identity} />
    </>
  );
}
