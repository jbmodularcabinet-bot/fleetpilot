"""Frozen dispatch schema, forced tenant/driver RLS and workflow guards."""

from alembic import op

revision = "0003_dispatch_trip_lifecycle"
down_revision = "0002_fleet_master"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint("uq_customer_tenant_id", "customers", ["organization_id", "id"])
    op.execute(
        "\nCREATE TABLE trips (\n\tid UUID NOT NULL, \n\torganization_id UUID NOT NULL, \n\ttrip_number VARCHAR(40) NOT NULL, \n\tnumber_sequence INTEGER NOT NULL, \n\tversion INTEGER NOT NULL, \n\tcustomer_id UUID NOT NULL, \n\tpickup_name VARCHAR(160) NOT NULL, \n\tpickup_address TEXT NOT NULL, \n\tpickup_latitude NUMERIC(9, 6), \n\tpickup_longitude NUMERIC(9, 6), \n\tpickup_contact_name VARCHAR(120), \n\tpickup_contact_phone VARCHAR(30), \n\tdelivery_name VARCHAR(160) NOT NULL, \n\tdelivery_address TEXT NOT NULL, \n\tdelivery_latitude NUMERIC(9, 6), \n\tdelivery_longitude NUMERIC(9, 6), \n\tdelivery_contact_name VARCHAR(120), \n\tdelivery_contact_phone VARCHAR(30), \n\tscheduled_pickup_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tscheduled_delivery_at TIMESTAMP WITH TIME ZONE, \n\tvehicle_id UUID, \n\tdriver_id UUID, \n\tcurrent_status VARCHAR(20) NOT NULL, \n\tcurrent_milestone VARCHAR(40) NOT NULL, \n\treference_number VARCHAR(120), \n\tcustomer_reference VARCHAR(120), \n\tcargo_description TEXT, \n\tcargo_weight NUMERIC(14, 3), \n\tcargo_weight_unit VARCHAR(10), \n\tspecial_instructions TEXT, \n\tdispatcher_notes TEXT, \n\tcreated_by UUID NOT NULL, \n\tupdated_by UUID NOT NULL, \n\tcancelled_at TIMESTAMP WITH TIME ZONE, \n\tcancelled_by UUID, \n\tcancellation_reason TEXT, \n\tcompleted_at TIMESTAMP WITH TIME ZONE, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_trip_tenant_id UNIQUE (organization_id, id), \n\tCONSTRAINT uq_trip_number UNIQUE (organization_id, trip_number), \n\tCONSTRAINT uq_trip_sequence UNIQUE (organization_id, number_sequence), \n\tCONSTRAINT fk_trip_customer_tenant FOREIGN KEY(organization_id, customer_id) REFERENCES customers (organization_id, id), \n\tCONSTRAINT fk_trip_vehicle_tenant FOREIGN KEY(organization_id, vehicle_id) REFERENCES vehicles (organization_id, id), \n\tCONSTRAINT fk_trip_driver_tenant FOREIGN KEY(organization_id, driver_id) REFERENCES drivers (organization_id, id), \n\tCONSTRAINT ck_trip_status CHECK (current_status IN ('SCHEDULED','DISPATCHED','PICKUP','LOADED','IN_TRANSIT','DELIVERED','COMPLETED','CANCELLED')), \n\tCONSTRAINT ck_trip_assignment_pair CHECK ((vehicle_id IS NULL) = (driver_id IS NULL)), \n\tCONSTRAINT ck_trip_schedule CHECK (scheduled_delivery_at IS NULL OR scheduled_delivery_at > scheduled_pickup_at), \n\tCONSTRAINT ck_trip_versions CHECK (version > 0 AND number_sequence > 0), \n\tFOREIGN KEY(organization_id) REFERENCES organizations (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id), \n\tFOREIGN KEY(updated_by) REFERENCES users (id), \n\tFOREIGN KEY(cancelled_by) REFERENCES users (id)\n)\n\n"
    )
    op.execute("CREATE INDEX ix_trip_created ON trips (organization_id, created_at)")
    op.execute(
        "CREATE INDEX ix_trip_customer ON trips (organization_id, customer_id, scheduled_pickup_at)"
    )
    op.execute(
        "CREATE INDEX ix_trip_driver ON trips (organization_id, driver_id, scheduled_pickup_at)"
    )
    op.execute("CREATE INDEX ix_trip_schedule ON trips (organization_id, scheduled_pickup_at)")
    op.execute(
        "CREATE INDEX ix_trip_status_schedule ON trips (organization_id, current_status, scheduled_pickup_at)"
    )
    op.execute(
        "CREATE INDEX ix_trip_vehicle ON trips (organization_id, vehicle_id, scheduled_pickup_at)"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_active_trip_driver_id ON trips (organization_id, driver_id) WHERE current_status NOT IN ('SCHEDULED','COMPLETED','CANCELLED')"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_active_trip_vehicle_id ON trips (organization_id, vehicle_id) WHERE current_status NOT IN ('SCHEDULED','COMPLETED','CANCELLED')"
    )
    op.execute(
        "\nCREATE TABLE trip_milestones (\n\tid UUID NOT NULL, \n\torganization_id UUID NOT NULL, \n\ttrip_id UUID NOT NULL, \n\tevent_number INTEGER NOT NULL, \n\tmilestone_type VARCHAR(40) NOT NULL, \n\toccurred_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\trecorded_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\trecorded_by UUID NOT NULL, \n\tsource VARCHAR(20) NOT NULL, \n\tnotes TEXT, \n\tmetadata_json JSONB NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_milestone_trip_tenant FOREIGN KEY(organization_id, trip_id) REFERENCES trips (organization_id, id), \n\tCONSTRAINT uq_milestone_order UNIQUE (organization_id, trip_id, event_number), \n\tCONSTRAINT ck_milestone_source CHECK (source IN ('OWNER_WEB','DISPATCHER_WEB','DRIVER_APP','SYSTEM')), \n\tFOREIGN KEY(organization_id) REFERENCES organizations (id), \n\tFOREIGN KEY(recorded_by) REFERENCES users (id)\n)\n\n"
    )
    op.execute(
        "CREATE INDEX ix_milestone_timeline ON trip_milestones (organization_id, trip_id, occurred_at)"
    )
    op.execute(
        "\nCREATE TABLE trip_assignments (\n\tid UUID NOT NULL, \n\torganization_id UUID NOT NULL, \n\ttrip_id UUID NOT NULL, \n\tvehicle_id UUID NOT NULL, \n\tdriver_id UUID NOT NULL, \n\tassigned_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tended_at TIMESTAMP WITH TIME ZONE, \n\tis_current BOOLEAN NOT NULL, \n\tcreated_by UUID NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_trip_assignment_trip FOREIGN KEY(organization_id, trip_id) REFERENCES trips (organization_id, id), \n\tCONSTRAINT fk_trip_assignment_vehicle FOREIGN KEY(organization_id, vehicle_id) REFERENCES vehicles (organization_id, id), \n\tCONSTRAINT fk_trip_assignment_driver FOREIGN KEY(organization_id, driver_id) REFERENCES drivers (organization_id, id), \n\tCONSTRAINT ck_trip_assignment_lifecycle CHECK ((is_current AND ended_at IS NULL) OR (NOT is_current AND ended_at IS NOT NULL AND ended_at >= assigned_at)), \n\tFOREIGN KEY(organization_id) REFERENCES organizations (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id)\n)\n\n"
    )
    op.execute(
        "CREATE INDEX ix_trip_assignment_history ON trip_assignments (organization_id, trip_id, assigned_at)"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_current_trip_assignment ON trip_assignments (organization_id, trip_id) WHERE is_current"
    )
    org = "NULLIF(current_setting('app.organization_id', true), '')::uuid"
    user = "NULLIF(current_setting('app.user_id', true), '')::uuid"
    member = f"EXISTS (SELECT 1 FROM organization_memberships m WHERE m.organization_id = {org} AND m.user_id = {user} AND m.active AND m.role <> 'DRIVER')"
    driver = f"driver_id IN (SELECT d.id FROM drivers d WHERE d.organization_id = {org} AND d.user_id = {user} AND d.employment_status = 'ACTIVE')"
    access = f"organization_id = {org} AND ({member} OR {driver})"
    for table in ("trips", "trip_milestones", "trip_assignments"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        policy = (
            access
            if table == "trips"
            else f"organization_id = {org} AND EXISTS (SELECT 1 FROM trips t WHERE t.id = {table}.trip_id AND t.organization_id = {org})"
        )
        op.execute(f"CREATE POLICY {table}_select ON {table} FOR SELECT USING ({policy})")
        insert = (
            f"organization_id = {org} AND ({member})"
            if table in ("trips", "trip_assignments")
            else f"{policy} AND recorded_by = {user}"
        )
        op.execute(f"CREATE POLICY {table}_insert ON {table} FOR INSERT WITH CHECK ({insert})")
        if table != "trip_milestones":
            update = policy if table == "trips" else f"{policy} AND ({member})"
            op.execute(
                f"CREATE POLICY {table}_update ON {table} FOR UPDATE USING ({update}) WITH CHECK ({update})"
            )
    op.execute("""CREATE FUNCTION guard_trip_history() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'Trip milestone history is immutable'; END $$""")
    op.execute(
        "CREATE TRIGGER immutable_trip_milestones BEFORE UPDATE OR DELETE ON trip_milestones FOR EACH ROW EXECUTE FUNCTION guard_trip_history()"
    )
    op.execute("""CREATE FUNCTION guard_trip_assignment_history() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP = 'DELETE' OR NOT OLD.is_current OR NEW.is_current OR NEW.ended_at IS NULL
      OR (to_jsonb(NEW) - 'is_current' - 'ended_at') IS DISTINCT FROM (to_jsonb(OLD) - 'is_current' - 'ended_at')
      THEN RAISE EXCEPTION 'Trip assignment history only permits explicit closure'; END IF;
      RETURN NEW;
    END $$""")
    op.execute(
        "CREATE TRIGGER immutable_trip_assignments BEFORE UPDATE OR DELETE ON trip_assignments FOR EACH ROW EXECUTE FUNCTION guard_trip_assignment_history()"
    )
    op.execute("""CREATE FUNCTION guard_trip_workflow() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE expected_status text;
    BEGIN
      IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Trips cannot be deleted'; END IF;
      IF TG_OP = 'UPDATE' THEN
        IF OLD.current_status IN ('COMPLETED','CANCELLED') THEN RAISE EXCEPTION 'Closed trips are immutable'; END IF;
        IF ROW(NEW.organization_id,NEW.id,NEW.trip_number,NEW.number_sequence,NEW.created_by,NEW.created_at)
           IS DISTINCT FROM ROW(OLD.organization_id,OLD.id,OLD.trip_number,OLD.number_sequence,OLD.created_by,OLD.created_at)
        THEN RAISE EXCEPTION 'Trip identity is immutable'; END IF;
        IF NEW.current_milestone IS DISTINCT FROM OLD.current_milestone AND NOT (
          (NEW.current_milestone = 'CANCELLED' AND OLD.current_milestone NOT IN ('DELIVERED','COMPLETED','CANCELLED')) OR
          (OLD.current_milestone, NEW.current_milestone) IN (
            ('SCHEDULED','DISPATCHED'),('DISPATCHED','EN_ROUTE_TO_PICKUP'),('EN_ROUTE_TO_PICKUP','ARRIVED_PICKUP'),
            ('ARRIVED_PICKUP','LOADING_STARTED'),('LOADING_STARTED','LOADING_COMPLETED'),('LOADING_COMPLETED','EN_ROUTE_TO_DELIVERY'),
            ('EN_ROUTE_TO_DELIVERY','ARRIVED_DELIVERY'),('ARRIVED_DELIVERY','UNLOADING_STARTED'),
            ('UNLOADING_STARTED','UNLOADING_COMPLETED'),('UNLOADING_COMPLETED','DELIVERED'),('DELIVERED','COMPLETED')))
        THEN RAISE EXCEPTION 'Invalid trip transition'; END IF;
        IF OLD.current_status <> 'SCHEDULED' AND
          (to_jsonb(NEW) - ARRAY['current_status','current_milestone','version','updated_at','updated_by','dispatcher_notes','vehicle_id','driver_id','cancelled_at','cancelled_by','cancellation_reason','completed_at'])
          IS DISTINCT FROM
          (to_jsonb(OLD) - ARRAY['current_status','current_milestone','version','updated_at','updated_by','dispatcher_notes','vehicle_id','driver_id','cancelled_at','cancelled_by','cancellation_reason','completed_at'])
        THEN RAISE EXCEPTION 'Dispatched operational fields are frozen'; END IF;
        IF OLD.current_milestone NOT IN ('SCHEDULED','DISPATCHED') AND ROW(NEW.vehicle_id,NEW.driver_id) IS DISTINCT FROM ROW(OLD.vehicle_id,OLD.driver_id)
        THEN RAISE EXCEPTION 'Cannot reassign after travel begins'; END IF;
      ELSIF NEW.current_status <> 'SCHEDULED' OR NEW.current_milestone <> 'SCHEDULED' THEN
        RAISE EXCEPTION 'Trips must begin scheduled';
      END IF;
      expected_status := CASE NEW.current_milestone
        WHEN 'SCHEDULED' THEN 'SCHEDULED' WHEN 'DISPATCHED' THEN 'DISPATCHED'
        WHEN 'EN_ROUTE_TO_PICKUP' THEN 'PICKUP' WHEN 'ARRIVED_PICKUP' THEN 'PICKUP' WHEN 'LOADING_STARTED' THEN 'PICKUP'
        WHEN 'LOADING_COMPLETED' THEN 'LOADED'
        WHEN 'EN_ROUTE_TO_DELIVERY' THEN 'IN_TRANSIT' WHEN 'ARRIVED_DELIVERY' THEN 'IN_TRANSIT'
        WHEN 'UNLOADING_STARTED' THEN 'IN_TRANSIT' WHEN 'UNLOADING_COMPLETED' THEN 'IN_TRANSIT'
        WHEN 'DELIVERED' THEN 'DELIVERED' WHEN 'COMPLETED' THEN 'COMPLETED' WHEN 'CANCELLED' THEN 'CANCELLED' ELSE NULL END;
      IF expected_status IS NULL OR NEW.current_status <> expected_status THEN RAISE EXCEPTION 'Status and milestone disagree'; END IF;
      IF NEW.current_status NOT IN ('SCHEDULED','CANCELLED') AND (NEW.vehicle_id IS NULL OR NEW.driver_id IS NULL) THEN RAISE EXCEPTION 'Trip requires assignment'; END IF;
      IF (NEW.current_status = 'COMPLETED') <> (NEW.completed_at IS NOT NULL) THEN RAISE EXCEPTION 'Completion timestamp required'; END IF;
      IF NEW.current_status = 'CANCELLED' THEN
        IF NEW.cancelled_at IS NULL OR NEW.cancelled_by IS NULL OR length(trim(NEW.cancellation_reason)) < 3 OR NEW.cancellation_reason IS NULL THEN RAISE EXCEPTION 'Cancellation details required'; END IF;
      ELSIF NEW.cancelled_at IS NOT NULL OR NEW.cancelled_by IS NOT NULL OR NEW.cancellation_reason IS NOT NULL THEN RAISE EXCEPTION 'Unexpected cancellation data'; END IF;
      RETURN NEW;
    END $$""")
    op.execute(
        "CREATE TRIGGER enforce_trip_workflow BEFORE INSERT OR UPDATE OR DELETE ON trips FOR EACH ROW EXECUTE FUNCTION guard_trip_workflow()"
    )
    op.execute("""CREATE FUNCTION guard_trip_resource_status() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_TABLE_NAME = 'customers' THEN
        IF NEW.status = 'INACTIVE' AND EXISTS (SELECT 1 FROM trips WHERE organization_id=NEW.organization_id AND customer_id=NEW.id AND current_status NOT IN ('COMPLETED','CANCELLED')) THEN RAISE EXCEPTION 'Customer has open trips'; END IF;
      ELSIF TG_TABLE_NAME = 'vehicles' THEN
        IF NEW.status = 'INACTIVE' AND EXISTS (SELECT 1 FROM trips WHERE organization_id=NEW.organization_id AND vehicle_id=NEW.id AND current_status NOT IN ('COMPLETED','CANCELLED')) THEN RAISE EXCEPTION 'Vehicle has open trips'; END IF;
      ELSE
        IF NEW.employment_status <> 'ACTIVE' AND EXISTS (SELECT 1 FROM trips WHERE organization_id=NEW.organization_id AND driver_id=NEW.id AND current_status NOT IN ('COMPLETED','CANCELLED')) THEN RAISE EXCEPTION 'Driver has open trips'; END IF;
      END IF;
      RETURN NEW;
    END $$""")
    op.execute(
        "CREATE TRIGGER check_vehicle_open_trips BEFORE UPDATE ON vehicles FOR EACH ROW EXECUTE FUNCTION guard_trip_resource_status()"
    )
    op.execute(
        "CREATE TRIGGER check_driver_open_trips BEFORE UPDATE ON drivers FOR EACH ROW EXECUTE FUNCTION guard_trip_resource_status()"
    )

    op.execute(
        "CREATE TRIGGER check_customer_open_trips BEFORE UPDATE ON customers FOR EACH ROW EXECUTE FUNCTION guard_trip_resource_status()"
    )


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS check_customer_open_trips ON customers")
    op.execute("DROP TRIGGER IF EXISTS check_vehicle_open_trips ON vehicles")
    op.execute("DROP TRIGGER IF EXISTS check_driver_open_trips ON drivers")
    op.execute("DROP FUNCTION IF EXISTS guard_trip_resource_status()")
    op.drop_table("trip_assignments")
    op.drop_table("trip_milestones")
    op.drop_table("trips")
    for function in ("guard_trip_assignment_history", "guard_trip_history", "guard_trip_workflow"):
        op.execute(f"DROP FUNCTION IF EXISTS {function}()")
    op.drop_constraint("uq_customer_tenant_id", "customers", type_="unique")
