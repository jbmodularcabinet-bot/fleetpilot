import { Mvp1Intelligence } from "@/components/mvp1-intelligence";
import { getIdentity } from "@/lib/server";

export default async function IntelligencePage() {
  const identity = await getIdentity("trip_financials.read");
  return <Mvp1Intelligence identity={identity} />;
}
