import { Mvp1ReportsIndex } from "@/components/mvp1-intelligence";
import { getIdentity } from "@/lib/server";

export default async function ReportsPage() {
  const identity = await getIdentity("trip_financials.read");
  return <Mvp1ReportsIndex identity={identity} />;
}
