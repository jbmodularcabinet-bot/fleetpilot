import { PageHeader } from "@fleetpilot/ui";
import { getIdentity } from "@/lib/server";
import { SettingsNav } from "@/components/navigation";
import { MembershipSettings } from "@/components/settings";
export default async function UsersSettings() {
  const identity = await getIdentity("users.read");
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
