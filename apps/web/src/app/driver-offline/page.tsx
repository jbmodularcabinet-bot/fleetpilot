import { OfflineShell } from "@/components/offline-shell";

// Public boot document contains no authenticated identity, cookies or trip data.
export default function Page() {
  return <OfflineShell />;
}
