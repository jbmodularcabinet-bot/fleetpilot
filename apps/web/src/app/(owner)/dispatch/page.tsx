import { getIdentity } from "@/lib/server";
import { DispatchBoard } from "@/components/trips";
export default async function Page() {
  const identity = await getIdentity("dispatch.read");
  return <DispatchBoard identity={identity} />;
}
