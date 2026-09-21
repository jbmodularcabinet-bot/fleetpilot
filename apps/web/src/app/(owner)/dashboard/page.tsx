import { CalendarDays } from "lucide-react";
import { PageHeader, StatusBadge } from "@fleetpilot/ui";
import { getIdentity } from "@/lib/server";
import { Mvp1Dashboard } from "@/components/mvp1-intelligence";

export default async function Dashboard() {
  const identity = await getIdentity("owner_dashboard.view");
  const date = new Intl.DateTimeFormat("en", {
    timeZone: identity.organization.timezone,
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date());

  return (
    <>
      <PageHeader
        title="Owner Dashboard"
        description="Reviewed contribution, financial exceptions, and decision support from authorized fleet records."
      >
        <span className="date-chip">
          <CalendarDays size={16} />
          {date}
        </span>
      </PageHeader>
      <div className="welcome-strip">
        <div>
          <span className="welcome-dot" />
          <strong>Welcome, {identity.user.name.split(" ")[0]}.</strong>
          <span>
            Review what needs attention before opening the underlying trip.
          </span>
        </div>{" "}
        <StatusBadge
          tone={
            identity.organization.slug === "demo-logistics"
              ? "active"
              : "positive"
          }
        >
          {identity.organization.slug === "demo-logistics"
            ? "Demo workspace"
            : "Owner command center"}
        </StatusBadge>
      </div>
      <Mvp1Dashboard identity={identity} />
    </>
  );
}
