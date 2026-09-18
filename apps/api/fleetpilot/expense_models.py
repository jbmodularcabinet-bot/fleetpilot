"""Expense identities, immutable financial revisions and private receipt metadata.

Migration 0007 owns workflow triggers/RLS. Routes use bound SQL for revision
commands and aggregates; these mappings retain the established domain metadata.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base


class TripExpense(Base):
    __tablename__ = "trip_expenses"
    __table_args__ = (
        UniqueConstraint("organization_id", "trip_id", "id"),
        ForeignKeyConstraint(["organization_id", "trip_id"], ["trips.organization_id", "trips.id"]),
        ForeignKeyConstraint(
            ["organization_id", "vehicle_id"], ["vehicles.organization_id", "vehicles.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "driver_id"], ["drivers.organization_id", "drivers.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "id", "current_revision"],
            [
                "expense_revisions.organization_id",
                "expense_revisions.expense_id",
                "expense_revisions.revision_number",
            ],
            name="current_expense_revision",
            deferrable=True,
            initially="DEFERRED",
            use_alter=True,
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    trip_id: Mapped[uuid.UUID]
    vehicle_id: Mapped[uuid.UUID]
    driver_id: Mapped[uuid.UUID]
    current_revision: Mapped[int] = mapped_column(Integer, server_default="1")
    status: Mapped[str] = mapped_column(String(20), server_default="SUBMITTED")
    submission_source: Mapped[str] = mapped_column(String(20))
    submitted_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_notes: Mapped[str | None] = mapped_column(Text)
    voided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    void_reason: Mapped[str | None] = mapped_column(Text)


class ExpenseRevision(Base):
    __tablename__ = "expense_revisions"
    __table_args__ = (
        UniqueConstraint("organization_id", "expense_id", "revision_number"),
        ForeignKeyConstraint(
            ["organization_id", "trip_id", "expense_id"],
            ["trip_expenses.organization_id", "trip_expenses.trip_id", "trip_expenses.id"],
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[uuid.UUID]
    trip_id: Mapped[uuid.UUID]
    expense_id: Mapped[uuid.UUID]
    revision_number: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(30))
    currency: Mapped[str] = mapped_column(String(3))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    description: Mapped[str | None] = mapped_column(Text)
    vendor_name: Mapped[str | None] = mapped_column(String(160))
    reference_number: Mapped[str | None] = mapped_column(String(120))
    liters: Mapped[Decimal | None] = mapped_column(Numeric(9, 3))
    price_per_liter: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    odometer: Mapped[Decimal | None] = mapped_column(Numeric(9, 1))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
    reason: Mapped[str | None] = mapped_column(Text)


class ExpenseEvidence(Base):
    __tablename__ = "expense_evidence"
    __table_args__ = (
        UniqueConstraint("organization_id", "expense_id", "id"),
        ForeignKeyConstraint(
            ["organization_id", "trip_id", "expense_id"],
            ["trip_expenses.organization_id", "trip_expenses.trip_id", "trip_expenses.id"],
        ),
        ForeignKeyConstraint(
            ["organization_id", "expense_id", "supersedes_id"],
            [
                "expense_evidence.organization_id",
                "expense_evidence.expense_id",
                "expense_evidence.id",
            ],
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[uuid.UUID]
    trip_id: Mapped[uuid.UUID]
    expense_id: Mapped[uuid.UUID]
    storage_key: Mapped[str] = mapped_column(String(160), unique=True)
    original_filename: Mapped[str] = mapped_column(String(160))
    content_type: Mapped[str] = mapped_column(String(30))
    file_size: Mapped[int] = mapped_column(Integer)
    checksum: Mapped[str] = mapped_column(String(64))
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
    status: Mapped[str] = mapped_column(String(20), server_default="ACTIVE")
    supersedes_id: Mapped[uuid.UUID | None]
