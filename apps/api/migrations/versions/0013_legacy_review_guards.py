"""Align legacy acceptance with financial locks, permissions and review tokens."""

from alembic import op

revision = "0013_legacy_review_guards"
down_revision = "0012_legacy_financial_review"
branch_labels = depends_on = None


def upgrade():
    op.execute("""ALTER POLICY legacy_review_read ON legacy_expense_review_events USING (
      organization_id=NULLIF(current_setting('app.organization_id',true),'')::uuid
      AND EXISTS(SELECT 1 FROM organization_memberships m
        WHERE m.organization_id=legacy_expense_review_events.organization_id
        AND m.user_id=NULLIF(current_setting('app.user_id',true),'')::uuid
        AND m.active AND m.role IN ('OWNER','ADMIN','MANAGER','ACCOUNTING')
        AND NOT coalesce(m.permissions_json->'deny','[]'::jsonb) ? 'financial_review.read'))""")
    op.execute("""CREATE FUNCTION guard_legacy_review_permissions() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE m organization_memberships%ROWTYPE; category text;
    BEGIN
      PERFORM id FROM organizations WHERE id=NEW.organization_id FOR UPDATE;
      SELECT * INTO m FROM organization_memberships WHERE organization_id=NEW.organization_id
        AND user_id=NULLIF(current_setting('app.user_id',true),'')::uuid AND active;
      IF m.role IS NULL OR m.role NOT IN ('OWNER','ADMIN') OR
        coalesce(m.permissions_json->'deny','[]'::jsonb) ?| ARRAY['financial_review.approve','financial_review.read','expenses.read','expenses.review']
        THEN RAISE EXCEPTION 'Legacy review permission required'; END IF;
      SELECT r.category INTO category FROM trip_expenses e JOIN expense_revisions r
        ON r.organization_id=e.organization_id AND r.expense_id=e.id AND r.revision_number=e.current_revision
        WHERE e.organization_id=NEW.organization_id AND e.id=NEW.expense_id;
      IF category='FUEL' AND coalesce(m.permissions_json->'deny','[]'::jsonb) ? 'fuel.review'
        THEN RAISE EXCEPTION 'Fuel review permission required'; END IF;
      RETURN NEW;
    END $$""")
    # Alphabetical ordering obtains the same organization lock before the existing guard.
    op.execute("CREATE TRIGGER legacy_review_access BEFORE INSERT ON legacy_expense_review_events FOR EACH ROW EXECUTE FUNCTION guard_legacy_review_permissions()")
    op.execute("CREATE TRIGGER financial_invalidation AFTER INSERT ON legacy_expense_review_events FOR EACH ROW EXECUTE FUNCTION invalidate_financial_review()")


def downgrade():
    op.execute("DROP TRIGGER financial_invalidation ON legacy_expense_review_events")
    op.execute("DROP TRIGGER legacy_review_access ON legacy_expense_review_events")
    op.execute("DROP FUNCTION guard_legacy_review_permissions()")
    op.execute("""ALTER POLICY legacy_review_read ON legacy_expense_review_events USING (
      organization_id=NULLIF(current_setting('app.organization_id',true),'')::uuid
      AND EXISTS(SELECT 1 FROM organization_memberships m
        WHERE m.organization_id=legacy_expense_review_events.organization_id
        AND m.user_id=NULLIF(current_setting('app.user_id',true),'')::uuid
        AND m.active AND NOT coalesce(m.permissions_json->'deny','[]'::jsonb) ? 'financial_review.read'))""")
