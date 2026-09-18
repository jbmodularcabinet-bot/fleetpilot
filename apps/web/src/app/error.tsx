"use client";
import { ErrorState } from "@fleetpilot/ui";
export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <main id="main" className="standalone">
      <ErrorState message="Your workspace is temporarily unavailable. Please try again." />
      <button className="button primary" onClick={reset}>
        Try again
      </button>
    </main>
  );
}
