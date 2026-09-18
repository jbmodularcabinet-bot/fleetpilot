import { notFound } from "next/navigation";
import { getIdentity } from "@/lib/server";
import {
  MasterDetail,
  MasterEditor,
  MasterList,
} from "@/components/master-data";
import type { Domain } from "@/lib/master-data";

export async function MasterPage({
  domain,
  segments = [],
  saved,
}: {
  domain: Domain;
  segments?: string[];
  saved?: boolean;
}) {
  const mode =
    segments.length === 0
      ? "list"
      : segments.length === 1 && segments[0] === "new"
        ? "create"
        : segments.length === 1
          ? "detail"
          : segments.length === 2 && segments[1] === "edit"
            ? "update"
            : null;
  if (!mode) notFound();
  if (
    (mode === "detail" || mode === "update") &&
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
      segments[0],
    )
  )
    notFound();
  const identity = await getIdentity(
    `${domain}.${mode === "create" ? "create" : mode === "update" ? "update" : "read"}`,
  );
  return mode === "list" ? (
    <MasterList domain={domain} identity={identity} />
  ) : mode === "detail" ? (
    <MasterDetail
      domain={domain}
      identity={identity}
      id={segments[0]}
      saved={saved}
    />
  ) : (
    <MasterEditor
      domain={domain}
      identity={identity}
      id={mode === "update" ? segments[0] : undefined}
    />
  );
}
