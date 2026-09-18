import { notFound } from "next/navigation";
import { MasterPage } from "@/components/master-page";
export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ domain: string; segments?: string[] }>;
  searchParams: Promise<{ saved?: string }>;
}) {
  const { domain, segments } = await params;
  if (domain !== "vehicles" && domain !== "drivers") notFound();
  return (
    <MasterPage
      domain={domain}
      segments={segments}
      saved={(await searchParams).saved === "1"}
    />
  );
}
