import { getIdentity } from "@/lib/server";
import { TripDetail } from "@/components/trips";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const identity = await getIdentity("driver_trip.read_own");
  return <TripDetail id={(await params).id} identity={identity} own />;
}
