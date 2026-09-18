import { getIdentity } from "@/lib/server";
import { DriverTrips } from "@/components/trips";
export default async function Page() {
  await getIdentity("driver_trip.read_own");
  return <DriverTrips />;
}
