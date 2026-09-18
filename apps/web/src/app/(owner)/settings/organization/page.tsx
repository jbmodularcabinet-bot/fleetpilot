import { PageHeader } from "@fleetpilot/ui";
import { getIdentity } from "@/lib/server";
import { SettingsNav } from "@/components/navigation";
import { OrganizationForm } from "@/components/settings";
export default async function OrganizationSettings() {
  const identity = await getIdentity("organization.read");
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
