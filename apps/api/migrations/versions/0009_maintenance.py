"""Tenant maintenance, immutable defect/cost/evidence history and vehicle safety."""

from alembic import op

revision = "0009_maintenance"
down_revision = "0008_closed_trip_adjustments"
branch_labels = depends_on = None
TABLES = (
    "maintenance_schedules",
    "driver_defects",
    "maintenance_work_orders",
    "maintenance_cost_items",
    "maintenance_evidence",
    "maintenance_events",
)


def upgrade():
    op.execute("ALTER TABLE vehicles DROP CONSTRAINT ck_vehicle_status")
    op.execute(
        "ALTER TABLE vehicles ADD CONSTRAINT ck_vehicle_status CHECK(status IN ('AVAILABLE','ASSIGNED','MAINTENANCE','INACTIVE'))"
    )
    op.execute(
        "ALTER TABLE vehicles ADD COLUMN maintenance_odometer numeric(9,1) CHECK(maintenance_odometer BETWEEN 0 AND 10000000)"
    )
    op.execute("ALTER TABLE driver_sync_commands ALTER COLUMN trip_id DROP NOT NULL")
    op.execute("ALTER TABLE driver_sync_commands ALTER COLUMN driver_id DROP NOT NULL")
    op.execute("""CREATE TABLE maintenance_schedules (
      id uuid PRIMARY KEY, organization_id uuid NOT NULL REFERENCES organizations(id), vehicle_id uuid NOT NULL,
      service_type varchar(40) NOT NULL, interval_type varchar(30) NOT NULL CHECK(interval_type IN ('ODOMETER','DATE','ODOMETER_OR_DATE')),
      odometer_interval_km integer CHECK(odometer_interval_km BETWEEN 1 AND 1000000), date_interval_days integer CHECK(date_interval_days BETWEEN 1 AND 3650),
      last_service_odometer numeric(9,1), last_service_at date, next_due_odometer numeric(12,1), next_due_at date,
      warning_km integer NOT NULL CHECK(warning_km>=0), warning_days integer NOT NULL CHECK(warning_days>=0),
      is_active boolean NOT NULL DEFAULT true, notes text,
      created_by uuid NOT NULL REFERENCES users(id), created_at timestamptz NOT NULL DEFAULT clock_timestamp(), updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      UNIQUE(organization_id,id), FOREIGN KEY(organization_id,vehicle_id) REFERENCES vehicles(organization_id,id),
      CHECK((interval_type='DATE')=(odometer_interval_km IS NULL)), CHECK((interval_type='ODOMETER')=(date_interval_days IS NULL)),
      CHECK(odometer_interval_km IS NULL OR (last_service_odometer IS NOT NULL AND next_due_odometer=last_service_odometer+odometer_interval_km AND warning_km<=odometer_interval_km)),
      CHECK(date_interval_days IS NULL OR (last_service_at IS NOT NULL AND next_due_at=last_service_at+date_interval_days AND warning_days<=date_interval_days))
    )""")
    op.execute("""CREATE TABLE driver_defects (
      id uuid PRIMARY KEY, organization_id uuid NOT NULL REFERENCES organizations(id), vehicle_id uuid NOT NULL, driver_id uuid NOT NULL, trip_id uuid,
      severity varchar(20) NOT NULL CHECK(severity IN ('MINOR','MODERATE','SERIOUS','CRITICAL')),
      category varchar(40) NOT NULL, description text NOT NULL CHECK(length(trim(description))>=3),
      reported_at_client timestamptz NOT NULL, received_at_server timestamptz NOT NULL DEFAULT clock_timestamp(),
      status varchar(30) NOT NULL DEFAULT 'REPORTED' CHECK(status IN ('REPORTED','REVIEWED','WORK_ORDER_CREATED','RESOLVED','DISMISSED')),
      created_by uuid NOT NULL REFERENCES users(id), created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      UNIQUE(organization_id,id), FOREIGN KEY(organization_id,vehicle_id) REFERENCES vehicles(organization_id,id),
      FOREIGN KEY(organization_id,driver_id) REFERENCES drivers(organization_id,id), FOREIGN KEY(organization_id,trip_id) REFERENCES trips(organization_id,id)
    )""")
    op.execute("""CREATE TABLE maintenance_work_orders (
      id uuid PRIMARY KEY, organization_id uuid NOT NULL REFERENCES organizations(id), vehicle_id uuid NOT NULL,
      maintenance_schedule_id uuid, defect_report_id uuid, trip_id uuid,
      work_order_number varchar(40) NOT NULL, type varchar(30) NOT NULL CHECK(type IN ('PREVENTIVE','REPAIR','INSPECTION','DEFECT_RESPONSE','OTHER')),
      priority varchar(20) NOT NULL CHECK(priority IN ('LOW','NORMAL','HIGH','CRITICAL')),
      status varchar(20) NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN','SCHEDULED','IN_PROGRESS','COMPLETED','CANCELLED')), version integer NOT NULL DEFAULT 1,
      title varchar(160) NOT NULL, description text NOT NULL, requires_vehicle_downtime boolean NOT NULL,
      service_provider varchar(160), opened_at timestamptz NOT NULL DEFAULT clock_timestamp(), scheduled_at timestamptz, started_at timestamptz, completed_at timestamptz,
      odometer_at_open numeric(9,1), odometer_at_completion numeric(9,1), work_performed text,
      downtime_started_at timestamptz, downtime_ended_at timestamptz,
      created_by uuid NOT NULL REFERENCES users(id), created_at timestamptz NOT NULL DEFAULT clock_timestamp(), updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      UNIQUE(organization_id,id), UNIQUE(organization_id,work_order_number), UNIQUE(organization_id,defect_report_id),
      FOREIGN KEY(organization_id,vehicle_id) REFERENCES vehicles(organization_id,id),
      FOREIGN KEY(organization_id,maintenance_schedule_id) REFERENCES maintenance_schedules(organization_id,id),
      FOREIGN KEY(organization_id,defect_report_id) REFERENCES driver_defects(organization_id,id), FOREIGN KEY(organization_id,trip_id) REFERENCES trips(organization_id,id),
      CHECK(downtime_ended_at IS NULL OR downtime_ended_at>=downtime_started_at),
      CHECK((status='COMPLETED')=(completed_at IS NOT NULL))
    )""")
    op.execute("""CREATE TABLE maintenance_cost_items (
      id uuid PRIMARY KEY, organization_id uuid NOT NULL REFERENCES organizations(id), work_order_id uuid NOT NULL,
      type varchar(10) NOT NULL CHECK(type IN ('PART','LABOR','OTHER')), description text NOT NULL,
      quantity numeric(9,3) NOT NULL CHECK(quantity>0), unit_cost numeric(12,4) NOT NULL CHECK(unit_cost>=0),
      total_cost numeric(12,2) NOT NULL CHECK(total_cost=round(quantity*unit_cost,2) AND total_cost BETWEEN 0 AND 10000000),
      vendor varchar(160), reference varchar(120), created_by uuid NOT NULL REFERENCES users(id), created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      UNIQUE(organization_id,id), FOREIGN KEY(organization_id,work_order_id) REFERENCES maintenance_work_orders(organization_id,id)
    )""")
    op.execute("""CREATE TABLE maintenance_evidence (
      id uuid PRIMARY KEY, organization_id uuid NOT NULL REFERENCES organizations(id), work_order_id uuid, defect_id uuid,
      evidence_type varchar(40) NOT NULL, storage_key varchar(160) NOT NULL UNIQUE, original_filename varchar(160) NOT NULL,
      content_type varchar(40) NOT NULL DEFAULT 'image/png', file_size integer NOT NULL CHECK(file_size BETWEEN 1 AND 5242880), checksum varchar(64) NOT NULL,
      status varchar(20) NOT NULL DEFAULT 'ACTIVE' CHECK(status='ACTIVE'), uploaded_by uuid NOT NULL REFERENCES users(id), uploaded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      UNIQUE(organization_id,id), CHECK((work_order_id IS NULL)<>(defect_id IS NULL)),
      FOREIGN KEY(organization_id,work_order_id) REFERENCES maintenance_work_orders(organization_id,id), FOREIGN KEY(organization_id,defect_id) REFERENCES driver_defects(organization_id,id)
    )""")
    op.execute("""CREATE TABLE maintenance_events (
      id uuid PRIMARY KEY, organization_id uuid NOT NULL REFERENCES organizations(id), vehicle_id uuid NOT NULL,
      work_order_id uuid, defect_id uuid, schedule_id uuid, action varchar(60) NOT NULL, notes text,
      actor_id uuid NOT NULL REFERENCES users(id), created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      FOREIGN KEY(organization_id,vehicle_id) REFERENCES vehicles(organization_id,id),
      FOREIGN KEY(organization_id,work_order_id) REFERENCES maintenance_work_orders(organization_id,id),
      FOREIGN KEY(organization_id,defect_id) REFERENCES driver_defects(organization_id,id), FOREIGN KEY(organization_id,schedule_id) REFERENCES maintenance_schedules(organization_id,id)
    )""")
    org = "NULLIF(current_setting('app.organization_id',true),'')::uuid"
    user = "NULLIF(current_setting('app.user_id',true),'')::uuid"
    staff = f"EXISTS(SELECT 1 FROM organization_memberships m WHERE m.organization_id={org} AND m.user_id={user} AND m.active AND m.role IN ('OWNER','ADMIN','MANAGER','MAINTENANCE'))"
    own = f"EXISTS(SELECT 1 FROM drivers d WHERE d.organization_id={org} AND d.id=driver_id AND d.user_id={user} AND d.employment_status='ACTIVE')"
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        base = f"organization_id={org}"
        scope = staff
        if table == "driver_defects":
            scope = f"({staff} OR {own})"
        if table == "maintenance_evidence":
            scope = f"({staff} OR (defect_id IS NOT NULL AND EXISTS(SELECT 1 FROM driver_defects d WHERE d.organization_id={org} AND d.id=defect_id)))"
        if table == "maintenance_events":
            scope = f"({staff} OR (defect_id IS NOT NULL AND EXISTS(SELECT 1 FROM driver_defects d WHERE d.organization_id={org} AND d.id=defect_id)))"
        op.execute(
            f"CREATE POLICY maintenance_read ON {table} FOR SELECT USING ({base} AND {scope})"
        )
        op.execute(
            f"CREATE POLICY maintenance_insert ON {table} FOR INSERT WITH CHECK ({base} AND {scope})"
        )
        if table in ("maintenance_schedules", "maintenance_work_orders", "driver_defects"):
            op.execute(
                f"CREATE POLICY maintenance_update ON {table} FOR UPDATE USING ({base} AND {staff}) WITH CHECK ({base} AND {staff})"
            )
        if table in ("maintenance_cost_items", "maintenance_evidence", "maintenance_events"):
            op.execute(
                f"CREATE TRIGGER maintenance_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION immutable_sync_command()"
            )
    for table, cols in [
        ("maintenance_schedules", "vehicle_id,is_active,next_due_at"),
        ("maintenance_work_orders", "vehicle_id,status,created_at"),
        ("driver_defects", "vehicle_id,status,created_at"),
        ("maintenance_cost_items", "work_order_id,created_at"),
        ("maintenance_evidence", "defect_id,work_order_id"),
        ("maintenance_events", "vehicle_id,created_at"),
    ]:
        op.execute(f"CREATE INDEX ix_{table}_lookup ON {table}(organization_id,{cols})")
    op.execute("""CREATE FUNCTION guard_maintenance_history() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Maintenance history is retained'; END IF;
      IF TG_TABLE_NAME='driver_defects' THEN
        IF (to_jsonb(NEW)-'status') IS DISTINCT FROM (to_jsonb(OLD)-'status') THEN RAISE EXCEPTION 'Original report is immutable'; END IF;
        IF NOT ((OLD.status='REPORTED' AND NEW.status IN ('REVIEWED','DISMISSED')) OR (OLD.status='REVIEWED' AND NEW.status IN ('WORK_ORDER_CREATED','DISMISSED')) OR (OLD.status='WORK_ORDER_CREATED' AND NEW.status='RESOLVED')) THEN RAISE EXCEPTION 'Invalid defect transition'; END IF;
      ELSE
        IF OLD.status IN ('COMPLETED','CANCELLED') THEN RAISE EXCEPTION 'Closed maintenance is immutable'; END IF;
        IF NEW.version<>OLD.version+1 OR NOT ((OLD.status='OPEN' AND NEW.status IN ('SCHEDULED','IN_PROGRESS','CANCELLED')) OR (OLD.status='SCHEDULED' AND NEW.status IN ('IN_PROGRESS','CANCELLED')) OR (OLD.status='IN_PROGRESS' AND NEW.status='COMPLETED')) THEN RAISE EXCEPTION 'Invalid work order transition'; END IF;
        IF ROW(NEW.organization_id,NEW.vehicle_id,NEW.maintenance_schedule_id,NEW.defect_report_id,NEW.trip_id,NEW.requires_vehicle_downtime) IS DISTINCT FROM ROW(OLD.organization_id,OLD.vehicle_id,OLD.maintenance_schedule_id,OLD.defect_report_id,OLD.trip_id,OLD.requires_vehicle_downtime) THEN RAISE EXCEPTION 'Maintenance ownership is immutable'; END IF;
      END IF;
      RETURN NEW;
    END $$""")
    for table in ("driver_defects", "maintenance_work_orders"):
        op.execute(
            f"CREATE TRIGGER maintenance_history BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION guard_maintenance_history()"
        )
    op.execute("""CREATE FUNCTION guard_vehicle_maintenance() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF EXISTS(SELECT 1 FROM maintenance_work_orders w WHERE w.organization_id=NEW.organization_id AND w.vehicle_id=NEW.id AND w.status='IN_PROGRESS' AND w.requires_vehicle_downtime) AND NEW.status NOT IN ('MAINTENANCE','INACTIVE') THEN RAISE EXCEPTION 'Active maintenance blocks availability'; END IF;
      IF NEW.status='MAINTENANCE' AND EXISTS(SELECT 1 FROM trips t WHERE t.organization_id=NEW.organization_id AND t.vehicle_id=NEW.id AND t.current_status NOT IN ('SCHEDULED','COMPLETED','CANCELLED')) THEN RAISE EXCEPTION 'Close or reassign operational trip before downtime'; END IF;
      RETURN NEW;
    END $$""")
    op.execute(
        "CREATE TRIGGER maintenance_vehicle_safety BEFORE UPDATE ON vehicles FOR EACH ROW EXECUTE FUNCTION guard_vehicle_maintenance()"
    )
    op.execute("""CREATE FUNCTION guard_dispatch_maintenance() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.vehicle_id IS NOT NULL AND (TG_OP='INSERT' OR NEW.vehicle_id IS DISTINCT FROM OLD.vehicle_id OR (NEW.current_status='DISPATCHED' AND OLD.current_status='SCHEDULED')) AND EXISTS(SELECT 1 FROM vehicles v WHERE v.organization_id=NEW.organization_id AND v.id=NEW.vehicle_id AND v.status IN ('MAINTENANCE','INACTIVE')) THEN RAISE EXCEPTION 'Vehicle unavailable for dispatch'; END IF;
      RETURN NEW;
    END $$""")
    op.execute(
        "CREATE TRIGGER maintenance_dispatch_safety BEFORE INSERT OR UPDATE ON trips FOR EACH ROW EXECUTE FUNCTION guard_dispatch_maintenance()"
    )

    op.execute("""CREATE FUNCTION guard_maintenance_insert() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE parent_status text; parent_vehicle uuid; linked_user uuid;
    BEGIN
      IF TG_TABLE_NAME='maintenance_work_orders' THEN
        IF NEW.status<>'OPEN' THEN RAISE EXCEPTION 'New work must be open'; END IF;
        IF NEW.maintenance_schedule_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM maintenance_schedules s WHERE s.organization_id=NEW.organization_id AND s.id=NEW.maintenance_schedule_id AND s.vehicle_id=NEW.vehicle_id AND s.is_active) THEN RAISE EXCEPTION 'Invalid service source'; END IF;
        IF NEW.defect_report_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM driver_defects d WHERE d.organization_id=NEW.organization_id AND d.id=NEW.defect_report_id AND d.vehicle_id=NEW.vehicle_id AND d.status='REVIEWED') THEN RAISE EXCEPTION 'Invalid defect source'; END IF;
        IF NEW.trip_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM trips t WHERE t.organization_id=NEW.organization_id AND t.id=NEW.trip_id AND t.vehicle_id=NEW.vehicle_id) THEN RAISE EXCEPTION 'Invalid trip context'; END IF;
      ELSIF TG_TABLE_NAME='driver_defects' THEN
        SELECT user_id INTO linked_user FROM drivers WHERE organization_id=NEW.organization_id AND id=NEW.driver_id AND employment_status='ACTIVE';
        IF linked_user IS NULL OR linked_user<>NEW.created_by OR linked_user IS DISTINCT FROM NULLIF(current_setting('app.user_id',true),'')::uuid OR NEW.status<>'REPORTED' THEN RAISE EXCEPTION 'Invalid defect actor'; END IF;
        IF NEW.trip_id IS NOT NULL THEN
          IF NOT EXISTS(SELECT 1 FROM trips t WHERE t.organization_id=NEW.organization_id AND t.id=NEW.trip_id AND t.vehicle_id=NEW.vehicle_id AND t.driver_id=NEW.driver_id AND t.current_status NOT IN ('COMPLETED','CANCELLED')) THEN RAISE EXCEPTION 'Unauthorized trip vehicle'; END IF;
        ELSIF NOT EXISTS(SELECT 1 FROM vehicle_driver_assignments a WHERE a.organization_id=NEW.organization_id AND a.vehicle_id=NEW.vehicle_id AND a.driver_id=NEW.driver_id AND a.is_current) AND NOT EXISTS(SELECT 1 FROM trips t WHERE t.organization_id=NEW.organization_id AND t.vehicle_id=NEW.vehicle_id AND t.driver_id=NEW.driver_id AND t.current_status NOT IN ('COMPLETED','CANCELLED')) THEN RAISE EXCEPTION 'Unauthorized vehicle'; END IF;
      ELSE
        IF NEW.work_order_id IS NOT NULL THEN
          SELECT status INTO parent_status FROM maintenance_work_orders WHERE organization_id=NEW.organization_id AND id=NEW.work_order_id;
          IF parent_status IS NULL OR parent_status IN ('COMPLETED','CANCELLED') THEN RAISE EXCEPTION 'Closed work history'; END IF;
        ELSIF TG_TABLE_NAME='maintenance_evidence' THEN
          SELECT status INTO parent_status FROM driver_defects WHERE organization_id=NEW.organization_id AND id=NEW.defect_id;
          IF parent_status IS NULL OR parent_status NOT IN ('REPORTED','REVIEWED') THEN RAISE EXCEPTION 'Closed defect evidence'; END IF;
        END IF;
      END IF;
      RETURN NEW;
    END $$""")
    for table in (
        "maintenance_work_orders",
        "driver_defects",
        "maintenance_cost_items",
        "maintenance_evidence",
    ):
        op.execute(
            f"CREATE TRIGGER maintenance_insert_guard BEFORE INSERT ON {table} FOR EACH ROW EXECUTE FUNCTION guard_maintenance_insert()"
        )
    op.execute("""CREATE FUNCTION apply_maintenance_availability() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.status='IN_PROGRESS' AND NEW.requires_vehicle_downtime THEN
        IF NEW.downtime_started_at IS NULL THEN RAISE EXCEPTION 'Downtime start required'; END IF;
        UPDATE vehicles SET status='MAINTENANCE' WHERE organization_id=NEW.organization_id AND id=NEW.vehicle_id AND status<>'INACTIVE';
      ELSIF NEW.status='COMPLETED' THEN
        IF NEW.odometer_at_completion IS NULL OR NEW.odometer_at_completion<0 OR length(trim(coalesce(NEW.work_performed,'')))=0 THEN RAISE EXCEPTION 'Completion evidence required'; END IF;
        IF NEW.odometer_at_completion < (SELECT greatest(coalesce(odometer,0),coalesce(reviewed_fuel_odometer,0),coalesce(maintenance_odometer,0)) FROM vehicles WHERE organization_id=NEW.organization_id AND id=NEW.vehicle_id) THEN RAISE EXCEPTION 'Odometer below trusted reading'; END IF;
        IF NEW.requires_vehicle_downtime AND NEW.downtime_ended_at IS NULL THEN RAISE EXCEPTION 'Downtime end required'; END IF;
        UPDATE vehicles SET maintenance_odometer=greatest(coalesce(maintenance_odometer,0),NEW.odometer_at_completion) WHERE organization_id=NEW.organization_id AND id=NEW.vehicle_id;
        IF NOT EXISTS(SELECT 1 FROM maintenance_work_orders w WHERE w.organization_id=NEW.organization_id AND w.vehicle_id=NEW.vehicle_id AND w.status='IN_PROGRESS' AND w.requires_vehicle_downtime) THEN
          UPDATE vehicles SET status=CASE WHEN EXISTS(SELECT 1 FROM vehicle_driver_assignments a WHERE a.organization_id=NEW.organization_id AND a.vehicle_id=NEW.vehicle_id AND a.is_current) THEN 'ASSIGNED' ELSE 'AVAILABLE' END WHERE organization_id=NEW.organization_id AND id=NEW.vehicle_id AND status='MAINTENANCE';
        END IF;
      END IF;
      RETURN NEW;
    END $$""")
    op.execute(
        "CREATE TRIGGER maintenance_availability AFTER UPDATE ON maintenance_work_orders FOR EACH ROW EXECUTE FUNCTION apply_maintenance_availability()"
    )


def downgrade():
    op.execute("DROP TRIGGER maintenance_dispatch_safety ON trips")
    op.execute("DROP FUNCTION guard_dispatch_maintenance()")
    op.execute("DROP TRIGGER maintenance_vehicle_safety ON vehicles")
    op.execute("DROP FUNCTION guard_vehicle_maintenance()")
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE {table}")
    op.execute("DROP FUNCTION guard_maintenance_history()")
    op.execute("DROP FUNCTION IF EXISTS guard_maintenance_insert()")
    op.execute("DROP FUNCTION IF EXISTS apply_maintenance_availability()")
    op.execute("ALTER TABLE vehicles DROP CONSTRAINT ck_vehicle_status")
    op.execute("UPDATE vehicles SET status='AVAILABLE' WHERE status='MAINTENANCE'")
    op.execute(
        "ALTER TABLE vehicles ADD CONSTRAINT ck_vehicle_status CHECK(status IN ('AVAILABLE','ASSIGNED','INACTIVE'))"
    )
    op.execute("ALTER TABLE vehicles DROP COLUMN maintenance_odometer")
    # Maintenance receipts remain immutable history; nullable context is retained on rollback.
