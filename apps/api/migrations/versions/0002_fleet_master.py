"""Tenant master records and durable one-to-one assignment history."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0002_fleet_master"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def common():
    return [
        sa.Column("id", pg.UUID(), primary_key=True),
        sa.Column("organization_id", pg.UUID(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("created_by", pg.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_by", pg.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade():
    op.create_table(
        "customers",
        *common(),
        sa.Column("customer_code", sa.String(40), nullable=False),
        sa.Column("company_name", sa.String(160), nullable=False),
        sa.Column("contact_person", sa.String(120)),
        sa.Column("phone", sa.String(30)),
        sa.Column("email", sa.String(320)),
        sa.Column("billing_address", sa.Text()),
        sa.Column("pickup_notes", sa.Text()),
        sa.Column("delivery_notes", sa.Text()),
        sa.Column("payment_terms", sa.String(120)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.UniqueConstraint("organization_id", "customer_code", name="uq_customer_code"),
        sa.CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_customer_status"),
        sa.CheckConstraint(
            "customer_code = upper(customer_code)", name="ck_customer_code_normalized"
        ),
    )
    op.create_table(
        "vehicles",
        *common(),
        sa.Column("unit_number", sa.String(40), nullable=False),
        sa.Column("plate_number", sa.String(30), nullable=False),
        sa.Column("vehicle_type", sa.String(80), nullable=False),
        sa.Column("make", sa.String(80)),
        sa.Column("model", sa.String(80)),
        sa.Column("year", sa.Integer()),
        sa.Column("capacity", sa.Numeric(14, 3)),
        sa.Column("capacity_unit", sa.String(20)),
        sa.Column("odometer", sa.Numeric(14, 1)),
        sa.Column("registration_expiry", sa.Date()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.UniqueConstraint("organization_id", "id", name="uq_vehicle_tenant_id"),
        sa.UniqueConstraint("organization_id", "unit_number", name="uq_vehicle_unit"),
        sa.UniqueConstraint("organization_id", "plate_number", name="uq_vehicle_plate"),
        sa.CheckConstraint(
            "status IN ('AVAILABLE','ASSIGNED','INACTIVE')", name="ck_vehicle_status"
        ),
        sa.CheckConstraint("capacity >= 0 AND odometer >= 0", name="ck_vehicle_nonnegative"),
        sa.CheckConstraint("year BETWEEN 1900 AND 2100", name="ck_vehicle_year"),
        sa.CheckConstraint(
            "(capacity IS NULL AND capacity_unit IS NULL) OR (capacity IS NOT NULL AND capacity_unit IS NOT NULL AND capacity_unit IN ('kg','tonnes','m3','pallets'))",
            name="ck_vehicle_capacity_unit",
        ),
        sa.CheckConstraint(
            "unit_number = upper(unit_number) AND plate_number = upper(plate_number)",
            name="ck_vehicle_codes_normalized",
        ),
    )
    op.create_table(
        "drivers",
        *common(),
        sa.Column("user_id", pg.UUID()),
        sa.Column("employee_number", sa.String(40), nullable=False),
        sa.Column("first_name", sa.String(80), nullable=False),
        sa.Column("last_name", sa.String(80), nullable=False),
        sa.Column("phone", sa.String(30)),
        sa.Column("email", sa.String(320)),
        sa.Column("license_number", sa.String(40)),
        sa.Column("license_type", sa.String(80)),
        sa.Column("license_expiry", sa.Date()),
        sa.Column("employment_status", sa.String(20), nullable=False),
        sa.Column("operational_status", sa.String(20), nullable=False),
        sa.Column("emergency_contact_name", sa.String(120)),
        sa.Column("emergency_contact_phone", sa.String(30)),
        sa.UniqueConstraint("organization_id", "id", name="uq_driver_tenant_id"),
        sa.UniqueConstraint("organization_id", "employee_number", name="uq_driver_employee"),
        sa.UniqueConstraint("organization_id", "license_number", name="uq_driver_license"),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_driver_user"),
        sa.ForeignKeyConstraint(
            ["organization_id", "user_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_driver_membership",
        ),
        sa.CheckConstraint(
            "employment_status IN ('ACTIVE','ON_LEAVE','SUSPENDED','INACTIVE')",
            name="ck_driver_employment",
        ),
        sa.CheckConstraint(
            "operational_status IN ('UNASSIGNED','ASSIGNED','INACTIVE')",
            name="ck_driver_operational",
        ),
        sa.CheckConstraint(
            "employee_number = upper(employee_number) AND (license_number IS NULL OR license_number = upper(license_number))",
            name="ck_driver_codes_normalized",
        ),
    )
    op.create_table(
        "vehicle_driver_assignments",
        sa.Column("id", pg.UUID(), primary_key=True),
        sa.Column("organization_id", pg.UUID(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("vehicle_id", pg.UUID(), nullable=False),
        sa.Column("driver_id", pg.UUID(), nullable=False),
        sa.Column(
            "assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("unassigned_at", sa.DateTime(timezone=True)),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("created_by", pg.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "vehicle_id"],
            ["vehicles.organization_id", "vehicles.id"],
            name="fk_assignment_vehicle_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "driver_id"],
            ["drivers.organization_id", "drivers.id"],
            name="fk_assignment_driver_tenant",
        ),
        sa.CheckConstraint(
            "(is_current AND unassigned_at IS NULL) OR (NOT is_current AND unassigned_at IS NOT NULL AND unassigned_at >= assigned_at)",
            name="ck_assignment_lifecycle",
        ),
    )
    for table, status in [
        ("customers", "status"),
        ("vehicles", "status"),
        ("drivers", "employment_status"),
    ]:
        op.create_index(
            f"ix_{table}_tenant_status_created", table, ["organization_id", status, "created_at"]
        )
        op.create_index(f"ix_{table}_tenant_created", table, ["organization_id", "created_at"])
    for field in ("vehicle_id", "driver_id"):
        op.create_index(
            f"uq_current_{field}",
            "vehicle_driver_assignments",
            ["organization_id", field],
            unique=True,
            postgresql_where=sa.text("is_current"),
        )
        op.create_index(
            f"ix_assignment_{field}_history",
            "vehicle_driver_assignments",
            ["organization_id", field, "assigned_at"],
        )
    op.create_index(
        "ix_assignment_tenant_created",
        "vehicle_driver_assignments",
        ["organization_id", "created_at"],
    )
    org = "NULLIF(current_setting('app.organization_id', true), '')::uuid"
    for table in ("customers", "vehicles", "drivers", "vehicle_driver_assignments"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        for action in ("SELECT", "INSERT", "UPDATE"):
            using = f"USING (organization_id = {org})" if action != "INSERT" else ""
            check = f"WITH CHECK (organization_id = {org})" if action != "SELECT" else ""
            op.execute(
                f"CREATE POLICY {table}_{action.lower()} ON {table} FOR {action} {using} {check}"
            )
    # No DELETE policies: deactivation preserves records. History may only be closed once.
    op.execute("""CREATE FUNCTION preserve_assignment_history() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Assignment history cannot be deleted'; END IF;
      IF NOT OLD.is_current OR NEW.is_current OR NEW.unassigned_at IS NULL
         OR (to_jsonb(NEW) - 'is_current' - 'unassigned_at') IS DISTINCT FROM (to_jsonb(OLD) - 'is_current' - 'unassigned_at')
      THEN RAISE EXCEPTION 'Only explicit unassignment may change assignment history'; END IF;
      RETURN NEW;
    END $$""")
    op.execute(
        "CREATE TRIGGER immutable_assignment_history BEFORE UPDATE OR DELETE ON vehicle_driver_assignments FOR EACH ROW EXECUTE FUNCTION preserve_assignment_history()"
    )


def downgrade():
    op.drop_table("vehicle_driver_assignments")
    op.execute("DROP FUNCTION preserve_assignment_history()")
    op.drop_table("drivers")
    op.drop_table("vehicles")
    op.drop_table("customers")
