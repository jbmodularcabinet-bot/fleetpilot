import { MasterPage } from "@/components/master-page";
export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ segments?: string[] }>;
  searchParams: Promise<{ saved?: string }>;
}) {
  return (
    <MasterPage
      domain="customers"
      segments={(await params).segments}
      saved={(await searchParams).saved === "1"}
    />
  );
}
