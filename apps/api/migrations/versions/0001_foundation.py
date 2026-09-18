"""Foundation tables, constraints and row-level security. Frozen migration schema."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def timestamps():
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", pg.UUID(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("hashed_password", sa.String(1024), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_superuser", sa.Boolean(), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("phone", sa.String(30)),
        sa.Column("auth_provider_id", sa.String(255), unique=True),
        sa.Column("status", sa.String(20), nullable=False),
        *timestamps(),
        sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="user_status"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table(
        "organizations",
        sa.Column("id", pg.UUID(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("legal_name", sa.String(200)),
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("timezone", sa.String(80), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("country", sa.String(2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("settings_json", pg.JSONB(), nullable=False),
        *timestamps(),
        sa.CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="organization_slug"),
        sa.CheckConstraint("status IN ('ACTIVE', 'SUSPENDED')", name="organization_status"),
    )
    op.create_table(
        "organization_memberships",
        sa.Column("id", pg.UUID(), primary_key=True),
        sa.Column("organization_id", pg.UUID(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", pg.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("permissions_json", pg.JSONB()),
        sa.Column("active", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_membership_org_user"),
        sa.CheckConstraint(
            "role IN ('OWNER','MANAGER','DISPATCHER','DRIVER','ACCOUNTING','MAINTENANCE','ADMIN')",
            name="membership_role",
        ),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", pg.UUID(), primary_key=True),
        sa.Column("organization_id", pg.UUID(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("actor_user_id", pg.UUID(), sa.ForeignKey("users.id")),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(60), nullable=False),
        sa.Column("entity_id", pg.UUID()),
        sa.Column("before_json", pg.JSONB()),
        sa.Column("after_json", pg.JSONB()),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("metadata_json", pg.JSONB()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("token", sa.String(64), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "user_id", pg.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
    )
    for table, columns in {
        "organization_memberships": ["organization_id", "user_id"],
        "audit_logs": ["organization_id"],
        "auth_sessions": ["user_id", "created_at"],
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])
    org = "NULLIF(current_setting('app.organization_id', true), '')::uuid"
    user = "NULLIF(current_setting('app.user_id', true), '')::uuid"
    for table in ("organizations", "organization_memberships", "audit_logs"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY membership_read ON organization_memberships FOR SELECT USING (user_id = {user} OR organization_id = {org})"
    )
    op.execute(
        f"CREATE POLICY membership_insert ON organization_memberships FOR INSERT WITH CHECK (organization_id = {org})"
    )
    op.execute(
        f"CREATE POLICY membership_update ON organization_memberships FOR UPDATE USING (organization_id = {org}) WITH CHECK (organization_id = {org})"
    )
    op.execute(
        f"CREATE POLICY organization_read ON organizations FOR SELECT USING (id = {org} OR id IN (SELECT organization_id FROM organization_memberships WHERE user_id = {user} AND active))"
    )
    op.execute(
        f"CREATE POLICY organization_update ON organizations FOR UPDATE USING (id = {org}) WITH CHECK (id = {org})"
    )
    op.execute(f"CREATE POLICY audit_read ON audit_logs FOR SELECT USING (organization_id = {org})")
    op.execute(
        f"CREATE POLICY audit_insert ON audit_logs FOR INSERT WITH CHECK (organization_id = {org})"
    )
    op.execute(
        "CREATE FUNCTION reject_audit_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Audit logs are append-only'; END $$"
    )
    op.execute(
        "CREATE TRIGGER audit_immutable BEFORE UPDATE OR DELETE ON audit_logs FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()"
    )


def downgrade():
    op.drop_table("auth_sessions")
    op.drop_table("audit_logs")
    op.execute("DROP FUNCTION reject_audit_mutation()")
    op.execute("DROP POLICY organization_read ON organizations")
    op.drop_table("organization_memberships")
    op.drop_table("organizations")
    op.drop_table("users")
