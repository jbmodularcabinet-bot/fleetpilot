"""Append-only acceptance overlay for legacy completed-trip expenses."""

from alembic import op

revision = "0012_legacy_financial_review"
down_revision = "0011_cash_advance_review"
branch_labels = depends_on = None


def blockers_sql(with_legacy: bool) -> str:
    legacy = " AND NOT EXISTS(SELECT 1 FROM legacy_expense_review_events l WHERE l.organization_id=e.organization_id AND l.expense_id=e.id AND l.action='ACCEPTED')" if with_legacy else ""
    return f"""CREATE OR REPLACE FUNCTION financial_review_blockers(t uuid) RETURNS text[] LANGUAGE sql STABLE AS $$
    SELECT array_remove(ARRAY[
      CASE WHEN NOT EXISTS(SELECT 1 FROM trips WHERE id=t AND current_status='COMPLETED') THEN 'Trip must be completed.' END,
      CASE WHEN NOT EXISTS(SELECT 1 FROM trip_revenue r LEFT JOIN revenue_effective_values p ON p.revenue_id=r.id WHERE r.trip_id=t AND r.status='REVIEWED' AND NOT coalesce(p.voided,false)) THEN 'Reviewed revenue is required.' END,
      CASE WHEN EXISTS(SELECT 1 FROM trip_revenue r LEFT JOIN revenue_effective_values p ON p.revenue_id=r.id WHERE r.trip_id=t AND r.status='SUBMITTED' AND NOT coalesce(p.voided,false)) THEN 'Revenue awaits review.' END,
      CASE WHEN EXISTS(SELECT 1 FROM trip_expenses e JOIN expense_revisions r ON r.expense_id=e.id AND r.revision_number=e.current_revision LEFT JOIN expense_effective_values p ON p.expense_id=e.id WHERE e.trip_id=t AND e.status='SUBMITTED' AND r.category<>'DRIVER_CASH_ADVANCE' AND NOT coalesce(p.voided,false){legacy}) THEN 'Direct expenses await review.' END,
      CASE WHEN EXISTS(SELECT 1 FROM cash_advances a WHERE a.trip_id=t AND advance_balance(a.id)>0 AND NOT EXISTS(SELECT 1 FROM cash_advance_settlement_entries e WHERE e.cash_advance_id=a.id AND e.entry_type='VOID')) THEN 'Cash advance remains outstanding.' END,
      CASE WHEN EXISTS(SELECT 1 FROM trip_expenses e JOIN expense_revisions r ON r.expense_id=e.id AND r.revision_number=e.current_revision LEFT JOIN expense_effective_values p ON p.expense_id=e.id WHERE e.trip_id=t AND e.status<>'VOIDED' AND r.category='DRIVER_CASH_ADVANCE' AND NOT coalesce(p.voided,false) AND NOT EXISTS(SELECT 1 FROM cash_advances a WHERE a.source_expense_id=e.id AND NOT EXISTS(SELECT 1 FROM cash_advance_settlement_entries z WHERE z.cash_advance_id=a.id AND z.entry_type='VOID'))) THEN 'Recorded cash advances require reconciliation.' END,
      CASE WHEN EXISTS(SELECT 1 FROM cash_advance_settlement_entries s JOIN trip_expenses e ON e.id=s.expense_id JOIN expense_revisions r ON r.expense_id=e.id AND r.revision_number=e.current_revision LEFT JOIN expense_effective_values p ON p.expense_id=e.id WHERE s.trip_id=t AND s.entry_type='EXPENSE_APPLIED' AND NOT EXISTS(SELECT 1 FROM cash_advance_settlement_entries z WHERE z.reverses_id=s.id) AND (e.status<>'REVIEWED' OR coalesce(p.voided,false) OR r.category='DRIVER_CASH_ADVANCE' OR s.amount>coalesce(p.amount,r.amount))) THEN 'Applied expense changed: reverse and reconcile its settlement.' END,
      CASE WHEN EXISTS(SELECT 1 FROM cash_advances a JOIN trip_expenses e ON e.id=a.source_expense_id JOIN expense_revisions r ON r.expense_id=e.id AND r.revision_number=e.current_revision LEFT JOIN expense_effective_values p ON p.expense_id=e.id WHERE a.trip_id=t AND NOT EXISTS(SELECT 1 FROM cash_advance_settlement_entries z WHERE z.cash_advance_id=a.id AND z.entry_type='VOID') AND (e.status='VOIDED' OR coalesce(p.voided,false) OR r.category<>'DRIVER_CASH_ADVANCE' OR a.amount_issued<>coalesce(p.amount,r.amount))) THEN 'Recorded advance changed: reconcile the original issuance.' END
    ],NULL)::text[] $$"""


