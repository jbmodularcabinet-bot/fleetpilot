import { getIdentity } from "@/lib/server";
import { WorkOrderDetail } from "@/components/maintenance";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const identity = await getIdentity("maintenance.read");
  const { id } = await params;
  return <WorkOrderDetail identity={identity} id={id} />;
}
