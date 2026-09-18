"""Operational revenue and shared append-only financial adjustments."""

from alembic import op

revision = "0010_trip_profitability"
down_revision = "0009_maintenance"
branch_labels = depends_on = None


def upgrade():
    op.execute("""CREATE TABLE trip_revenue (
      id uuid PRIMARY KEY, organization_id uuid NOT NULL, trip_id uuid NOT NULL,
      revenue_type text NOT NULL CHECK(revenue_type IN ('BASE_TRIP_CHARGE','SURCHARGE','WAITING_TIME','SPECIAL_HANDLING','OTHER')),
      amount numeric(12,2) NOT NULL CHECK(amount>0 AND amount<=10000000), currency text NOT NULL DEFAULT 'PHP' CHECK(currency='PHP'),
      description text CHECK(length(description)<=2000), reference_number varchar(120),
      status text NOT NULL DEFAULT 'SUBMITTED' CHECK(status IN ('SUBMITTED','REVIEWED','VOIDED')),
      created_by uuid NOT NULL REFERENCES users(id), created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      reviewed_by uuid REFERENCES users(id), reviewed_at timestamptz,
      voided_by uuid REFERENCES users(id), voided_at timestamptz, void_reason text,
      UNIQUE(organization_id,trip_id,id), UNIQUE(organization_id,id),
      FOREIGN KEY(organization_id,trip_id) REFERENCES trips(organization_id,id),
      CHECK(revenue_type<>'OTHER' OR length(trim(description))>=3 AND description IS NOT NULL),
      CHECK((reviewed_at IS NULL)=(reviewed_by IS NULL)),
      CHECK(status<>'REVIEWED' OR reviewed_at IS NOT NULL),
      CHECK(status<>'VOIDED' OR voided_at IS NOT NULL AND voided_by IS NOT NULL AND void_reason IS NOT NULL AND length(regexp_replace(void_reason,'[[:space:]]','','g'))>=10)
    )""")
    op.execute(
        "CREATE INDEX ix_revenue_trip ON trip_revenue(organization_id,trip_id,status,created_at,id)"
    )
    op.execute("""CREATE TABLE revenue_effective_values (
      revenue_id uuid PRIMARY KEY, organization_id uuid NOT NULL, trip_id uuid NOT NULL,
      sequence integer NOT NULL CHECK(sequence>0), amount numeric(12,2) NOT NULL CHECK(amount>0 AND amount<=10000000),
      description text, reference_number varchar(120), voided boolean NOT NULL DEFAULT false,
      FOREIGN KEY(organization_id,trip_id,revenue_id) REFERENCES trip_revenue(organization_id,trip_id,id)
    )""")
    op.execute("""ALTER TABLE closed_trip_adjustments ALTER COLUMN expense_id DROP NOT NULL,
      ALTER COLUMN source_revision DROP NOT NULL, ADD COLUMN revenue_id uuid,
      ADD CONSTRAINT adjustment_target CHECK((expense_id IS NOT NULL AND revenue_id IS NULL AND source_revision IS NOT NULL) OR (expense_id IS NULL AND revenue_id IS NOT NULL AND source_revision IS NULL)),
      ADD CONSTRAINT adjustment_revenue_fk FOREIGN KEY(organization_id,trip_id,revenue_id) REFERENCES trip_revenue(organization_id,trip_id,id),
      ADD CONSTRAINT adjustment_revenue_id UNIQUE(organization_id,revenue_id,id),
      ADD CONSTRAINT adjustment_revenue_sequence UNIQUE(organization_id,revenue_id,sequence),
      ADD CONSTRAINT adjustment_revenue_reverse FOREIGN KEY(organization_id,revenue_id,reverses_id) REFERENCES closed_trip_adjustments(organization_id,revenue_id,id)""")
    org = "NULLIF(current_setting('app.organization_id',true),'')::uuid"
    user = "NULLIF(current_setting('app.user_id',true),'')::uuid"
    member = f"EXISTS(SELECT 1 FROM organization_memberships m WHERE m.organization_id={org} AND m.user_id={user} AND m.active AND m.role IN ('OWNER','ADMIN','MANAGER','ACCOUNTING') AND NOT coalesce(m.permissions_json->'deny','[]'::jsonb) ? 'trip_financials.read')"
    admin = f"EXISTS(SELECT 1 FROM organization_memberships m WHERE m.organization_id={org} AND m.user_id={user} AND m.active AND m.role IN ('OWNER','ADMIN'))"
    for table in ("trip_revenue", "revenue_effective_values"):
        base = f"organization_id={org} AND {member}"
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY revenue_read ON {table} FOR SELECT USING ({base})")
        op.execute(f"CREATE POLICY revenue_insert ON {table} FOR INSERT WITH CHECK ({base})")
        op.execute(
            f"CREATE POLICY revenue_update ON {table} FOR UPDATE USING ({base}) WITH CHECK ({base})"
        )
    revenue_base = f"organization_id={org} AND {admin} AND EXISTS(SELECT 1 FROM trip_revenue r WHERE r.organization_id={org} AND r.id=closed_trip_adjustments.revenue_id)"
    op.execute(
        f"CREATE POLICY revenue_adjustment_read ON closed_trip_adjustments FOR SELECT USING ({revenue_base} AND NOT EXISTS(SELECT 1 FROM organization_memberships m WHERE m.organization_id={org} AND m.user_id={user} AND coalesce(m.permissions_json->'deny','[]'::jsonb) ? 'closed_trip_adjustments.read'))"
    )
    op.execute(
        f"CREATE POLICY revenue_adjustment_insert ON closed_trip_adjustments FOR INSERT WITH CHECK ({revenue_base})"
    )
    op.execute(
        "CREATE TRIGGER protect_revenue_projection BEFORE INSERT OR UPDATE OR DELETE ON revenue_effective_values FOR EACH ROW EXECUTE FUNCTION guard_adjustment_projection()"
    )
    op.execute("""CREATE FUNCTION guard_trip_revenue() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE m organization_memberships%ROWTYPE; permission text;
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Revenue history is immutable'; END IF;
      PERFORM id FROM organizations WHERE id=NEW.organization_id FOR UPDATE;
      SELECT * INTO m FROM organization_memberships WHERE organization_id=NEW.organization_id AND user_id=NULLIF(current_setting('app.user_id',true),'')::uuid AND active;
      permission := CASE WHEN TG_OP='INSERT' THEN 'trip_revenue.create' WHEN NEW.status='REVIEWED' THEN 'trip_revenue.review' ELSE 'trip_revenue.void' END;
      IF m.role IS NULL OR m.role NOT IN ('OWNER','ADMIN','MANAGER','ACCOUNTING') OR coalesce(m.permissions_json->'deny','[]'::jsonb) ? permission OR coalesce(m.permissions_json->'deny','[]'::jsonb) ? 'trip_financials.read' THEN RAISE EXCEPTION 'Revenue permission required'; END IF;
      IF NOT EXISTS(SELECT 1 FROM trips WHERE organization_id=NEW.organization_id AND id=NEW.trip_id AND current_status<>'CANCELLED') THEN RAISE EXCEPTION 'Cancelled or missing trip'; END IF;
      IF TG_OP='INSERT' THEN
        IF NEW.status<>'SUBMITTED' OR NEW.created_by<>m.user_id OR NEW.reviewed_at IS NOT NULL OR NEW.reviewed_by IS NOT NULL OR NEW.voided_at IS NOT NULL OR NEW.voided_by IS NOT NULL OR NEW.void_reason IS NOT NULL THEN RAISE EXCEPTION 'Invalid submission'; END IF;
      ELSE
        IF (to_jsonb(NEW)-ARRAY['status','reviewed_by','reviewed_at','voided_by','voided_at','void_reason']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['status','reviewed_by','reviewed_at','voided_by','voided_at','void_reason']) THEN RAISE EXCEPTION 'Original revenue is immutable'; END IF;
        IF OLD.status='VOIDED' OR EXISTS(SELECT 1 FROM revenue_effective_values WHERE revenue_id=OLD.id AND voided) THEN RAISE EXCEPTION 'Voided revenue'; END IF;
        IF NEW.status='REVIEWED' THEN
          IF OLD.status<>'SUBMITTED' OR NEW.reviewed_by IS DISTINCT FROM m.user_id OR NEW.reviewed_at IS NULL OR NEW.voided_by IS NOT NULL OR NEW.voided_at IS NOT NULL OR NEW.void_reason IS NOT NULL THEN RAISE EXCEPTION 'Invalid review'; END IF;
        ELSIF NEW.status='VOIDED' THEN
          IF EXISTS(SELECT 1 FROM trips WHERE id=NEW.trip_id AND organization_id=NEW.organization_id AND current_status='COMPLETED') THEN RAISE EXCEPTION 'Closed revenue requires adjustment'; END IF;
          IF NEW.voided_by IS DISTINCT FROM m.user_id OR NEW.voided_at IS NULL OR (NEW.reviewed_by,NEW.reviewed_at) IS DISTINCT FROM (OLD.reviewed_by,OLD.reviewed_at) THEN RAISE EXCEPTION 'Invalid void'; END IF;
        ELSE RAISE EXCEPTION 'Invalid revenue transition'; END IF;
      END IF;
      RETURN NEW;
    END $$""")
    op.execute(
        "CREATE TRIGGER revenue_guard BEFORE INSERT OR UPDATE OR DELETE ON trip_revenue FOR EACH ROW EXECUTE FUNCTION guard_trip_revenue()"
    )
    op.execute("DROP TRIGGER closed_adjustment_event ON closed_trip_adjustments")
    op.execute(
        "CREATE TRIGGER closed_adjustment_event BEFORE INSERT ON closed_trip_adjustments FOR EACH ROW WHEN (NEW.expense_id IS NOT NULL) EXECUTE FUNCTION apply_closed_adjustment()"
    )
    op.execute(
        "CREATE TRIGGER closed_adjustment_immutable BEFORE UPDATE OR DELETE ON closed_trip_adjustments FOR EACH ROW EXECUTE FUNCTION apply_closed_adjustment()"
    )
    op.execute("""CREATE FUNCTION apply_revenue_adjustment() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE r trip_revenue%ROWTYPE; p revenue_effective_values%ROWTYPE; m organization_memberships%ROWTYPE;
      previous closed_trip_adjustments%ROWTYPE; snapshot jsonb; permission text;
    BEGIN
      PERFORM id FROM organizations WHERE id=NEW.organization_id FOR UPDATE;
      SELECT * INTO m FROM organization_memberships WHERE organization_id=NEW.organization_id AND user_id=NULLIF(current_setting('app.user_id',true),'')::uuid AND active;
      permission:=CASE WHEN NEW.reverses_id IS NULL THEN 'closed_trip_adjustments.create' ELSE 'closed_trip_adjustments.reverse' END;
      IF m.role IS NULL OR m.role NOT IN ('OWNER','ADMIN') OR NEW.created_by IS DISTINCT FROM m.user_id OR coalesce(m.permissions_json->'deny','[]'::jsonb) ? permission OR coalesce(m.permissions_json->'deny','[]'::jsonb) ? 'closed_trip_adjustments.read' THEN RAISE EXCEPTION 'Adjustment permission required'; END IF;
      SELECT * INTO r FROM trip_revenue WHERE id=NEW.revenue_id AND organization_id=NEW.organization_id AND trip_id=NEW.trip_id;
      IF NOT FOUND OR r.status='VOIDED' THEN RAISE EXCEPTION 'Revenue not adjustable'; END IF;
      IF EXISTS(SELECT 1 FROM trips WHERE id=r.trip_id AND current_status='CANCELLED') THEN RAISE EXCEPTION 'Cancelled trip'; END IF;
      SELECT * INTO p FROM revenue_effective_values WHERE revenue_id=r.id AND organization_id=r.organization_id;
      IF NOT FOUND THEN p.sequence:=0; p.amount:=r.amount; p.description:=r.description; p.reference_number:=r.reference_number; p.voided:=false; END IF;
      snapshot:=jsonb_build_object('amount',p.amount::text,'description',p.description,'reference_number',p.reference_number,'voided',p.voided);
      IF NEW.field_name NOT IN ('amount','description','reference_number','voided') OR NEW.sequence<>p.sequence+1 OR NEW.old_value IS DISTINCT FROM snapshot->NEW.field_name THEN RAISE EXCEPTION 'Stale or invalid correction'; END IF;
      IF NEW.reverses_id IS NOT NULL THEN
        SELECT * INTO previous FROM closed_trip_adjustments a WHERE a.revenue_id=r.id AND a.organization_id=r.organization_id AND a.reverses_id IS NULL AND NOT EXISTS(SELECT 1 FROM closed_trip_adjustments b WHERE b.reverses_id=a.id AND b.organization_id=a.organization_id) ORDER BY a.sequence DESC LIMIT 1;
        IF previous.id IS DISTINCT FROM NEW.reverses_id OR NEW.field_name<>previous.field_name OR NEW.new_value IS DISTINCT FROM previous.old_value THEN RAISE EXCEPTION 'Reverse latest active entry first'; END IF;
      ELSE
        IF p.voided THEN RAISE EXCEPTION 'Reverse void first'; END IF;
        IF NEW.adjustment_type<>(CASE NEW.field_name WHEN 'amount' THEN 'AMOUNT_CORRECTION' WHEN 'description' THEN 'DESCRIPTION_CORRECTION' WHEN 'reference_number' THEN 'REFERENCE_CORRECTION' ELSE 'VOID_ADJUSTMENT' END) THEN RAISE EXCEPTION 'Invalid correction'; END IF;
      END IF;
      IF NEW.old_value IS NOT DISTINCT FROM NEW.new_value THEN RAISE EXCEPTION 'Unchanged value'; END IF;
      IF NEW.field_name='amount' THEN
        IF jsonb_typeof(NEW.new_value)<>'string' OR (NEW.new_value#>>'{}') !~ '^[0-9]{1,10}([.][0-9]{1,2})?$' THEN RAISE EXCEPTION 'Decimal string required'; END IF;
        p.amount:=(NEW.new_value#>>'{}')::numeric;
        IF p.amount<=0 OR p.amount>10000000 OR NEW.amount_delta IS DISTINCT FROM p.amount-(NEW.old_value#>>'{}')::numeric THEN RAISE EXCEPTION 'Invalid amount'; END IF;
      ELSIF NEW.field_name='voided' THEN
        IF jsonb_typeof(NEW.new_value)<>'boolean' OR (NEW.reverses_id IS NULL AND NEW.new_value<>'true'::jsonb) THEN RAISE EXCEPTION 'Invalid void'; END IF;
        p.voided:=(NEW.new_value#>>'{}')::boolean;
      ELSE
        IF NEW.new_value<>'null'::jsonb AND jsonb_typeof(NEW.new_value)<>'string' THEN RAISE EXCEPTION 'Text required'; END IF;
        IF NEW.field_name='description' THEN p.description:=NEW.new_value#>>'{}'; ELSE p.reference_number:=NEW.new_value#>>'{}'; END IF;
        IF length(p.description)>2000 OR length(p.reference_number)>120 OR (r.revenue_type='OTHER' AND length(trim(coalesce(p.description,'')))<3) THEN RAISE EXCEPTION 'Invalid text'; END IF;
      END IF;
      IF NEW.field_name<>'amount' AND NEW.amount_delta IS NOT NULL THEN RAISE EXCEPTION 'Unexpected delta'; END IF;
      INSERT INTO revenue_effective_values(revenue_id,organization_id,trip_id,sequence,amount,description,reference_number,voided)
      VALUES(r.id,r.organization_id,r.trip_id,NEW.sequence,p.amount,p.description,p.reference_number,p.voided)
      ON CONFLICT(revenue_id) DO UPDATE SET sequence=EXCLUDED.sequence,amount=EXCLUDED.amount,description=EXCLUDED.description,reference_number=EXCLUDED.reference_number,voided=EXCLUDED.voided;
      RETURN NEW;
    END $$""")
    op.execute(
        "CREATE TRIGGER revenue_adjustment_event BEFORE INSERT ON closed_trip_adjustments FOR EACH ROW WHEN (NEW.revenue_id IS NOT NULL) EXECUTE FUNCTION apply_revenue_adjustment()"
    )


