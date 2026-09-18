"""Revenue mappings; profitability is computed, never a stale stored total."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKeyConstraint, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base


class TripRevenue(Base):
    __tablename__ = "trip_revenue"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id", "trip_id"], ["trips.organization_id", "trips.id"]),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[uuid.UUID]
    trip_id: Mapped[uuid.UUID]
    revenue_type: Mapped[str] = mapped_column(Text)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(Text, default="PHP")
    description: Mapped[str | None] = mapped_column(Text)
    reference_number: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(Text, default="SUBMITTED")
    created_by: Mapped[uuid.UUID]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
    reviewed_by: Mapped[uuid.UUID | None]
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by: Mapped[uuid.UUID | None]
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    void_reason: Mapped[str | None] = mapped_column(Text)


class RevenueEffectiveValue(Base):
    __tablename__ = "revenue_effective_values"
    revenue_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[uuid.UUID]
    trip_id: Mapped[uuid.UUID]
    sequence: Mapped[int]
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    description: Mapped[str | None] = mapped_column(Text)
    reference_number: Mapped[str | None] = mapped_column(String(120))
    voided: Mapped[bool]
