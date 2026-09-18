import {
  Banknote,
  Truck,
  CircleDollarSign,
  ClipboardCheck,
  Activity,
  ArrowUpRight,
  CalendarDays,
  Sparkles,
  ChartNoAxesCombined,
  CircleHelp,
} from "lucide-react";
import {
  Card,
  EmptyState,
  KpiCard,
  PageHeader,
  StatusBadge,
} from "@fleetpilot/ui";
import { getIdentity } from "@/lib/server";
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
        description="One screen. Total clarity. Your fleet’s next chapter starts here."
      >
        <span className="date-chip">
          <CalendarDays size={16} />
          {date}
        </span>
      </PageHeader>
      <div className="welcome-strip">
        <div>
          <span className="welcome-dot" />
          <strong>Welcome, {identity.user.name.split(" ")[0]}.</strong> Your
          workspace is ready.
        </div>
        <StatusBadge>Dashboard summaries unavailable</StatusBadge>
      </div>
      <div className="kpi-grid">
        <KpiCard
          label="Revenue Today"
          icon={<CircleDollarSign />}
          tone="positive"
          hint="Financial reporting is not available yet"
        />
        <KpiCard
          label="Trips In Progress"
          icon={<Truck />}
          tone="active"
          hint="View current trips on the Dispatch Board"
        />
        <KpiCard
          label="Fleet Availability"
          icon={<Activity />}
          tone="neutral"
          hint="Active, idle and unavailable trucks"
        />
        <KpiCard
          label="Collections at Risk"
          icon={<Banknote />}
          tone="warning"
          hint="Overdue and approaching-due receivables"
        />
        <KpiCard
          label="Issues Needing Approval"
          icon={<ClipboardCheck />}
          tone="critical"
          hint="Exceptions requiring owner action"
        />
      </div>
      <div className="dashboard-grid">
        <Card
          title="Revenue & Profitability"
          className="profit-panel"
          action={<CircleHelp size={16} className="muted" />}
        >
          <div className="metric-row">
            {["Revenue", "Gross contribution", "Margin"].map((label) => (
              <div key={label}>
                <strong>—</strong>
                <span>{label}</span>
              </div>
            ))}
          </div>
          <div className="chart-empty">
            <div className="chart-grid" aria-hidden="true" />
            <EmptyState
              icon={<ChartNoAxesCombined size={24} />}
              title="Your performance, in perspective"
              description="Trip-level contribution is available in Trip Detail. Command Center financial aggregation is not available."
            />
          </div>
          <div className="chart-caption">
            <span>REVENUE & CONTRIBUTION</span>
            <span>Aggregation unavailable</span>
          </div>
        </Card>
        <Card
          title="Fleet Status"
          className="fleet-panel"
          action={<span className="small muted">Overview</span>}
        >
          <div className="fleet-summary">
            <div className="empty-donut">
              <strong>—</strong>
              <small>Total trucks</small>
            </div>
            <div className="fleet-legend">
              {["Active", "Idle", "In maintenance", "Out of service"].map(
                (label) => (
                  <div key={label}>
                    <span className="neutral-dot" />
                    <span>{label}</span>
                    <strong>—</strong>
                  </div>
                ),
              )}
            </div>
          </div>
          <div className="panel-note panel-note-action">
            <span>Fleet status becomes live after vehicles and assignments are connected.</span>
            <span className="panel-note-link">Fleet setup ?</span>
          </div>
        </Card>
        <Card
          title="Recent Trips"
          className="trips-panel"
          action={
            <span className="small muted">
              Not connected <ArrowUpRight size={12} />
            </span>
          }
        >
          <div className="trip-columns" aria-hidden="true">
            <span>Trip no.</span>
            <span>Origin → Destination</span>
            <span>Status</span>
          </div>
          <EmptyState
            icon={<Truck size={22} />}
            title="A clear view of every journey"
            description="Open Operations → Dispatch Board to view and manage real trips. Dashboard summaries are not available yet."
          />
        </Card>
      </div>
      <Card className="brief-panel">
        <div className="brief-icon">
          <Sparkles size={23} />
        </div>
        <div>
          <h2>
            AI Brief <span>— Your day at a glance</span>
          </h2>
          <p>
            FleetPilot AI will surface owner-level exceptions, profit signals and
            daily priorities after operational data is connected and validated.
          </p>
          <span className="small muted">
            No generated insights or financial figures are shown until source data is available.
          </span>
        </div>
        <StatusBadge>Not connected</StatusBadge>
      </Card>
    </>
  );
}
