import { MasterPage } from "@/components/master-page";

/**
 * Compatibility route for the public demo's owner-side Drivers navigation.
 *
 * Keep this in the owner route group so the existing OwnerLayout protects it,
 * and delegate to the canonical RBAC/tenant-scoped drivers implementation.
 * The driver's own workspace remains /driver.
 */
export default async function OwnerDriversPage({
  params,
  searchParams,
}: {
  params: Promise<{ segments?: string[] }>;
  searchParams: Promise<{ saved?: string }>;
}) {
  const { segments } = await params;
  return (
    <MasterPage
      domain="drivers"
      segments={segments}
      saved={(await searchParams).saved === "1"}
    />
  );
}
