import { Logout } from "@/components/navigation";
export default function AccessDenied() {
  return (
    <main id="main" className="standalone">
      <h1>Workspace access is unavailable.</h1>
      <p>
        Contact your administrator to check your account and organization
        membership.
      </p>
      <Logout />
    </main>
  );
}
