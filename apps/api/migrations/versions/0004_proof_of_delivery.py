"""Frozen proof-of-delivery schema and history protections."""

from alembic import op

revision = "0004_proof_of_delivery"
down_revision = "0003_dispatch_trip_lifecycle"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE trips ADD COLUMN pod_required boolean NOT NULL DEFAULT false")
    op.execute("ALTER TABLE trips DISABLE TRIGGER enforce_trip_workflow")
    op.execute(
        "UPDATE trips SET pod_required = true WHERE current_status NOT IN ('DELIVERED','COMPLETED','CANCELLED')"
    )
    op.execute("ALTER TABLE trips ENABLE TRIGGER enforce_trip_workflow")
    op.execute("ALTER TABLE trips ALTER COLUMN pod_required SET DEFAULT true")
    op.execute(
        "\nCREATE TABLE delivery_attempts (\n\tid UUID NOT NULL, \n\torganization_id UUID NOT NULL, \n\ttrip_id UUID NOT NULL, \n\tattempt_number INTEGER NOT NULL, \n\tstatus VARCHAR(20) NOT NULL, \n\tarrived_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tcompleted_at TIMESTAMP WITH TIME ZONE, \n\tcreated_by UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_delivery_attempt_identity UNIQUE (organization_id, trip_id, id), \n\tCONSTRAINT uq_delivery_attempt_number UNIQUE (organization_id, trip_id, attempt_number), \n\tFOREIGN KEY(organization_id, trip_id) REFERENCES trips (organization_id, id), \n\tCONSTRAINT ck_delivery_attempt_status CHECK (status IN ('IN_PROGRESS','DELIVERED','FAILED')), \n\tCONSTRAINT ck_delivery_attempt_completion CHECK (attempt_number > 0 AND ((status = 'IN_PROGRESS' AND completed_at IS NULL) OR (status <> 'IN_PROGRESS' AND completed_at IS NOT NULL))), \n\tFOREIGN KEY(organization_id) REFERENCES organizations (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id)\n)\n\n"
    )
    op.execute(
        "CREATE INDEX ix_attempt_trip_history ON delivery_attempts (organization_id, trip_id, created_at)"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_open_delivery_attempt ON delivery_attempts (organization_id, trip_id) WHERE status = 'IN_PROGRESS'"
    )
    op.execute(
        "\nCREATE TABLE delivery_evidence (\n\tid UUID NOT NULL, \n\torganization_id UUID NOT NULL, \n\ttrip_id UUID NOT NULL, \n\tdelivery_attempt_id UUID NOT NULL, \n\tevidence_type VARCHAR(30) NOT NULL, \n\tstorage_key VARCHAR(160) NOT NULL, \n\toriginal_filename VARCHAR(160) NOT NULL, \n\tcontent_type VARCHAR(30) NOT NULL, \n\tfile_size INTEGER NOT NULL, \n\tchecksum VARCHAR(64) NOT NULL, \n\tcaptured_at TIMESTAMP WITH TIME ZONE, \n\tuploaded_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tuploaded_by UUID NOT NULL, \n\tstatus VARCHAR(20) NOT NULL, \n\tsupersedes_id UUID, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_evidence_identity UNIQUE (organization_id, trip_id, delivery_attempt_id, id), \n\tFOREIGN KEY(organization_id, trip_id, delivery_attempt_id) REFERENCES delivery_attempts (organization_id, trip_id, id), \n\tFOREIGN KEY(organization_id, trip_id, delivery_attempt_id, supersedes_id) REFERENCES delivery_evidence (organization_id, trip_id, delivery_attempt_id, id), \n\tCONSTRAINT ck_evidence_type CHECK (evidence_type IN ('DELIVERY_PHOTO','SIGNATURE','EXCEPTION_PHOTO','OTHER_DELIVERY_EVIDENCE')), \n\tCONSTRAINT ck_evidence_status CHECK (status IN ('ACTIVE','SUPERSEDED')), \n\tCONSTRAINT ck_evidence_size CHECK (file_size > 0 AND file_size <= 5242880), \n\tFOREIGN KEY(organization_id) REFERENCES organizations (id), \n\tUNIQUE (storage_key), \n\tFOREIGN KEY(uploaded_by) REFERENCES users (id)\n)\n\n"
    )
    op.execute(
        "CREATE INDEX ix_evidence_attempt ON delivery_evidence (organization_id, delivery_attempt_id, uploaded_at)"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_active_signature ON delivery_evidence (organization_id, delivery_attempt_id) WHERE status = 'ACTIVE' AND evidence_type = 'SIGNATURE'"
    )
    op.execute(
        "\nCREATE TABLE proof_of_delivery (\n\tid UUID NOT NULL, \n\torganization_id UUID NOT NULL, \n\ttrip_id UUID NOT NULL, \n\tdelivery_attempt_id UUID NOT NULL, \n\trecipient_name VARCHAR(160) NOT NULL, \n\trecipient_role VARCHAR(120), \n\tconfirmed_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tconfirmed_by_driver_id UUID NOT NULL, \n\tconfirmed_by_user_id UUID NOT NULL, \n\tdriver_confirmed BOOLEAN NOT NULL, \n\tsignature_evidence_id UUID, \n\tnotes TEXT, \n\tstatus VARCHAR(20) NOT NULL, \n\treviewed_at TIMESTAMP WITH TIME ZONE, \n\treviewed_by UUID, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_pod_trip UNIQUE (organization_id, trip_id), \n\tCONSTRAINT uq_pod_attempt UNIQUE (organization_id, delivery_attempt_id), \n\tFOREIGN KEY(organization_id, trip_id, delivery_attempt_id) REFERENCES delivery_attempts (organization_id, trip_id, id), \n\tFOREIGN KEY(organization_id, trip_id, delivery_attempt_id, signature_evidence_id) REFERENCES delivery_evidence (organization_id, trip_id, delivery_attempt_id, id), \n\tFOREIGN KEY(organization_id, confirmed_by_driver_id) REFERENCES drivers (organization_id, id), \n\tCONSTRAINT ck_pod_confirmation CHECK (length(trim(recipient_name)) > 0 AND driver_confirmed), \n\tCONSTRAINT ck_pod_review CHECK ((status = 'SUBMITTED' AND reviewed_at IS NULL AND reviewed_by IS NULL) OR (status = 'REVIEWED' AND reviewed_at IS NOT NULL AND reviewed_by IS NOT NULL)), \n\tFOREIGN KEY(organization_id) REFERENCES organizations (id), \n\tFOREIGN KEY(confirmed_by_user_id) REFERENCES users (id), \n\tFOREIGN KEY(reviewed_by) REFERENCES users (id)\n)\n\n"
    )
    op.execute(
        "\nCREATE TABLE delivery_exceptions (\n\tid UUID NOT NULL, \n\torganization_id UUID NOT NULL, \n\ttrip_id UUID NOT NULL, \n\tdelivery_attempt_id UUID NOT NULL, \n\texception_type VARCHAR(30) NOT NULL, \n\tnotes TEXT, \n\tstatus VARCHAR(20) NOT NULL, \n\tcreated_by UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tresolved_at TIMESTAMP WITH TIME ZONE, \n\tresolved_by UUID, \n\tresolution_notes TEXT, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_exception_attempt UNIQUE (organization_id, delivery_attempt_id), \n\tFOREIGN KEY(organization_id, trip_id, delivery_attempt_id) REFERENCES delivery_attempts (organization_id, trip_id, id), \n\tCONSTRAINT ck_delivery_exception_type CHECK (exception_type IN ('RECIPIENT_UNAVAILABLE','WRONG_ADDRESS','INCOMPLETE_ADDRESS','DELIVERY_REJECTED','DAMAGED_CARGO','PARTIAL_DELIVERY','SITE_ACCESS_ISSUE','VEHICLE_ISSUE','DRIVER_ISSUE','OTHER')), \n\tCONSTRAINT ck_exception_other_notes CHECK (exception_type <> 'OTHER' OR (notes IS NOT NULL AND length(trim(notes)) >= 3)), \n\tCONSTRAINT ck_exception_resolution CHECK ((status = 'OPEN' AND resolved_at IS NULL AND resolved_by IS NULL AND resolution_notes IS NULL) OR (status = 'RETRY_AUTHORIZED' AND resolved_at IS NOT NULL AND resolved_by IS NOT NULL AND length(trim(resolution_notes)) >= 3)), \n\tFOREIGN KEY(organization_id) REFERENCES organizations (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id), \n\tFOREIGN KEY(resolved_by) REFERENCES users (id)\n)\n\n"
    )
    op.execute(
        "CREATE INDEX ix_exception_trip_status ON delivery_exceptions (organization_id, trip_id, status)"
    )
    org = "NULLIF(current_setting('app.organization_id', true), '')::uuid"
    for table in (
        "delivery_attempts",
        "delivery_evidence",
        "proof_of_delivery",
        "delivery_exceptions",
    ):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        policy = f"organization_id = {org} AND EXISTS (SELECT 1 FROM trips t WHERE t.id = {table}.trip_id AND t.organization_id = {org})"
        op.execute(f"CREATE POLICY {table}_select ON {table} FOR SELECT USING ({policy})")
        op.execute(f"CREATE POLICY {table}_insert ON {table} FOR INSERT WITH CHECK ({policy})")
        op.execute(
            f"CREATE POLICY {table}_update ON {table} FOR UPDATE USING ({policy}) WITH CHECK ({policy})"
        )
    op.execute("""CREATE FUNCTION guard_delivery_history() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE attempt_status text; trip_status text;
    BEGIN
      IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Delivery history cannot be deleted'; END IF;
      SELECT current_status INTO trip_status FROM trips WHERE id=NEW.trip_id AND organization_id=NEW.organization_id;
      IF trip_status IS NULL OR trip_status IN ('COMPLETED','CANCELLED') THEN RAISE EXCEPTION 'Trip is closed or inaccessible'; END IF;
      IF TG_TABLE_NAME = 'delivery_attempts' THEN
        IF TG_OP = 'INSERT' THEN
          IF NEW.status <> 'IN_PROGRESS' OR NOT EXISTS (SELECT 1 FROM trips WHERE id=NEW.trip_id AND organization_id=NEW.organization_id AND current_milestone IN ('ARRIVED_DELIVERY','UNLOADING_STARTED','UNLOADING_COMPLETED'))
          OR EXISTS (SELECT 1 FROM delivery_exceptions WHERE trip_id=NEW.trip_id AND organization_id=NEW.organization_id AND status='OPEN') THEN RAISE EXCEPTION 'Invalid delivery attempt'; END IF;
        ELSIF OLD.status <> 'IN_PROGRESS' OR NEW.status NOT IN ('DELIVERED','FAILED') OR NEW.completed_at IS NULL
          OR (to_jsonb(NEW)-ARRAY['status','completed_at']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['status','completed_at'])
        THEN RAISE EXCEPTION 'Delivery attempt history is immutable'; END IF;
      ELSIF TG_TABLE_NAME = 'delivery_evidence' THEN
        SELECT status INTO attempt_status FROM delivery_attempts WHERE id=NEW.delivery_attempt_id AND trip_id=NEW.trip_id AND organization_id=NEW.organization_id;
        IF attempt_status IS DISTINCT FROM 'IN_PROGRESS' THEN RAISE EXCEPTION 'Evidence attempt is closed'; END IF;
        IF TG_OP = 'UPDATE' AND (OLD.status <> 'ACTIVE' OR NEW.status <> 'SUPERSEDED'
          OR (to_jsonb(NEW)-'status') IS DISTINCT FROM (to_jsonb(OLD)-'status'))
        THEN RAISE EXCEPTION 'Evidence is immutable except explicit supersession'; END IF;
      ELSIF TG_TABLE_NAME = 'proof_of_delivery' THEN
        IF TG_OP = 'INSERT' THEN
          IF NEW.status <> 'SUBMITTED' OR NOT EXISTS (SELECT 1 FROM delivery_attempts WHERE id=NEW.delivery_attempt_id AND organization_id=NEW.organization_id AND trip_id=NEW.trip_id AND status='DELIVERED')
          OR NOT EXISTS (SELECT 1 FROM delivery_evidence WHERE delivery_attempt_id=NEW.delivery_attempt_id AND organization_id=NEW.organization_id AND trip_id=NEW.trip_id AND evidence_type='DELIVERY_PHOTO' AND status='ACTIVE')
          OR (NEW.signature_evidence_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM delivery_evidence WHERE id=NEW.signature_evidence_id AND delivery_attempt_id=NEW.delivery_attempt_id AND organization_id=NEW.organization_id AND evidence_type='SIGNATURE' AND status='ACTIVE'))
          THEN RAISE EXCEPTION 'POD requires successful attempt and evidence'; END IF;
        ELSIF OLD.status <> 'SUBMITTED' OR NEW.status <> 'REVIEWED' OR NEW.reviewed_at IS NULL OR NEW.reviewed_by IS NULL
          OR (to_jsonb(NEW)-ARRAY['status','reviewed_at','reviewed_by']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['status','reviewed_at','reviewed_by'])
        THEN RAISE EXCEPTION 'POD only permits explicit review'; END IF;
      ELSE
        IF TG_OP = 'INSERT' THEN
          IF NEW.status <> 'OPEN' OR NOT EXISTS (SELECT 1 FROM delivery_attempts WHERE id=NEW.delivery_attempt_id AND organization_id=NEW.organization_id AND trip_id=NEW.trip_id AND status='FAILED') THEN RAISE EXCEPTION 'Exception requires failed attempt'; END IF;
        ELSIF OLD.status <> 'OPEN' OR NEW.status <> 'RETRY_AUTHORIZED' OR NEW.resolved_at IS NULL OR NEW.resolved_by IS NULL OR NEW.resolution_notes IS NULL
          OR (to_jsonb(NEW)-ARRAY['status','resolved_at','resolved_by','resolution_notes']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['status','resolved_at','resolved_by','resolution_notes'])
        THEN RAISE EXCEPTION 'Exception only permits explicit resolution'; END IF;
      END IF;
      RETURN NEW;
    END $$""")
    for table in (
        "delivery_attempts",
        "delivery_evidence",
        "proof_of_delivery",
        "delivery_exceptions",
    ):
        op.execute(
            f"CREATE TRIGGER protect_{table} BEFORE INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION guard_delivery_history()"
        )
    op.execute("""CREATE FUNCTION guard_trip_pod() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.pod_required IS DISTINCT FROM OLD.pod_required THEN RAISE EXCEPTION 'POD policy cannot be bypassed'; END IF;
      IF NEW.current_status = 'DELIVERED' AND OLD.current_status <> 'DELIVERED' AND NOT EXISTS (
        SELECT 1 FROM proof_of_delivery p JOIN delivery_attempts a ON a.id=p.delivery_attempt_id AND a.organization_id=p.organization_id AND a.trip_id=p.trip_id
        WHERE p.trip_id=NEW.id AND p.organization_id=NEW.organization_id AND a.status='DELIVERED')
      THEN RAISE EXCEPTION 'Delivery requires POD'; END IF;
      IF NEW.current_status = 'COMPLETED' AND NEW.pod_required AND NOT EXISTS (
        SELECT 1 FROM proof_of_delivery WHERE trip_id=NEW.id AND organization_id=NEW.organization_id AND status='REVIEWED')
      THEN RAISE EXCEPTION 'Completion requires reviewed POD'; END IF;
      IF NEW.current_milestone IS DISTINCT FROM OLD.current_milestone AND NEW.current_status <> 'CANCELLED'
        AND EXISTS (SELECT 1 FROM delivery_exceptions WHERE trip_id=NEW.id AND organization_id=NEW.organization_id AND status='OPEN')
      THEN RAISE EXCEPTION 'Unresolved delivery issue blocks progress'; END IF;
      RETURN NEW;
    END $$""")
    op.execute(
        "CREATE TRIGGER enforce_trip_pod BEFORE UPDATE ON trips FOR EACH ROW EXECUTE FUNCTION guard_trip_pod()"
    )
    op.execute("""CREATE FUNCTION check_delivery_outcome() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.status = 'DELIVERED' AND NOT EXISTS (SELECT 1 FROM proof_of_delivery WHERE delivery_attempt_id=NEW.id AND organization_id=NEW.organization_id AND trip_id=NEW.trip_id) THEN RAISE EXCEPTION 'Successful attempt requires POD'; END IF;
      IF NEW.status = 'FAILED' AND NOT EXISTS (SELECT 1 FROM delivery_exceptions WHERE delivery_attempt_id=NEW.id AND organization_id=NEW.organization_id AND trip_id=NEW.trip_id) THEN RAISE EXCEPTION 'Failed attempt requires exception'; END IF;
      RETURN NEW;
    END $$""")
    op.execute(
        "CREATE CONSTRAINT TRIGGER delivery_outcome_integrity AFTER UPDATE ON delivery_attempts DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_delivery_outcome()"
    )


def downgrade():
    op.execute("DROP TRIGGER enforce_trip_pod ON trips")
    op.execute("DROP FUNCTION guard_trip_pod()")
    for table in (
        "delivery_exceptions",
        "proof_of_delivery",
        "delivery_evidence",
        "delivery_attempts",
    ):
        op.drop_table(table)
    op.execute("DROP FUNCTION check_delivery_outcome()")
    op.execute("DROP FUNCTION guard_delivery_history()")
    op.drop_column("trips", "pod_required")
