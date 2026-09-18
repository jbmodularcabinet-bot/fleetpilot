import { Card, PageHeader, StatusBadge } from "@fleetpilot/ui";
import { getIdentity } from "@/lib/server";
import { Logout } from "@/components/navigation";
import { OwnDriverProfile } from "@/components/master-data";
export default async function Profile() {
  const identity = await getIdentity("driver_app.view");
  return (
    <div className="driver-content profile">
      <PageHeader
        title="Profile"
        description="Your information in one place."
      />
      <div className="profile-avatar">{identity.user.name[0]}</div>
      <h2>{identity.user.name}</h2>
      <StatusBadge tone="active">Driver</StatusBadge>
      <Card title="Your account">
        <dl>
          <dt>Email</dt>
          <dd>{identity.user.email}</dd>
          <dt>Organization</dt>
          <dd>{identity.organization.name}</dd>
          <dt>Timezone</dt>
          <dd>{identity.organization.timezone}</dd>
        </dl>
      </Card>
      <OwnDriverProfile />
      <Logout />
    </div>
  );
}
