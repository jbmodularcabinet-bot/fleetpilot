import { notFound } from "next/navigation";
import { Mvp1Report, type ReportKey } from "@/components/mvp1-intelligence";
import { getIdentity } from "@/lib/server";

const REPORT_KEYS = [
  "executive-contribution",
  "trip-contribution",
  "customer-contribution",
  "direct-cost-analysis",
  "financial-exceptions",
  "cash-advance-settlement",
] as const satisfies readonly ReportKey[];

export default async function ReportPage({
  params,
}: {
  params: Promise<{ report: string }>;
}) {
  const { report } = await params;
  if (!REPORT_KEYS.includes(report as ReportKey)) notFound();
  const identity = await getIdentity("trip_financials.read");
  return <Mvp1Report identity={identity} report={report as ReportKey} />;
}
