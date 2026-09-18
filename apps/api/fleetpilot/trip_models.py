import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base, Timestamps


class Trip(Timestamps, Base):
    __tablename__ = "trips"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_trip_tenant_id"),
        UniqueConstraint("organization_id", "trip_number", name="uq_trip_number"),
        UniqueConstraint("organization_id", "number_sequence", name="uq_trip_sequence"),
        ForeignKeyConstraint(
            ["organization_id", "customer_id"],
            ["customers.organization_id", "customers.id"],
            name="fk_trip_customer_tenant",
        ),
        ForeignKeyConstraint(
            ["organization_id", "vehicle_id"],
            ["vehicles.organization_id", "vehicles.id"],
            name="fk_trip_vehicle_tenant",
        ),
        ForeignKeyConstraint(
            ["organization_id", "driver_id"],
            ["drivers.organization_id", "drivers.id"],
            name="fk_trip_driver_tenant",
        ),
        CheckConstraint(
            "current_status IN ('SCHEDULED','DISPATCHED','PICKUP','LOADED','IN_TRANSIT','DELIVERED','COMPLETED','CANCELLED')",
            name="ck_trip_status",
        ),
        CheckConstraint(
            "(vehicle_id IS NULL) = (driver_id IS NULL)", name="ck_trip_assignment_pair"
        ),
        CheckConstraint(
            "scheduled_delivery_at IS NULL OR scheduled_delivery_at > scheduled_pickup_at",
            name="ck_trip_schedule",
        ),
        CheckConstraint("version > 0 AND number_sequence > 0", name="ck_trip_versions"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    trip_number: Mapped[str] = mapped_column(String(40))
    number_sequence: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)
    pod_required: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    customer_id: Mapped[uuid.UUID]
    pickup_name: Mapped[str] = mapped_column(String(160))
    pickup_address: Mapped[str] = mapped_column(Text)
    pickup_latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    pickup_longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    pickup_contact_name: Mapped[str | None] = mapped_column(String(120))
    pickup_contact_phone: Mapped[str | None] = mapped_column(String(30))
    delivery_name: Mapped[str] = mapped_column(String(160))
    delivery_address: Mapped[str] = mapped_column(Text)
    delivery_latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    delivery_longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    delivery_contact_name: Mapped[str | None] = mapped_column(String(120))
    delivery_contact_phone: Mapped[str | None] = mapped_column(String(30))
    scheduled_pickup_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scheduled_delivery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    vehicle_id: Mapped[uuid.UUID | None]
    driver_id: Mapped[uuid.UUID | None]
    current_status: Mapped[str] = mapped_column(String(20), default="SCHEDULED")
    current_milestone: Mapped[str] = mapped_column(String(40), default="SCHEDULED")
    reference_number: Mapped[str | None] = mapped_column(String(120))
    customer_reference: Mapped[str | None] = mapped_column(String(120))
    cargo_description: Mapped[str | None] = mapped_column(Text)
    cargo_weight: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    cargo_weight_unit: Mapped[str | None] = mapped_column(String(10))
    special_instructions: Mapped[str | None] = mapped_column(Text)
    dispatcher_notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    updated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    cancellation_reason: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TripMilestone(Base):
    __tablename__ = "trip_milestones"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "trip_id"],
            ["trips.organization_id", "trips.id"],
            name="fk_milestone_trip_tenant",
        ),
        UniqueConstraint("organization_id", "trip_id", "event_number", name="uq_milestone_order"),
        CheckConstraint(
            "source IN ('OWNER_WEB','DISPATCHER_WEB','DRIVER_APP','SYSTEM')",
            name="ck_milestone_source",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    trip_id: Mapped[uuid.UUID]
    event_number: Mapped[int] = mapped_column(Integer)
    milestone_type: Mapped[str] = mapped_column(String(40))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    recorded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    source: Mapped[str] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class TripAssignment(Base):
    __tablename__ = "trip_assignments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "trip_id"],
            ["trips.organization_id", "trips.id"],
            name="fk_trip_assignment_trip",
        ),
        ForeignKeyConstraint(
            ["organization_id", "vehicle_id"],
            ["vehicles.organization_id", "vehicles.id"],
            name="fk_trip_assignment_vehicle",
        ),
        ForeignKeyConstraint(
            ["organization_id", "driver_id"],
            ["drivers.organization_id", "drivers.id"],
            name="fk_trip_assignment_driver",
        ),
        CheckConstraint(
            "(is_current AND ended_at IS NULL) OR (NOT is_current AND ended_at IS NOT NULL AND ended_at >= assigned_at)",
            name="ck_trip_assignment_lifecycle",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    trip_id: Mapped[uuid.UUID]
    vehicle_id: Mapped[uuid.UUID]
    driver_id: Mapped[uuid.UUID]
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


for name, fields in {
    "ix_trip_status_schedule": (
        Trip.organization_id,
        Trip.current_status,
        Trip.scheduled_pickup_at,
    ),
    "ix_trip_schedule": (Trip.organization_id, Trip.scheduled_pickup_at),
    "ix_trip_customer": (Trip.organization_id, Trip.customer_id, Trip.scheduled_pickup_at),
    "ix_trip_vehicle": (Trip.organization_id, Trip.vehicle_id, Trip.scheduled_pickup_at),
    "ix_trip_driver": (Trip.organization_id, Trip.driver_id, Trip.scheduled_pickup_at),
    "ix_trip_created": (Trip.organization_id, Trip.created_at),
}.items():
    Index(name, *fields)
for field in ("vehicle_id", "driver_id"):
    Index(
        f"uq_active_trip_{field}",
        Trip.organization_id,
        getattr(Trip, field),
        unique=True,
        postgresql_where=text("current_status NOT IN ('SCHEDULED','COMPLETED','CANCELLED')"),
    )
Index(
    "ix_milestone_timeline",
    TripMilestone.organization_id,
    TripMilestone.trip_id,
    TripMilestone.occurred_at,
)
Index(
    "uq_current_trip_assignment",
    TripAssignment.organization_id,
    TripAssignment.trip_id,
    unique=True,
    postgresql_where=text("is_current"),
)
Index(
    "ix_trip_assignment_history",
    TripAssignment.organization_id,
    TripAssignment.trip_id,
    TripAssignment.assigned_at,
)
