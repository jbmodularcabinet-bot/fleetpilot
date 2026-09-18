import { notFound, redirect } from "next/navigation";
import { getIdentity } from "@/lib/server";
import { LegacyReviewQueue, ProfitabilityList } from "@/components/financials";
import { TripDetail, TripEditor } from "@/components/trips";
export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ segments?: string[] }>;
  searchParams: Promise<{ saved?: string }>;
}) {
  const { segments = [] } = await params;
  if (segments.length === 1 && segments[0] === "profitability") {
    const identity = await getIdentity("trip_profitability.read");
    return <ProfitabilityList identity={identity} />;
  }
  if (segments.length === 1 && segments[0] === "financial-review") {
    const identity = await getIdentity("financial_review.read");
    return <LegacyReviewQueue identity={identity} />;
  }
  if (!segments.length) redirect("/dispatch");
  if (segments.length === 1 && segments[0] === "new") {
    await getIdentity("trips.create");
    return <TripEditor />;
  }
  if (
    !/^[0-9a-f-]{36}$/i.test(segments[0]) ||
    segments.length > 2 ||
    (segments.length === 2 && segments[1] !== "edit")
  )
    notFound();
  const identity = await getIdentity(
    segments.length === 2 ? "trips.update" : "trips.read",
  );
  return segments.length === 2 ? (
    <TripEditor id={segments[0]} />
  ) : (
    <TripDetail
      id={segments[0]}
      identity={identity}
      saved={(await searchParams).saved === "1"}
    />
  );
}
