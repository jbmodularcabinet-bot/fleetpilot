"""Append-only closed-trip adjustments and a guarded effective projection."""

from alembic import op

revision = "0008_closed_trip_adjustments"
down_revision = "0007_trip_expenses"
branch_labels = depends_on = None


def upgrade():
    op.execute("""CREATE TABLE expense_effective_values (
      organization_id uuid NOT NULL, trip_id uuid NOT NULL, expense_id uuid PRIMARY KEY,
      sequence integer NOT NULL CHECK(sequence>0), amount numeric(12,2) NOT NULL CHECK(amount>0 AND amount<=10000000),
      odometer numeric(9,1), description text, reference_number varchar(120), voided boolean NOT NULL DEFAULT false,
      FOREIGN KEY(organization_id,trip_id,expense_id) REFERENCES trip_expenses(organization_id,trip_id,id),
      CHECK(odometer IS NULL OR odometer BETWEEN 0 AND 10000000)
    )""")
    op.execute("""CREATE TABLE closed_trip_adjustments (
      id uuid PRIMARY KEY, organization_id uuid NOT NULL, trip_id uuid NOT NULL, expense_id uuid NOT NULL,
      source_revision integer NOT NULL, sequence integer NOT NULL CHECK(sequence>0),
      adjustment_type varchar(40) NOT NULL CHECK(adjustment_type IN ('AMOUNT_CORRECTION','REFERENCE_CORRECTION','DESCRIPTION_CORRECTION','ODOMETER_CORRECTION','VOID_ADJUSTMENT','REVERSAL')),
      field_name varchar(30) NOT NULL CHECK(field_name IN ('amount','reference_number','description','odometer','voided')),
      old_value jsonb NOT NULL, new_value jsonb NOT NULL, amount_delta numeric(12,2),
      reason text NOT NULL CHECK(length(regexp_replace(reason,'[[:space:]]','','g'))>=10 AND length(reason)<=2000),
      created_by uuid NOT NULL REFERENCES users(id), created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      reverses_id uuid, UNIQUE(organization_id,expense_id,id), UNIQUE(organization_id,expense_id,sequence),
      UNIQUE(reverses_id),
      FOREIGN KEY(organization_id,trip_id,expense_id) REFERENCES trip_expenses(organization_id,trip_id,id),
      FOREIGN KEY(organization_id,expense_id,source_revision) REFERENCES expense_revisions(organization_id,expense_id,revision_number),
      FOREIGN KEY(organization_id,expense_id,reverses_id) REFERENCES closed_trip_adjustments(organization_id,expense_id,id),
      CHECK((adjustment_type='REVERSAL')=(reverses_id IS NOT NULL))
    )""")
    op.execute(
        "CREATE INDEX ix_adjustment_trip ON closed_trip_adjustments(organization_id,trip_id,created_at,id)"
    )
    org = "NULLIF(current_setting('app.organization_id',true),'')::uuid"
    user = "NULLIF(current_setting('app.user_id',true),'')::uuid"
    member = f"EXISTS(SELECT 1 FROM organization_memberships m WHERE m.organization_id={org} AND m.user_id={user} AND m.active AND m.role IN ('OWNER','ADMIN'))"
    for table in ("closed_trip_adjustments", "expense_effective_values"):
        base = f"organization_id={org} AND EXISTS(SELECT 1 FROM trip_expenses e WHERE e.id={table}.expense_id AND e.organization_id={org})"
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        read = (
            base
            if table == "expense_effective_values"
            else base
            + " AND "
            + member
            + f" AND NOT EXISTS(SELECT 1 FROM organization_memberships m WHERE m.organization_id={org} AND m.user_id={user} AND coalesce(m.permissions_json->'deny','[]'::jsonb) ? 'closed_trip_adjustments.read')"
        )
        op.execute(f"CREATE POLICY adjustment_read ON {table} FOR SELECT USING ({read})")
        op.execute(
            f"CREATE POLICY adjustment_insert ON {table} FOR INSERT WITH CHECK ({base} AND {member})"
        )
        if table == "expense_effective_values":
            op.execute(
                f"CREATE POLICY adjustment_update ON {table} FOR UPDATE USING ({base} AND {member}) WITH CHECK ({base} AND {member})"
            )
    op.execute("""CREATE FUNCTION guard_adjustment_projection() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF pg_trigger_depth()<>2 OR TG_OP='DELETE' THEN RAISE EXCEPTION 'Effective values require an adjustment event'; END IF;
      RETURN NEW;
    END $$""")
    op.execute(
        "CREATE TRIGGER protect_effective_values BEFORE INSERT OR UPDATE OR DELETE ON expense_effective_values FOR EACH ROW EXECUTE FUNCTION guard_adjustment_projection()"
    )
    op.execute("""CREATE FUNCTION apply_closed_adjustment() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE e trip_expenses%ROWTYPE; r expense_revisions%ROWTYPE; p expense_effective_values%ROWTYPE;
      previous closed_trip_adjustments%ROWTYPE; snapshot jsonb; member organization_memberships%ROWTYPE; permission text;
    BEGIN
      IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Adjustment history is immutable'; END IF;
      PERFORM id FROM organizations WHERE id=NEW.organization_id FOR UPDATE;
      SELECT * INTO member FROM organization_memberships WHERE organization_id=NEW.organization_id AND user_id=NULLIF(current_setting('app.user_id',true),'')::uuid AND active;
      permission := CASE WHEN NEW.reverses_id IS NULL THEN 'closed_trip_adjustments.create' ELSE 'closed_trip_adjustments.reverse' END;
      IF member.role IS NULL OR member.role NOT IN ('OWNER','ADMIN') OR coalesce(member.permissions_json->'deny','[]'::jsonb) ? permission OR coalesce(member.permissions_json->'deny','[]'::jsonb) ? 'closed_trip_adjustments.read' OR NEW.created_by IS DISTINCT FROM member.user_id THEN RAISE EXCEPTION 'Adjustment permission required'; END IF;
      SELECT * INTO e FROM trip_expenses WHERE id=NEW.expense_id AND organization_id=NEW.organization_id;
      IF NOT FOUND OR e.status='VOIDED' OR e.trip_id<>NEW.trip_id OR e.current_revision<>NEW.source_revision OR NOT EXISTS(SELECT 1 FROM trips WHERE id=e.trip_id AND organization_id=e.organization_id AND current_status='COMPLETED') THEN RAISE EXCEPTION 'Adjustment requires a completed trip and original expense'; END IF;
      SELECT * INTO r FROM expense_revisions WHERE expense_id=e.id AND organization_id=e.organization_id AND revision_number=e.current_revision;
      SELECT * INTO p FROM expense_effective_values WHERE expense_id=e.id AND organization_id=e.organization_id;
      IF NOT FOUND THEN
        p.sequence:=0; p.amount:=r.amount; p.odometer:=r.odometer; p.description:=r.description; p.reference_number:=r.reference_number; p.voided:=false;
      END IF;
      snapshot:=jsonb_build_object('amount',p.amount::text,'odometer',p.odometer::text,'description',p.description,'reference_number',p.reference_number,'voided',p.voided);
      IF NEW.sequence<>p.sequence+1 OR NEW.old_value IS DISTINCT FROM snapshot->NEW.field_name THEN RAISE EXCEPTION 'Stale adjustment'; END IF;
      IF NEW.reverses_id IS NOT NULL THEN
        SELECT * INTO previous FROM closed_trip_adjustments a WHERE a.expense_id=e.id AND a.organization_id=e.organization_id AND a.reverses_id IS NULL AND NOT EXISTS(SELECT 1 FROM closed_trip_adjustments b WHERE b.reverses_id=a.id AND b.organization_id=a.organization_id) ORDER BY a.sequence DESC LIMIT 1;
        IF previous.id IS DISTINCT FROM NEW.reverses_id OR NEW.field_name<>previous.field_name OR NEW.new_value IS DISTINCT FROM previous.old_value THEN RAISE EXCEPTION 'Reverse latest active adjustment first'; END IF;
      ELSE
        IF p.voided THEN RAISE EXCEPTION 'Reverse void before further adjustment'; END IF;
        IF NEW.adjustment_type<>(CASE NEW.field_name WHEN 'amount' THEN 'AMOUNT_CORRECTION' WHEN 'odometer' THEN 'ODOMETER_CORRECTION' WHEN 'description' THEN 'DESCRIPTION_CORRECTION' WHEN 'reference_number' THEN 'REFERENCE_CORRECTION' ELSE 'VOID_ADJUSTMENT' END) THEN RAISE EXCEPTION 'Invalid adjustment type'; END IF;
      END IF;
      IF NEW.new_value IS NOT DISTINCT FROM NEW.old_value THEN RAISE EXCEPTION 'No change'; END IF;
      IF NEW.field_name IN ('amount','odometer') THEN
        IF NEW.new_value<>'null'::jsonb AND (jsonb_typeof(NEW.new_value)<>'string' OR (NEW.new_value#>>'{}') !~ '^[0-9]{1,10}([.][0-9]{1,2})?$') THEN RAISE EXCEPTION 'Decimal string required'; END IF;
        IF NEW.field_name='amount' THEN
          IF NEW.new_value='null'::jsonb THEN RAISE EXCEPTION 'Amount required'; END IF;
          p.amount:=(NEW.new_value#>>'{}')::numeric;
          IF p.amount<=0 OR p.amount>10000000 OR NEW.amount_delta IS DISTINCT FROM p.amount-(NEW.old_value#>>'{}')::numeric THEN RAISE EXCEPTION 'Invalid amount'; END IF;
        ELSE
          IF r.category<>'FUEL' OR (NEW.new_value<>'null'::jsonb AND (NEW.new_value#>>'{}') !~ '^[0-9]{1,10}([.][0-9])?$') THEN RAISE EXCEPTION 'Fuel odometer required'; END IF;
          p.odometer:=(NEW.new_value#>>'{}')::numeric;
        END IF;
      ELSIF NEW.field_name='voided' THEN
        IF jsonb_typeof(NEW.new_value)<>'boolean' OR (NEW.reverses_id IS NULL AND NEW.new_value<>'true'::jsonb) THEN RAISE EXCEPTION 'Invalid void'; END IF;
        p.voided:=(NEW.new_value#>>'{}')::boolean;
      ELSE
        IF NEW.new_value<>'null'::jsonb AND jsonb_typeof(NEW.new_value)<>'string' THEN RAISE EXCEPTION 'Text required'; END IF;
        IF NEW.field_name='description' THEN p.description:=NEW.new_value#>>'{}'; ELSE p.reference_number:=NEW.new_value#>>'{}'; END IF;
        IF length(p.description)>2000 OR length(p.reference_number)>120 OR (r.category='OTHER' AND length(trim(coalesce(p.description,'')))<3) THEN RAISE EXCEPTION 'Invalid description or reference'; END IF;
      END IF;
      IF NEW.field_name<>'amount' AND NEW.amount_delta IS NOT NULL THEN RAISE EXCEPTION 'Unexpected amount delta'; END IF;
      INSERT INTO expense_effective_values(organization_id,trip_id,expense_id,sequence,amount,odometer,description,reference_number,voided)
      VALUES(e.organization_id,e.trip_id,e.id,NEW.sequence,p.amount,p.odometer,p.description,p.reference_number,p.voided)
      ON CONFLICT(expense_id) DO UPDATE SET sequence=EXCLUDED.sequence,amount=EXCLUDED.amount,odometer=EXCLUDED.odometer,description=EXCLUDED.description,reference_number=EXCLUDED.reference_number,voided=EXCLUDED.voided;
      RETURN NEW;
    END $$""")
    op.execute(
        "CREATE TRIGGER closed_adjustment_event BEFORE INSERT OR UPDATE OR DELETE ON closed_trip_adjustments FOR EACH ROW EXECUTE FUNCTION apply_closed_adjustment()"
    )


def downgrade():
    op.drop_table("closed_trip_adjustments")
    op.drop_table("expense_effective_values")
    op.execute("DROP FUNCTION apply_closed_adjustment()")
    op.execute("DROP FUNCTION guard_adjustment_projection()")
