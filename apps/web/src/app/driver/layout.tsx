import {
  OfflineStatus,
  DriverLocalBoundary,
} from "@/components/offline-status";
import { getIdentity } from "@/lib/server";
import { MobileBottomNav } from "@/components/navigation";
export default async function DriverLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const identity = await getIdentity("driver_app.view");
  return (
    <div className="driver-surround">
      <div className="driver-app">
        <main id="main">
          <DriverLocalBoundary>
            <OfflineStatus identity={identity} />
            {children}
          </DriverLocalBoundary>
        </main>
        <MobileBottomNav />
      </div>
    </div>
  );
}
