"""Append-only cash settlement and explicit, invalidatable financial review."""

from alembic import op

revision = "0011_cash_advance_review"
down_revision = "0010_trip_profitability"
branch_labels = depends_on = None

SOURCES = (
    "trip_revenue",
    "trip_expenses",
    "closed_trip_adjustments",
    "cash_advances",
    "cash_advance_settlement_entries",
)


def upgrade():
    op.execute("""CREATE TABLE cash_advances (
      id uuid PRIMARY KEY, organization_id uuid NOT NULL, trip_id uuid NOT NULL, driver_id uuid NOT NULL,
      amount_issued numeric(12,2) NOT NULL CHECK(amount_issued>0 AND amount_issued<=10000000),
      currency text NOT NULL DEFAULT 'PHP' CHECK(currency='PHP'), source_expense_id uuid,
      purpose text CHECK(length(purpose)<=2000), issued_by uuid NOT NULL REFERENCES users(id),
      issued_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      UNIQUE(organization_id,trip_id,id), UNIQUE(source_expense_id),
      FOREIGN KEY(organization_id,trip_id) REFERENCES trips(organization_id,id),
      FOREIGN KEY(organization_id,driver_id) REFERENCES drivers(organization_id,id),
      FOREIGN KEY(organization_id,trip_id,source_expense_id) REFERENCES trip_expenses(organization_id,trip_id,id)
    )""")
    op.execute("""CREATE TABLE cash_advance_settlement_entries (
      id uuid PRIMARY KEY, organization_id uuid NOT NULL, trip_id uuid NOT NULL, cash_advance_id uuid NOT NULL,
      entry_type text NOT NULL CHECK(entry_type IN ('EXPENSE_APPLIED','CASH_RETURNED','REVERSAL','VOID')),
      amount numeric(12,2) NOT NULL CHECK(amount>=0 AND amount<=10000000), currency text NOT NULL DEFAULT 'PHP' CHECK(currency='PHP'),
      expense_id uuid, reverses_id uuid UNIQUE, reason text NOT NULL CHECK(length(regexp_replace(reason,'[[:space:]]','','g'))>=10 AND length(reason)<=2000),
      created_by uuid NOT NULL REFERENCES users(id), created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      UNIQUE(organization_id,trip_id,cash_advance_id,id),
      FOREIGN KEY(organization_id,trip_id,cash_advance_id) REFERENCES cash_advances(organization_id,trip_id,id),
      FOREIGN KEY(organization_id,trip_id,expense_id) REFERENCES trip_expenses(organization_id,trip_id,id),
      FOREIGN KEY(organization_id,trip_id,cash_advance_id,reverses_id) REFERENCES cash_advance_settlement_entries(organization_id,trip_id,cash_advance_id,id),
      CHECK((entry_type='EXPENSE_APPLIED')=(expense_id IS NOT NULL)),
      CHECK((entry_type='REVERSAL')=(reverses_id IS NOT NULL)),
      CHECK((entry_type='VOID' AND amount=0) OR (entry_type<>'VOID' AND amount>0))
    )""")
    op.execute("""CREATE TABLE trip_financial_review_events (
      id uuid PRIMARY KEY, organization_id uuid NOT NULL, trip_id uuid NOT NULL,
      status text NOT NULL CHECK(status IN ('UNDER_REVIEW','APPROVED','NEEDS_ATTENTION')),
      reason text NOT NULL, created_by uuid NOT NULL REFERENCES users(id),
      created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      sequence bigint GENERATED ALWAYS AS IDENTITY,
      FOREIGN KEY(organization_id,trip_id) REFERENCES trips(organization_id,id)
    )""")
    for table in (
        "cash_advances",
        "cash_advance_settlement_entries",
        "trip_financial_review_events",
    ):
        op.execute(f"CREATE INDEX ix_{table}_trip ON {table}(organization_id,trip_id)")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        cap = (
            "financial_review.read"
            if table == "trip_financial_review_events"
            else "cash_advance.read"
        )
        tenant = "organization_id=NULLIF(current_setting('app.organization_id',true),'')::uuid"
        member = f"EXISTS(SELECT 1 FROM organization_memberships m WHERE m.organization_id={table}.organization_id AND m.user_id=NULLIF(current_setting('app.user_id',true),'')::uuid AND active AND role IN ('OWNER','ADMIN','MANAGER','ACCOUNTING') AND NOT coalesce(permissions_json->'deny','[]'::jsonb) ? '{cap}')"
        nested = " OR pg_trigger_depth()>0" if table == "trip_financial_review_events" else ""
        op.execute(
            f"CREATE POLICY governance_read ON {table} FOR SELECT USING ({tenant} AND ({member}{nested}))"
        )
        op.execute(
            f"CREATE POLICY governance_insert ON {table} FOR INSERT WITH CHECK ({tenant} AND ({member}{nested}))"
        )
        # Policies allow UPDATE/DELETE so the immutable trigger fails explicitly even for owner.
        op.execute(
            f"CREATE POLICY governance_mutation ON {table} FOR ALL USING ({tenant} AND {member}) WITH CHECK ({tenant} AND {member})"
        )
    op.execute(
        "CREATE INDEX ix_settlement_advance ON cash_advance_settlement_entries(organization_id,cash_advance_id,created_at)"
    )
    op.execute(
        "CREATE INDEX ix_settlement_expense ON cash_advance_settlement_entries(organization_id,expense_id) WHERE expense_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_financial_review_latest ON trip_financial_review_events(organization_id,trip_id,sequence DESC)"
    )
    op.execute("""CREATE FUNCTION advance_balance(a uuid) RETURNS numeric LANGUAGE sql STABLE AS $$
      SELECT c.amount_issued-coalesce((SELECT sum(e.amount) FROM cash_advance_settlement_entries e WHERE e.cash_advance_id=c.id AND e.entry_type IN ('EXPENSE_APPLIED','CASH_RETURNED') AND NOT EXISTS(SELECT 1 FROM cash_advance_settlement_entries r WHERE r.reverses_id=e.id)),0) FROM cash_advances c WHERE c.id=a
    $$""")
    op.execute("""CREATE FUNCTION financial_review_blockers(t uuid) RETURNS text[] LANGUAGE sql STABLE AS $$
    SELECT array_remove(ARRAY[
      CASE WHEN NOT EXISTS(SELECT 1 FROM trips WHERE id=t AND current_status='COMPLETED') THEN 'Trip must be completed.' END,
      CASE WHEN NOT EXISTS(SELECT 1 FROM trip_revenue r LEFT JOIN revenue_effective_values p ON p.revenue_id=r.id WHERE r.trip_id=t AND r.status='REVIEWED' AND NOT coalesce(p.voided,false)) THEN 'Reviewed revenue is required.' END,
      CASE WHEN EXISTS(SELECT 1 FROM trip_revenue r LEFT JOIN revenue_effective_values p ON p.revenue_id=r.id WHERE r.trip_id=t AND r.status='SUBMITTED' AND NOT coalesce(p.voided,false)) THEN 'Revenue awaits review.' END,
      CASE WHEN EXISTS(SELECT 1 FROM trip_expenses e JOIN expense_revisions r ON r.expense_id=e.id AND r.revision_number=e.current_revision LEFT JOIN expense_effective_values p ON p.expense_id=e.id WHERE e.trip_id=t AND e.status='SUBMITTED' AND r.category<>'DRIVER_CASH_ADVANCE' AND NOT coalesce(p.voided,false)) THEN 'Direct expenses await review.' END,
      CASE WHEN EXISTS(SELECT 1 FROM cash_advances a WHERE a.trip_id=t AND advance_balance(a.id)>0 AND NOT EXISTS(SELECT 1 FROM cash_advance_settlement_entries e WHERE e.cash_advance_id=a.id AND e.entry_type='VOID')) THEN 'Cash advance remains outstanding.' END,
      CASE WHEN EXISTS(SELECT 1 FROM trip_expenses e JOIN expense_revisions r ON r.expense_id=e.id AND r.revision_number=e.current_revision LEFT JOIN expense_effective_values p ON p.expense_id=e.id WHERE e.trip_id=t AND e.status<>'VOIDED' AND r.category='DRIVER_CASH_ADVANCE' AND NOT coalesce(p.voided,false) AND NOT EXISTS(SELECT 1 FROM cash_advances a WHERE a.source_expense_id=e.id AND NOT EXISTS(SELECT 1 FROM cash_advance_settlement_entries z WHERE z.cash_advance_id=a.id AND z.entry_type='VOID'))) THEN 'Recorded cash advances require reconciliation.' END,
      CASE WHEN EXISTS(SELECT 1 FROM cash_advance_settlement_entries s JOIN trip_expenses e ON e.id=s.expense_id JOIN expense_revisions r ON r.expense_id=e.id AND r.revision_number=e.current_revision LEFT JOIN expense_effective_values p ON p.expense_id=e.id WHERE s.trip_id=t AND s.entry_type='EXPENSE_APPLIED' AND NOT EXISTS(SELECT 1 FROM cash_advance_settlement_entries z WHERE z.reverses_id=s.id) AND (e.status<>'REVIEWED' OR coalesce(p.voided,false) OR r.category='DRIVER_CASH_ADVANCE' OR s.amount>coalesce(p.amount,r.amount))) THEN 'Applied expense changed: reverse and reconcile its settlement.' END,
      CASE WHEN EXISTS(SELECT 1 FROM cash_advances a JOIN trip_expenses e ON e.id=a.source_expense_id JOIN expense_revisions r ON r.expense_id=e.id AND r.revision_number=e.current_revision LEFT JOIN expense_effective_values p ON p.expense_id=e.id WHERE a.trip_id=t AND NOT EXISTS(SELECT 1 FROM cash_advance_settlement_entries z WHERE z.cash_advance_id=a.id AND z.entry_type='VOID') AND (e.status='VOIDED' OR coalesce(p.voided,false) OR r.category<>'DRIVER_CASH_ADVANCE' OR a.amount_issued<>coalesce(p.amount,r.amount))) THEN 'Recorded advance changed: reconcile the original issuance.' END
    ],NULL)::text[] $$""")
    op.execute("""CREATE FUNCTION guard_cash_governance() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE m organization_memberships%ROWTYPE; a cash_advances%ROWTYPE; v_exp record; original cash_advance_settlement_entries%ROWTYPE; permission text; balance numeric;
    BEGIN
      IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Financial history is append-only'; END IF;
      PERFORM id FROM organizations WHERE id=NEW.organization_id FOR UPDATE;
      SELECT * INTO m FROM organization_memberships WHERE organization_id=NEW.organization_id AND user_id=NULLIF(current_setting('app.user_id',true),'')::uuid AND active;
      permission:=CASE WHEN TG_TABLE_NAME='cash_advances' THEN 'cash_advance.create' ELSE 'cash_advance.settle' END;
      IF TG_TABLE_NAME='cash_advance_settlement_entries' THEN IF NEW.entry_type='VOID' THEN permission:='cash_advance.void'; END IF; END IF;
      IF m.role IS NULL OR m.role NOT IN ('OWNER','ADMIN','MANAGER','ACCOUNTING') OR coalesce(m.permissions_json->'deny','[]'::jsonb) ? permission OR coalesce(m.permissions_json->'deny','[]'::jsonb) ? 'cash_advance.read' THEN RAISE EXCEPTION 'Cash permission required'; END IF;
      IF NOT EXISTS(SELECT 1 FROM trips WHERE id=NEW.trip_id AND organization_id=NEW.organization_id AND current_status<>'CANCELLED') THEN RAISE EXCEPTION 'Trip not eligible'; END IF;
      IF TG_TABLE_NAME='cash_advances' THEN
        IF NEW.issued_by IS DISTINCT FROM m.user_id THEN RAISE EXCEPTION 'Invalid actor'; END IF;
        IF NEW.source_expense_id IS NULL THEN
          IF NOT EXISTS(SELECT 1 FROM trips WHERE id=NEW.trip_id AND driver_id=NEW.driver_id) THEN RAISE EXCEPTION 'Assigned driver required'; END IF;
        ELSE
          SELECT e.driver_id,e.status,r.category,coalesce(p.amount,r.amount) amount,coalesce(p.voided,false) voided INTO v_exp FROM trip_expenses e JOIN expense_revisions r ON r.expense_id=e.id AND r.revision_number=e.current_revision LEFT JOIN expense_effective_values p ON p.expense_id=e.id WHERE e.id=NEW.source_expense_id AND e.organization_id=NEW.organization_id AND e.trip_id=NEW.trip_id;
          IF NOT FOUND OR v_exp.status='VOIDED' OR v_exp.voided OR v_exp.category<>'DRIVER_CASH_ADVANCE' OR v_exp.amount<>NEW.amount_issued OR v_exp.driver_id<>NEW.driver_id THEN RAISE EXCEPTION 'Invalid recorded advance'; END IF;
        END IF;
      ELSE
        IF NEW.created_by IS DISTINCT FROM m.user_id THEN RAISE EXCEPTION 'Invalid actor'; END IF;
        SELECT * INTO a FROM cash_advances WHERE id=NEW.cash_advance_id AND organization_id=NEW.organization_id AND trip_id=NEW.trip_id;
        IF NOT FOUND OR EXISTS(SELECT 1 FROM cash_advance_settlement_entries WHERE cash_advance_id=a.id AND entry_type='VOID') THEN RAISE EXCEPTION 'Advance not eligible'; END IF;
        balance:=advance_balance(a.id);
        IF NEW.entry_type='VOID' THEN
          IF EXISTS(SELECT 1 FROM cash_advance_settlement_entries WHERE cash_advance_id=a.id) THEN RAISE EXCEPTION 'Settlement history prevents void'; END IF;
        ELSIF NEW.entry_type='REVERSAL' THEN
          SELECT * INTO original FROM cash_advance_settlement_entries WHERE id=NEW.reverses_id AND cash_advance_id=a.id;
          IF NOT FOUND OR original.entry_type NOT IN ('EXPENSE_APPLIED','CASH_RETURNED') OR NEW.amount<>original.amount THEN RAISE EXCEPTION 'Invalid reversal'; END IF;
        ELSE
          IF NEW.amount>balance THEN RAISE EXCEPTION 'Over settlement'; END IF;
          IF NEW.entry_type='EXPENSE_APPLIED' THEN
            SELECT e.driver_id,e.status,r.category,coalesce(p.amount,r.amount) amount,coalesce(p.voided,false) voided INTO v_exp FROM trip_expenses e JOIN expense_revisions r ON r.expense_id=e.id AND r.revision_number=e.current_revision LEFT JOIN expense_effective_values p ON p.expense_id=e.id WHERE e.id=NEW.expense_id AND e.organization_id=NEW.organization_id AND e.trip_id=NEW.trip_id;
            IF NOT FOUND OR v_exp.status<>'REVIEWED' OR v_exp.voided OR v_exp.category='DRIVER_CASH_ADVANCE' OR v_exp.driver_id<>a.driver_id OR NEW.amount<>v_exp.amount THEN RAISE EXCEPTION 'Eligible whole reviewed expense required'; END IF;
            IF EXISTS(SELECT 1 FROM cash_advance_settlement_entries s WHERE s.expense_id=NEW.expense_id AND NOT EXISTS(SELECT 1 FROM cash_advance_settlement_entries r WHERE r.reverses_id=s.id)) THEN RAISE EXCEPTION 'Expense already applied'; END IF;
          END IF;
        END IF;
      END IF;
      RETURN NEW;
    END $$""")
    for table in ("cash_advances", "cash_advance_settlement_entries"):
        op.execute(
            f"CREATE TRIGGER cash_guard BEFORE INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION guard_cash_governance()"
        )
    op.execute("""CREATE FUNCTION guard_financial_review() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE m organization_memberships%ROWTYPE;
    BEGIN
      IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Review history is immutable'; END IF;
      PERFORM id FROM organizations WHERE id=NEW.organization_id FOR UPDATE;
      IF NEW.created_by IS DISTINCT FROM NULLIF(current_setting('app.user_id',true),'')::uuid THEN RAISE EXCEPTION 'Invalid reviewer'; END IF;
      IF NEW.status='NEEDS_ATTENTION' AND pg_trigger_depth()>1 THEN RETURN NEW; END IF;
      SELECT * INTO m FROM organization_memberships WHERE organization_id=NEW.organization_id AND user_id=NEW.created_by AND active;
      IF m.role IS NULL OR m.role NOT IN ('OWNER','ADMIN') OR coalesce(m.permissions_json->'deny','[]'::jsonb) ?| ARRAY['financial_review.approve','financial_review.read','cash_advance.read','trip_financials.read','expenses.read'] THEN RAISE EXCEPTION 'Review permission required'; END IF;
      IF NEW.status NOT IN ('UNDER_REVIEW','APPROVED') THEN RAISE EXCEPTION 'Invalid review command'; END IF;
      IF NEW.status='APPROVED' AND cardinality(financial_review_blockers(NEW.trip_id))>0 THEN RAISE EXCEPTION 'Financial review blocked'; END IF;
      RETURN NEW;
    END $$""")
    op.execute(
        "CREATE TRIGGER review_guard BEFORE INSERT OR UPDATE OR DELETE ON trip_financial_review_events FOR EACH ROW EXECUTE FUNCTION guard_financial_review()"
    )
    op.execute("""CREATE FUNCTION invalidate_financial_review() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE previous text;
    BEGIN
      SELECT status INTO previous FROM trip_financial_review_events WHERE organization_id=NEW.organization_id AND trip_id=NEW.trip_id ORDER BY sequence DESC LIMIT 1;
        INSERT INTO trip_financial_review_events(id,organization_id,trip_id,status,reason,created_by) VALUES(gen_random_uuid(),NEW.organization_id,NEW.trip_id,'NEEDS_ATTENTION','Financial records changed: '||TG_TABLE_NAME,NULLIF(current_setting('app.user_id',true),'')::uuid);
        IF previous IN ('APPROVED','UNDER_REVIEW') THEN
          INSERT INTO audit_logs(id,organization_id,actor_user_id,action,entity_type,entity_id,after_json) VALUES(gen_random_uuid(),NEW.organization_id,NULLIF(current_setting('app.user_id',true),'')::uuid,'financial_review.invalidated','trip',NEW.trip_id,jsonb_build_object('source',TG_TABLE_NAME));
        END IF;
      RETURN NEW;
    END $$""")
    for table in SOURCES:
        op.execute(
            f"CREATE TRIGGER financial_invalidation AFTER INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION invalidate_financial_review()"
        )


def downgrade():
    for table in SOURCES:
        op.execute(f"DROP TRIGGER financial_invalidation ON {table}")
    op.execute("DROP FUNCTION invalidate_financial_review()")
    for table in (
        "trip_financial_review_events",
        "cash_advance_settlement_entries",
        "cash_advances",
    ):
        op.execute(f"DROP TABLE {table} CASCADE")
    for function in (
        "guard_financial_review()",
        "guard_cash_governance()",
        "financial_review_blockers(uuid)",
        "advance_balance(uuid)",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS {function}")
