import { getIdentity } from "@/lib/server";
import { ReportingWorkspace } from "@/components/mvp1-intelligence";
import { FILTER_KEYS } from "@/lib/reporting";
export const dynamic = "force-dynamic";
export default async function Intelligence({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const identity = await getIdentity("organization.read");
  const params = await searchParams;
  const filters: Record<string, string> = {};
  FILTER_KEYS.forEach((key) => {
    if (typeof params[key] === "string") filters[key] = params[key] as string;
  });
  return (
    <ReportingWorkspace
      key={identity.organization.id + JSON.stringify(filters)}
      identity={identity}
      mode="intelligence"
      initialFilters={filters}
    />
  );
}
