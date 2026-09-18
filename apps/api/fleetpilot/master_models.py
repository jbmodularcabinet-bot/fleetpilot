"""Tenant-owned master records; operational trip state is deliberately absent."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base, Timestamps


class MasterRecord(Timestamps):
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    updated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    notes: Mapped[str | None] = mapped_column(Text)


class Customer(MasterRecord, Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("organization_id", "customer_code", name="uq_customer_code"),
        UniqueConstraint("organization_id", "id", name="uq_customer_tenant_id"),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_customer_status"),
        CheckConstraint("customer_code = upper(customer_code)", name="ck_customer_code_normalized"),
    )
    customer_code: Mapped[str] = mapped_column(String(40))
    company_name: Mapped[str] = mapped_column(String(160))
    contact_person: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(320))
    billing_address: Mapped[str | None] = mapped_column(Text)
    pickup_notes: Mapped[str | None] = mapped_column(Text)
    delivery_notes: Mapped[str | None] = mapped_column(Text)
    payment_terms: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")


class Vehicle(MasterRecord, Base):
    __tablename__ = "vehicles"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_vehicle_tenant_id"),
        UniqueConstraint("organization_id", "unit_number", name="uq_vehicle_unit"),
        UniqueConstraint("organization_id", "plate_number", name="uq_vehicle_plate"),
        CheckConstraint(
            "status IN ('AVAILABLE','ASSIGNED','MAINTENANCE','INACTIVE')", name="ck_vehicle_status"
        ),
        CheckConstraint("capacity >= 0 AND odometer >= 0", name="ck_vehicle_nonnegative"),
        CheckConstraint("year BETWEEN 1900 AND 2100", name="ck_vehicle_year"),
        CheckConstraint(
            "(capacity IS NULL AND capacity_unit IS NULL) OR (capacity IS NOT NULL AND capacity_unit IS NOT NULL AND capacity_unit IN ('kg','tonnes','m3','pallets'))",
            name="ck_vehicle_capacity_unit",
        ),
        CheckConstraint(
            "unit_number = upper(unit_number) AND plate_number = upper(plate_number)",
            name="ck_vehicle_codes_normalized",
        ),
    )
    unit_number: Mapped[str] = mapped_column(String(40))
    plate_number: Mapped[str] = mapped_column(String(30))
    vehicle_type: Mapped[str] = mapped_column(String(80))
    make: Mapped[str | None] = mapped_column(String(80))
    model: Mapped[str | None] = mapped_column(String(80))
    year: Mapped[int | None]
    capacity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    capacity_unit: Mapped[str | None] = mapped_column(String(20))
    odometer: Mapped[Decimal | None] = mapped_column(Numeric(14, 1))
    # Monotonic reviewed-fuel reading; not accepted/exposed by master-data schemas.
    reviewed_fuel_odometer: Mapped[Decimal | None] = mapped_column(Numeric(9, 1))
    maintenance_odometer: Mapped[Decimal | None] = mapped_column(Numeric(9, 1))
    registration_expiry: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="AVAILABLE")


class Driver(MasterRecord, Base):
    __tablename__ = "drivers"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_driver_tenant_id"),
        UniqueConstraint("organization_id", "employee_number", name="uq_driver_employee"),
        UniqueConstraint("organization_id", "license_number", name="uq_driver_license"),
        UniqueConstraint("organization_id", "user_id", name="uq_driver_user"),
        CheckConstraint(
            "employment_status IN ('ACTIVE','ON_LEAVE','SUSPENDED','INACTIVE')",
            name="ck_driver_employment",
        ),
        CheckConstraint(
            "operational_status IN ('UNASSIGNED','ASSIGNED','INACTIVE')",
            name="ck_driver_operational",
        ),
        CheckConstraint(
            "employee_number = upper(employee_number) AND (license_number IS NULL OR license_number = upper(license_number))",
            name="ck_driver_codes_normalized",
        ),
        ForeignKeyConstraint(
            ["organization_id", "user_id"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_driver_membership",
        ),
    )
    user_id: Mapped[uuid.UUID | None]
    employee_number: Mapped[str] = mapped_column(String(40))
    first_name: Mapped[str] = mapped_column(String(80))
    last_name: Mapped[str] = mapped_column(String(80))
    phone: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(320))
    license_number: Mapped[str | None] = mapped_column(String(40))
    license_type: Mapped[str | None] = mapped_column(String(80))
    license_expiry: Mapped[date | None] = mapped_column(Date)
    employment_status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    operational_status: Mapped[str] = mapped_column(String(20), default="UNASSIGNED")
    emergency_contact_name: Mapped[str | None] = mapped_column(String(120))
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(30))


class VehicleDriverAssignment(Base):
    __tablename__ = "vehicle_driver_assignments"
    __table_args__ = (
        CheckConstraint(
            "(is_current AND unassigned_at IS NULL) OR (NOT is_current AND unassigned_at IS NOT NULL AND unassigned_at >= assigned_at)",
            name="ck_assignment_lifecycle",
        ),
        ForeignKeyConstraint(
            ["organization_id", "vehicle_id"],
            ["vehicles.organization_id", "vehicles.id"],
            name="fk_assignment_vehicle_tenant",
        ),
        ForeignKeyConstraint(
            ["organization_id", "driver_id"],
            ["drivers.organization_id", "drivers.id"],
            name="fk_assignment_driver_tenant",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    vehicle_id: Mapped[uuid.UUID]
    driver_id: Mapped[uuid.UUID]
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    unassigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


for model, status in [(Customer, "status"), (Vehicle, "status"), (Driver, "employment_status")]:
    Index(
        f"ix_{model.__tablename__}_tenant_status_created",
        model.organization_id,
        getattr(model, status),
        model.created_at,
    )
    Index(f"ix_{model.__tablename__}_tenant_created", model.organization_id, model.created_at)
for field in ("vehicle_id", "driver_id"):
    Index(
        f"uq_current_{field}",
        VehicleDriverAssignment.organization_id,
        getattr(VehicleDriverAssignment, field),
        unique=True,
        postgresql_where=text("is_current"),
    )
    Index(
        f"ix_assignment_{field}_history",
        VehicleDriverAssignment.organization_id,
        getattr(VehicleDriverAssignment, field),
        VehicleDriverAssignment.assigned_at,
    )
Index(
    "ix_assignment_tenant_created",
    VehicleDriverAssignment.organization_id,
    VehicleDriverAssignment.created_at,
)
