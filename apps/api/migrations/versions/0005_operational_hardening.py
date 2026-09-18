"""Shared abuse-control counters; no tenant business data."""

from alembic import op

revision = "0005_operational_hardening"
down_revision = "0004_proof_of_delivery"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE request_rate_windows (
        key_hash varchar(64) PRIMARY KEY,
        expires_at timestamptz NOT NULL,
        request_count integer NOT NULL CHECK (request_count > 0)
    )""")
    op.execute("CREATE INDEX ix_rate_expiry ON request_rate_windows(expires_at)")
    # Infrastructure counters hold only SHA-256 network/category keys. No tenant records.
    op.execute("REVOKE ALL ON request_rate_windows FROM PUBLIC")


def downgrade():
    op.execute("DROP TABLE request_rate_windows")
