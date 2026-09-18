"""Mappings for append-only governance records; migration owns security guards."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base


class CashAdvance(Base):
    __tablename__ = "cash_advances"
    __table_args__ = (
        UniqueConstraint("organization_id", "trip_id", "id"),
        ForeignKeyConstraint(["organization_id", "trip_id"], ["trips.organization_id", "trips.id"]),
        ForeignKeyConstraint(
            ["organization_id", "driver_id"], ["drivers.organization_id", "drivers.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "trip_id", "source_expense_id"],
            ["trip_expenses.organization_id", "trip_expenses.trip_id", "trip_expenses.id"],
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[uuid.UUID]
    trip_id: Mapped[uuid.UUID]
    driver_id: Mapped[uuid.UUID]
    amount_issued: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(Text, server_default="PHP")
    source_expense_id: Mapped[uuid.UUID | None] = mapped_column(unique=True)
    purpose: Mapped[str | None] = mapped_column(Text)
    issued_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )


class CashAdvanceSettlementEntry(Base):
    __tablename__ = "cash_advance_settlement_entries"
    __table_args__ = (
        UniqueConstraint("organization_id", "trip_id", "cash_advance_id", "id"),
        ForeignKeyConstraint(
            ["organization_id", "trip_id", "cash_advance_id"],
            ["cash_advances.organization_id", "cash_advances.trip_id", "cash_advances.id"],
        ),
        ForeignKeyConstraint(
            ["organization_id", "trip_id", "expense_id"],
            ["trip_expenses.organization_id", "trip_expenses.trip_id", "trip_expenses.id"],
        ),
        ForeignKeyConstraint(
            ["organization_id", "trip_id", "cash_advance_id", "reverses_id"],
            [
                "cash_advance_settlement_entries.organization_id",
                "cash_advance_settlement_entries.trip_id",
                "cash_advance_settlement_entries.cash_advance_id",
                "cash_advance_settlement_entries.id",
            ],
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[uuid.UUID]
    trip_id: Mapped[uuid.UUID]
    cash_advance_id: Mapped[uuid.UUID]
    entry_type: Mapped[str] = mapped_column(Text)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(Text, server_default="PHP")
    expense_id: Mapped[uuid.UUID | None]
    reverses_id: Mapped[uuid.UUID | None] = mapped_column(unique=True)
    reason: Mapped[str] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )


class TripFinancialReviewEvent(Base):
    __tablename__ = "trip_financial_review_events"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "trip_id"], ["trips.organization_id", "trips.id"]),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[uuid.UUID]
    trip_id: Mapped[uuid.UUID]
    status: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
    sequence: Mapped[int] = mapped_column(BigInteger, Identity(always=True))
