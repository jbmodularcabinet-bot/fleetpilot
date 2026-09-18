import { getIdentity } from "@/lib/server";
import { DriverHomeContent } from "@/components/driver-home";
export default async function DriverHome() {
  return <DriverHomeContent identity={await getIdentity("driver_app.view")} />;
}