def downgrade():
    # Only isolated/disposable rollback is tested; revenue data is removed by downgrade.
    op.execute("DROP TRIGGER revenue_adjustment_event ON closed_trip_adjustments")
    op.execute("DROP TRIGGER closed_adjustment_immutable ON closed_trip_adjustments")
    op.execute("DROP TRIGGER closed_adjustment_event ON closed_trip_adjustments")
    op.execute("DELETE FROM closed_trip_adjustments WHERE revenue_id IS NOT NULL")
    op.execute("DROP POLICY revenue_adjustment_read ON closed_trip_adjustments")
    op.execute("DROP POLICY revenue_adjustment_insert ON closed_trip_adjustments")
    op.execute(
        "ALTER TABLE closed_trip_adjustments DROP COLUMN revenue_id CASCADE, ALTER COLUMN expense_id SET NOT NULL, ALTER COLUMN source_revision SET NOT NULL"
    )
    op.execute(
        "CREATE TRIGGER closed_adjustment_event BEFORE INSERT OR UPDATE OR DELETE ON closed_trip_adjustments FOR EACH ROW EXECUTE FUNCTION apply_closed_adjustment()"
    )
    op.drop_table("revenue_effective_values")
    op.drop_table("trip_revenue")
    op.execute("DROP FUNCTION guard_trip_revenue()")
    op.execute("DROP FUNCTION apply_revenue_adjustment()")
