import { reportingEntryFilters } from "@/lib/reporting-server";
import { getIdentity } from "@/lib/server";
import { ReportingWorkspace } from "@/components/mvp1-intelligence";
import { FILTER_KEYS } from "@/lib/reporting";
export const dynamic = "force-dynamic";
export default async function Dashboard({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const identity = await getIdentity("owner_dashboard.view");
  const params = await searchParams;
  const filters: Record<string, string> = {};
  FILTER_KEYS.forEach((key) => {
    if (typeof params[key] === "string") filters[key] = params[key] as string;
  });
  const entryFilters = await reportingEntryFilters(identity, filters);
  return (
    <ReportingWorkspace
      key={identity.organization.id + JSON.stringify(entryFilters)}
      identity={identity}
      mode="dashboard"
      initialFilters={entryFilters}
    />
  );
}
