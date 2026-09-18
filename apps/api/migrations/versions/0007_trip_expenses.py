"""Operational PHP costs, immutable revisions and private receipt history."""

from alembic import op

revision = "0007_trip_expenses"
down_revision = "0006_driver_sync"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE vehicles ADD COLUMN reviewed_fuel_odometer numeric(9,1) CHECK(reviewed_fuel_odometer BETWEEN 0 AND 10000000)"
    )
    op.execute("""CREATE TABLE trip_expenses (
      id uuid PRIMARY KEY, organization_id uuid NOT NULL REFERENCES organizations(id),
      trip_id uuid NOT NULL, vehicle_id uuid NOT NULL, driver_id uuid NOT NULL,
      current_revision integer NOT NULL DEFAULT 1 CHECK(current_revision > 0),
      status varchar(20) NOT NULL DEFAULT 'SUBMITTED' CHECK(status IN ('SUBMITTED','REVIEWED','VOIDED')),
      submission_source varchar(20) NOT NULL CHECK(submission_source IN ('OWNER_WEB','DRIVER_APP')),
      submitted_by uuid NOT NULL REFERENCES users(id), submitted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      reviewed_by uuid REFERENCES users(id), reviewed_at timestamptz, review_notes text,
      voided_by uuid REFERENCES users(id), voided_at timestamptz, void_reason text,
      UNIQUE(organization_id,trip_id,id),
      FOREIGN KEY(organization_id,trip_id) REFERENCES trips(organization_id,id),
      FOREIGN KEY(organization_id,vehicle_id) REFERENCES vehicles(organization_id,id),
      FOREIGN KEY(organization_id,driver_id) REFERENCES drivers(organization_id,id),
      CHECK ((status='REVIEWED') = (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)),
      CHECK ((status='VOIDED') = (voided_by IS NOT NULL AND voided_at IS NOT NULL AND length(trim(void_reason))>=3))
    )""")
    op.execute("""CREATE TABLE expense_revisions (
      id uuid PRIMARY KEY, organization_id uuid NOT NULL, trip_id uuid NOT NULL, expense_id uuid NOT NULL,
      revision_number integer NOT NULL CHECK(revision_number>0),
      category varchar(30) NOT NULL CHECK(category IN ('FUEL','TOLL','PARKING','DRIVER_ALLOWANCE','DRIVER_CASH_ADVANCE','HELPER_ALLOWANCE','LOADING_FEE','UNLOADING_FEE','SUBCONTRACTOR','OTHER')),
      currency varchar(3) NOT NULL CHECK(currency='PHP'), amount numeric(12,2) NOT NULL CHECK(amount>0 AND amount<=10000000),
      occurred_at timestamptz NOT NULL, description text, vendor_name varchar(160), reference_number varchar(120),
      liters numeric(9,3), price_per_liter numeric(9,4), odometer numeric(9,1),
      created_by uuid NOT NULL REFERENCES users(id), created_at timestamptz NOT NULL DEFAULT clock_timestamp(), reason text,
      UNIQUE(organization_id,expense_id,revision_number),
      FOREIGN KEY(organization_id,trip_id,expense_id) REFERENCES trip_expenses(organization_id,trip_id,id),
      CHECK ((category='FUEL' AND liters>0 AND liters<=10000 AND price_per_liter>0 AND price_per_liter<=10000 AND liters IS NOT NULL AND price_per_liter IS NOT NULL AND amount=round(liters*price_per_liter,2)) OR (category<>'FUEL' AND liters IS NULL AND price_per_liter IS NULL AND odometer IS NULL)),
      CHECK(odometer IS NULL OR odometer BETWEEN 0 AND 10000000),
      CHECK(category<>'OTHER' OR (description IS NOT NULL AND length(trim(description))>=3)),
      CHECK(category<>'SUBCONTRACTOR' OR (vendor_name IS NOT NULL AND length(trim(vendor_name))>0)),
      CHECK(revision_number=1 OR (reason IS NOT NULL AND length(trim(reason))>=3))
    )""")
    op.execute("""ALTER TABLE trip_expenses ADD CONSTRAINT current_expense_revision
      FOREIGN KEY(organization_id,id,current_revision) REFERENCES expense_revisions(organization_id,expense_id,revision_number)
      DEFERRABLE INITIALLY DEFERRED""")
    op.execute("""CREATE TABLE expense_evidence (
      id uuid PRIMARY KEY, organization_id uuid NOT NULL, trip_id uuid NOT NULL, expense_id uuid NOT NULL,
      storage_key varchar(160) NOT NULL UNIQUE, original_filename varchar(160) NOT NULL,
      content_type varchar(30) NOT NULL CHECK(content_type='image/png'), file_size integer NOT NULL CHECK(file_size BETWEEN 1 AND 5242880),
      checksum varchar(64) NOT NULL, uploaded_by uuid NOT NULL REFERENCES users(id),
      uploaded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      status varchar(20) NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','SUPERSEDED')),
      supersedes_id uuid, UNIQUE(organization_id,expense_id,id),
      FOREIGN KEY(organization_id,trip_id,expense_id) REFERENCES trip_expenses(organization_id,trip_id,id),
      FOREIGN KEY(organization_id,expense_id,supersedes_id) REFERENCES expense_evidence(organization_id,expense_id,id)
    )""")
    op.execute(
        "CREATE INDEX ix_expenses_trip ON trip_expenses(organization_id,trip_id,submitted_at,id)"
    )
    op.execute(
        "CREATE INDEX ix_expenses_vehicle ON trip_expenses(organization_id,vehicle_id,submitted_at,id)"
    )
    op.execute(
        "CREATE INDEX ix_expense_evidence_parent ON expense_evidence(organization_id,expense_id,uploaded_at)"
    )
    org = "NULLIF(current_setting('app.organization_id',true),'')::uuid"
    user = "NULLIF(current_setting('app.user_id',true),'')::uuid"
    member = f"EXISTS(SELECT 1 FROM organization_memberships m WHERE m.organization_id={org} AND m.user_id={user} AND m.active AND m.role<>'DRIVER')"
    own = f"driver_id IN(SELECT id FROM drivers WHERE organization_id={org} AND user_id={user} AND employment_status='ACTIVE')"
    for table in ("trip_expenses", "expense_revisions", "expense_evidence"):
        policy = f"organization_id={org} AND EXISTS(SELECT 1 FROM trips t WHERE t.id={table}.trip_id AND t.organization_id={org})"
        policy += (
            f" AND ({member} OR {own})"
            if table == "trip_expenses"
            else f" AND EXISTS(SELECT 1 FROM trip_expenses e WHERE e.id={table}.expense_id AND e.organization_id={org})"
        )
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY expense_read ON {table} FOR SELECT USING ({policy})")
        op.execute(f"CREATE POLICY expense_insert ON {table} FOR INSERT WITH CHECK ({policy})")
        if table != "expense_revisions":
            op.execute(
                f"CREATE POLICY expense_update ON {table} FOR UPDATE USING ({policy}) WITH CHECK ({policy})"
            )
    op.execute("""CREATE FUNCTION guard_expense_history() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='DELETE' OR TG_TABLE_NAME='expense_revisions' THEN RAISE EXCEPTION 'Expense history is immutable'; END IF;
      IF TG_TABLE_NAME='expense_evidence' THEN
        IF OLD.status<>'ACTIVE' OR NEW.status<>'SUPERSEDED' OR (to_jsonb(NEW)-'status') IS DISTINCT FROM (to_jsonb(OLD)-'status') THEN RAISE EXCEPTION 'Receipt is immutable'; END IF;
      ELSE
        IF OLD.status='VOIDED' OR (to_jsonb(NEW)-ARRAY['current_revision','status','reviewed_by','reviewed_at','review_notes','voided_by','voided_at','void_reason']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['current_revision','status','reviewed_by','reviewed_at','review_notes','voided_by','voided_at','void_reason']) THEN RAISE EXCEPTION 'Expense identity is immutable'; END IF;
        IF NEW.current_revision NOT IN (OLD.current_revision,OLD.current_revision+1) THEN RAISE EXCEPTION 'Invalid revision'; END IF;
        IF NEW.current_revision<>OLD.current_revision AND NEW.status<>'SUBMITTED' THEN RAISE EXCEPTION 'Corrections require review'; END IF;
      END IF;
      RETURN NEW;
    END $$""")
    for table in ("trip_expenses", "expense_revisions", "expense_evidence"):
        op.execute(
            f"CREATE TRIGGER immutable_expense_history BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION guard_expense_history()"
        )

    op.execute("""CREATE FUNCTION guard_expense_context() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE active_trip trips%ROWTYPE; parent trip_expenses%ROWTYPE; member_role text;
    BEGIN
      SELECT * INTO active_trip FROM trips WHERE id=NEW.trip_id AND organization_id=NEW.organization_id;
      IF NOT FOUND OR active_trip.current_status IN ('SCHEDULED','COMPLETED','CANCELLED') THEN RAISE EXCEPTION 'Expenses require an open dispatched trip'; END IF;
      SELECT role INTO member_role FROM organization_memberships WHERE organization_id=NEW.organization_id AND user_id=NULLIF(current_setting('app.user_id',true),'')::uuid AND active;
      IF TG_TABLE_NAME='trip_expenses' THEN
        IF TG_OP='INSERT' AND (NEW.vehicle_id IS DISTINCT FROM active_trip.vehicle_id OR NEW.driver_id IS DISTINCT FROM active_trip.driver_id OR NEW.status<>'SUBMITTED' OR NEW.current_revision<>1) THEN RAISE EXCEPTION 'Invalid expense assignment'; END IF;
        IF TG_OP='UPDATE' AND member_role='DRIVER' THEN RAISE EXCEPTION 'Driver cannot review or correct expense'; END IF;
      ELSE
        SELECT * INTO parent FROM trip_expenses WHERE id=NEW.expense_id AND organization_id=NEW.organization_id;
        IF NOT FOUND OR parent.status='VOIDED' THEN RAISE EXCEPTION 'Expense is closed'; END IF;
        IF TG_TABLE_NAME='expense_evidence' AND parent.status<>'SUBMITTED' THEN RAISE EXCEPTION 'Receipt requires submitted expense'; END IF;
        IF TG_TABLE_NAME='expense_revisions' THEN
          IF TG_OP='INSERT' AND ((NEW.revision_number<>parent.current_revision AND NEW.revision_number<>parent.current_revision+1) OR (member_role='DRIVER' AND NEW.revision_number<>1)) THEN RAISE EXCEPTION 'Invalid financial revision'; END IF;
        END IF;
      END IF;
      RETURN NEW;
    END $$""")
    for table in ("trip_expenses", "expense_revisions", "expense_evidence"):
        op.execute(
            f"CREATE TRIGGER expense_context BEFORE INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION guard_expense_context()"
        )
    op.execute("""CREATE FUNCTION retain_reviewed_fuel_reading() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE reading numeric;
    BEGIN
      IF NEW.status='REVIEWED' AND OLD.status<>'REVIEWED' THEN
        SELECT odometer INTO reading FROM expense_revisions WHERE organization_id=NEW.organization_id AND expense_id=NEW.id AND revision_number=NEW.current_revision AND category='FUEL';
        IF reading IS NOT NULL THEN
          UPDATE vehicles SET reviewed_fuel_odometer=greatest(coalesce(reviewed_fuel_odometer,0),reading) WHERE organization_id=NEW.organization_id AND id=NEW.vehicle_id;
        END IF;
      END IF;
      RETURN NEW;
    END $$""")
    op.execute(
        "CREATE TRIGGER retain_fuel_reading AFTER UPDATE ON trip_expenses FOR EACH ROW EXECUTE FUNCTION retain_reviewed_fuel_reading()"
    )
    op.execute("""CREATE FUNCTION guard_reviewed_fuel_reading() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF OLD.reviewed_fuel_odometer IS NOT NULL AND (NEW.reviewed_fuel_odometer IS NULL OR NEW.reviewed_fuel_odometer<OLD.reviewed_fuel_odometer) THEN RAISE EXCEPTION 'Reviewed fuel reading cannot silently decrease'; END IF;
      RETURN NEW;
    END $$""")
    op.execute(
        "CREATE TRIGGER protect_reviewed_fuel_reading BEFORE UPDATE ON vehicles FOR EACH ROW EXECUTE FUNCTION guard_reviewed_fuel_reading()"
    )


def downgrade():
    op.execute("ALTER TABLE trip_expenses DROP CONSTRAINT current_expense_revision")
    for table in ("expense_evidence", "expense_revisions", "trip_expenses"):
        op.drop_table(table)
    op.execute("DROP FUNCTION guard_expense_history()")
    op.execute("DROP FUNCTION IF EXISTS guard_expense_context()")
    op.execute("DROP TRIGGER IF EXISTS protect_reviewed_fuel_reading ON vehicles")
    op.execute("DROP FUNCTION IF EXISTS guard_reviewed_fuel_reading()")
    op.execute("DROP FUNCTION IF EXISTS retain_reviewed_fuel_reading()")
    op.execute("ALTER TABLE vehicles DROP COLUMN IF EXISTS reviewed_fuel_odometer")
