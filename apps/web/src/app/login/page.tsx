import { Suspense } from "react";
import { FleetPilotLogo } from "@fleetpilot/ui";
import { LoginForm } from "@/components/login";
import { ArrowUpRight, ShieldCheck } from "lucide-react";
export default function LoginPage() {
  return (
    <main id="main" className="login-page">
      <section className="login-story">
        <FleetPilotLogo />
        <div className="login-message">
          <span className="eyebrow">MOVE SMARTER. GO FURTHER.</span>
          <h1>
            Run the fleet.
            <br />
            <span>Not the chaos.</span>
          </h1>
          <p>
            One workspace. A clearer day.
            <br />
            Your next chapter starts here.
          </p>
          <div className="login-road" aria-hidden="true">
            <div />
            <div />
            <div />
          </div>
        </div>
        <div className="login-story-footer">
          <span>
            Built for the people
            <br />
            who keep business moving.
          </span>
          <ArrowUpRight size={30} />
        </div>
      </section>
      <section className="login-form-panel">
        <div className="login-mobile-brand">
          <FleetPilotLogo />
        </div>
        <div className="login-form-wrap">
          <span className="eyebrow muted">WELCOME TO FLEETPILOT</span>
          <h2>Good to see you.</h2>
          <p className="muted">Sign in to your organization’s workspace.</p>
          <Suspense>
            <LoginForm />
          </Suspense>
          <div className="login-security">
            <ShieldCheck size={17} />
            <span>Secure access. Your organization’s data stays yours.</span>
          </div>
        </div>
        <p className="login-footer">
          FleetPilot · Run the fleet. Not the chaos.
        </p>
      </section>
    </main>
  );
}
