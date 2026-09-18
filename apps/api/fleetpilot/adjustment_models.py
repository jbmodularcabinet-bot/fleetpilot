"""Mappings for immutable events and their database-maintained projection."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKeyConstraint, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base


class ClosedTripAdjustment(Base):
    __tablename__ = "closed_trip_adjustments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "trip_id", "expense_id"],
            ["trip_expenses.organization_id", "trip_expenses.trip_id", "trip_expenses.id"],
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[uuid.UUID]
    trip_id: Mapped[uuid.UUID]
    expense_id: Mapped[uuid.UUID | None]
    revenue_id: Mapped[uuid.UUID | None]
    source_revision: Mapped[int | None] = mapped_column(Integer)
    sequence: Mapped[int] = mapped_column(Integer)
    adjustment_type: Mapped[str] = mapped_column(String(40))
    field_name: Mapped[str] = mapped_column(String(30))
    old_value: Mapped[object] = mapped_column(JSONB)
    new_value: Mapped[object] = mapped_column(JSONB)
    amount_delta: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    reason: Mapped[str] = mapped_column(Text)
    created_by: Mapped[uuid.UUID]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
    reverses_id: Mapped[uuid.UUID | None]


class ExpenseEffectiveValue(Base):
    __tablename__ = "expense_effective_values"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "trip_id", "expense_id"],
            ["trip_expenses.organization_id", "trip_expenses.trip_id", "trip_expenses.id"],
        ),
    )
    expense_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[uuid.UUID]
    trip_id: Mapped[uuid.UUID]
    sequence: Mapped[int] = mapped_column(Integer)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    odometer: Mapped[Decimal | None] = mapped_column(Numeric(9, 1))
    description: Mapped[str | None] = mapped_column(Text)
    reference_number: Mapped[str | None] = mapped_column(String(120))
    voided: Mapped[bool]
