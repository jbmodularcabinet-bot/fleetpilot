import { getIdentity } from "@/lib/server";
import { MaintenanceList } from "@/components/maintenance";
export default async function Page() {
  const identity = await getIdentity("maintenance.read");
  return <MaintenanceList identity={identity} />;
}
