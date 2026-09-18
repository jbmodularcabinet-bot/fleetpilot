import Link from "next/link";
export default function NotFound() {
  return (
    <main id="main" className="standalone">
      <h1>This page is not available.</h1>
      <p>This feature may be planned for a future FleetPilot batch.</p>
      <Link href="/" className="button primary">
        Return to your workspace
      </Link>
    </main>
  );
}
