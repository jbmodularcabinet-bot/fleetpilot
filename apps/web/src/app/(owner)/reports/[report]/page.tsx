import { reportingEntryFilters } from "@/lib/reporting-server";
import { notFound } from "next/navigation";
import { getIdentity } from "@/lib/server";
import { ReportingWorkspace } from "@/components/mvp1-intelligence";
import { FILTER_KEYS, REPORTS, type ReportName } from "@/lib/reporting";
export const dynamic = "force-dynamic";
export default async function Report({
  params,
  searchParams,
}: {
  params: Promise<{ report: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const identity = await getIdentity("organization.read");
  const { report } = await params;
  if (!REPORTS.some(([key]) => key === report)) notFound();
  const search = await searchParams;
  const filters: Record<string, string> = {};
  FILTER_KEYS.forEach((key) => {
    if (typeof search[key] === "string") filters[key] = search[key] as string;
  });
  const entryFilters = await reportingEntryFilters(identity, filters);
  return (
    <ReportingWorkspace
      key={identity.organization.id + report + JSON.stringify(entryFilters)}
      identity={identity}
      reportName={report as ReportName}
      initialFilters={entryFilters}
    />
  );
}
