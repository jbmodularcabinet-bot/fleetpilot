import { redirect } from "next/navigation";
import { FILTER_KEYS, reportQuery } from "@/lib/reporting";
export default async function Reports({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const search = await searchParams;
  const filters: Record<string, string> = {};
  FILTER_KEYS.forEach((key) => {
    if (typeof search[key] === "string") filters[key] = search[key] as string;
  });
  redirect(`/reports/executive-contribution?${reportQuery(filters)}`);
}
