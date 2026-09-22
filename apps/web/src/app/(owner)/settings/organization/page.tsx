import { PageHeader } from "@fleetpilot/ui";
import { getIdentity } from "@/lib/server";
import { SettingsNav } from "@/components/navigation";
import { OrganizationForm } from "@/components/settings";
import { isClientDemo } from "@fleetpilot/auth";
import { redirect } from "next/navigation";
export default async function OrganizationSettings() {
  const identity = await getIdentity("organization.read");
  if (isClientDemo(identity)) redirect("/access-denied");
  return (
    <>
      <PageHeader
        title="Settings"
        description="The details that keep your workspace running."
      />
      <SettingsNav identity={identity} />
      <OrganizationForm identity={identity} />
    </>
  );
}
