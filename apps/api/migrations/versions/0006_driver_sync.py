"""Durable, immutable driver command receipts; existing trip versions are retained."""

from alembic import op

revision = "0006_driver_sync"
down_revision = "0005_operational_hardening"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE driver_sync_commands (
      organization_id uuid NOT NULL REFERENCES organizations(id),
      actor_user_id uuid NOT NULL REFERENCES users(id),
      idempotency_key uuid NOT NULL,
      driver_id uuid NOT NULL,
      trip_id uuid NOT NULL,
      command_type varchar(20) NOT NULL,
      request_hash varchar(64) NOT NULL,
      result jsonb NOT NULL,
      occurred_at_client timestamptz NOT NULL,
      received_at_server timestamptz NOT NULL DEFAULT clock_timestamp(),
      clock_suspect boolean NOT NULL,
      PRIMARY KEY (organization_id, actor_user_id, idempotency_key),
      FOREIGN KEY (organization_id, driver_id) REFERENCES drivers(organization_id,id),
      FOREIGN KEY (organization_id, trip_id) REFERENCES trips(organization_id,id)
    )""")
    op.execute(
        "CREATE INDEX ix_driver_sync_trip ON driver_sync_commands(organization_id, trip_id, received_at_server)"
    )
    op.execute("ALTER TABLE driver_sync_commands ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE driver_sync_commands FORCE ROW LEVEL SECURITY")
    policy = "organization_id = NULLIF(current_setting('app.organization_id',true),'')::uuid AND actor_user_id = NULLIF(current_setting('app.user_id',true),'')::uuid"
    op.execute(f"CREATE POLICY sync_read ON driver_sync_commands FOR SELECT USING ({policy})")
    op.execute(
        f"CREATE POLICY sync_insert ON driver_sync_commands FOR INSERT WITH CHECK ({policy})"
    )
    op.execute("""CREATE FUNCTION immutable_sync_command() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN RAISE EXCEPTION 'Sync receipts are immutable'; END $$""")
    op.execute(
        "CREATE TRIGGER immutable_sync_command BEFORE UPDATE OR DELETE ON driver_sync_commands FOR EACH ROW EXECUTE FUNCTION immutable_sync_command()"
    )


def downgrade():
    op.execute("DROP TABLE driver_sync_commands")
    op.execute("DROP FUNCTION immutable_sync_command()")
