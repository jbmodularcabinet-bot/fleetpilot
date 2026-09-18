import { redirect } from "next/navigation";
import { homeFor } from "@fleetpilot/auth";
import { getIdentity } from "@/lib/server";
export default async function Home() {
  redirect(homeFor(await getIdentity()));
}
