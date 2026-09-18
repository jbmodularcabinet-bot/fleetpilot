import type { ReactNode } from "react";
import { ArrowRight, CircleHelp, Inbox, LoaderCircle } from "lucide-react";

export function FleetPilotLogo({ compact = false }: { compact?: boolean }) {
  return (
    <div
      className={`brand ${compact ? "brand-small" : ""}`}
      role="img"
      aria-label="FleetPilot — Run the fleet. Not the chaos."
    />
  );
}
export function Card({
  children,
  className = "",
  title,
  action,
}: {
  children: ReactNode;
  className?: string;
  title?: string;
  action?: ReactNode;
}) {
  return (
    <section className={`card ${className}`}>
      {title && (
        <div className="card-heading">
          <h2>{title}</h2>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}
export function StatusBadge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "positive" | "active" | "warning";
}) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}
export function PageHeader({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <header className="page-heading">
      <div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {children}
    </header>
  );
}
export function KpiCard({
  label,
  icon,
  tone = "neutral",
  hint = "Available when connected",
}: {
  label: string;
  icon: ReactNode;
  tone?: "neutral" | "positive" | "active" | "warning" | "critical" | "intelligence";
  hint?: string;
}) {
  return (
    <Card className={`kpi kpi-${tone}`}>
      <div className="kpi-top">
        <span className={`icon-box icon-box-${tone}`}>{icon}</span>
        <span>{label}</span>
      </div>
      <div className="kpi-value" aria-label="No data">
        —
      </div>
      <span className="muted small">{hint}</span>
    </Card>
  );
}
export function EmptyState({
  title,
  description,
  icon,
}: {
  title: string;
  description: string;
  icon?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <span className="empty-icon">{icon ?? <Inbox size={23} />}</span>
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  );
}
export function LoadingState() {
  return (
    <div className="empty-state" role="status">
      <LoaderCircle className="spin" />
      <p>Loading your workspace…</p>
    </div>
  );
}
export function ErrorState({ message }: { message: string }) {
  return (
    <div className="error-state" role="alert">
      <CircleHelp size={18} />
      <span>{message}</span>
    </div>
  );
}
export function DriverPrimaryAction() {
  return (
    <button className="button primary driver-cta" disabled>
      Waiting for your first trip <ArrowRight size={18} />
    </button>
  );
}