def upgrade():
    op.execute("""CREATE TABLE legacy_expense_review_events (
      id uuid PRIMARY KEY, organization_id uuid NOT NULL, trip_id uuid NOT NULL, expense_id uuid NOT NULL,
      action text NOT NULL DEFAULT 'ACCEPTED' CHECK(action='ACCEPTED'),
      created_by uuid NOT NULL REFERENCES users(id), created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
      UNIQUE(organization_id,expense_id),
      FOREIGN KEY(organization_id,trip_id,expense_id) REFERENCES trip_expenses(organization_id,trip_id,id)
    )""")
    op.execute("CREATE INDEX ix_legacy_expense_review_trip ON legacy_expense_review_events(organization_id,trip_id,created_at)")
    op.execute("ALTER TABLE legacy_expense_review_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE legacy_expense_review_events FORCE ROW LEVEL SECURITY")
    tenant = "organization_id=NULLIF(current_setting('app.organization_id',true),'')::uuid"
    member = "EXISTS(SELECT 1 FROM organization_memberships m WHERE m.organization_id=legacy_expense_review_events.organization_id AND m.user_id=NULLIF(current_setting('app.user_id',true),'')::uuid AND m.active AND NOT coalesce(m.permissions_json->'deny','[]'::jsonb) ? 'financial_review.read')"
    writer = "EXISTS(SELECT 1 FROM organization_memberships m WHERE m.organization_id=legacy_expense_review_events.organization_id AND m.user_id=NULLIF(current_setting('app.user_id',true),'')::uuid AND m.active AND m.role IN ('OWNER','ADMIN') AND NOT coalesce(m.permissions_json->'deny','[]'::jsonb) ?| ARRAY['financial_review.approve','expenses.review'])"
    op.execute(f"CREATE POLICY legacy_review_read ON legacy_expense_review_events FOR SELECT USING ({tenant} AND {member})")
    op.execute(f"CREATE POLICY legacy_review_insert ON legacy_expense_review_events FOR INSERT WITH CHECK ({tenant} AND {writer})")
    op.execute("""CREATE FUNCTION guard_legacy_expense_review() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE m organization_memberships%ROWTYPE; current_category text; current_voided boolean;
    BEGIN
      IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Legacy review history is append-only'; END IF;
      IF NEW.created_by IS DISTINCT FROM NULLIF(current_setting('app.user_id',true),'')::uuid THEN RAISE EXCEPTION 'Invalid reviewer'; END IF;
      SELECT * INTO m FROM organization_memberships WHERE organization_id=NEW.organization_id AND user_id=NEW.created_by AND active;
      IF m.role NOT IN ('OWNER','ADMIN') OR coalesce(m.permissions_json->'deny','[]'::jsonb) ?| ARRAY['financial_review.approve','expenses.review'] THEN RAISE EXCEPTION 'Legacy review permission required'; END IF;
      IF NOT EXISTS(SELECT 1 FROM trips WHERE id=NEW.trip_id AND organization_id=NEW.organization_id AND current_status='COMPLETED') THEN RAISE EXCEPTION 'Legacy review requires completed trip'; END IF;
      SELECT r.category,coalesce(p.voided,false) INTO current_category,current_voided
      FROM trip_expenses e JOIN expense_revisions r ON r.organization_id=e.organization_id AND r.expense_id=e.id AND r.revision_number=e.current_revision
      LEFT JOIN expense_effective_values p ON p.organization_id=e.organization_id AND p.expense_id=e.id
      WHERE e.organization_id=NEW.organization_id AND e.trip_id=NEW.trip_id AND e.id=NEW.expense_id AND e.status='SUBMITTED';
      IF NOT FOUND OR current_category='DRIVER_CASH_ADVANCE' OR current_voided THEN RAISE EXCEPTION 'Legacy expense is not eligible for acceptance'; END IF;
      RETURN NEW;
    END $$""")
    op.execute("CREATE TRIGGER legacy_review_guard BEFORE INSERT OR UPDATE OR DELETE ON legacy_expense_review_events FOR EACH ROW EXECUTE FUNCTION guard_legacy_expense_review()")
    op.execute(blockers_sql(True))


def downgrade():
    op.execute(blockers_sql(False))
    op.execute("DROP TRIGGER legacy_review_guard ON legacy_expense_review_events")
    op.execute("DROP FUNCTION guard_legacy_expense_review()")
    op.execute("DROP TABLE legacy_expense_review_events")
