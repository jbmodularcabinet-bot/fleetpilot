import { getIdentity } from "@/lib/server";
import { Sidebar, TopNav } from "@/components/navigation";
import { redirect } from "next/navigation";
import { can } from "@fleetpilot/auth";
export default async function OwnerLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const identity = await getIdentity("organization.read");
  if (can(identity, "driver_app.view")) redirect("/driver");
  return (
    <div className="desktop-app">
      <Sidebar identity={identity} />
      <div className="desktop-main">
        <TopNav identity={identity} />
        <main id="main" className="page-content">
          {children}
        </main>
        <footer className="app-footer">
          <span>
            FleetPilot{" "}
            <span className="muted">· Run the fleet. Not the chaos.</span>
          </span>
          <span className="muted">Foundation workspace</span>
        </footer>
      </div>
    </div>
  );
}
