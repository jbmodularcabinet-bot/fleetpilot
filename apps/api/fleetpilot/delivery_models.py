"""Explicit delivery attempts, POD, evidence and exception history."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base


class DeliveryAttempt(Base):
    __tablename__ = "delivery_attempts"
    __table_args__ = (
        UniqueConstraint("organization_id", "trip_id", "id", name="uq_delivery_attempt_identity"),
        UniqueConstraint(
            "organization_id", "trip_id", "attempt_number", name="uq_delivery_attempt_number"
        ),
        ForeignKeyConstraint(["organization_id", "trip_id"], ["trips.organization_id", "trips.id"]),
        CheckConstraint(
            "status IN ('IN_PROGRESS','DELIVERED','FAILED')", name="ck_delivery_attempt_status"
        ),
        CheckConstraint(
            "attempt_number > 0 AND ((status = 'IN_PROGRESS' AND completed_at IS NULL) OR (status <> 'IN_PROGRESS' AND completed_at IS NOT NULL))",
            name="ck_delivery_attempt_completion",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    trip_id: Mapped[uuid.UUID]
    attempt_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="IN_PROGRESS")
    arrived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DeliveryEvidence(Base):
    __tablename__ = "delivery_evidence"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "trip_id", "delivery_attempt_id", "id", name="uq_evidence_identity"
        ),
        ForeignKeyConstraint(
            ["organization_id", "trip_id", "delivery_attempt_id"],
            [
                "delivery_attempts.organization_id",
                "delivery_attempts.trip_id",
                "delivery_attempts.id",
            ],
        ),
        ForeignKeyConstraint(
            ["organization_id", "trip_id", "delivery_attempt_id", "supersedes_id"],
            [
                "delivery_evidence.organization_id",
                "delivery_evidence.trip_id",
                "delivery_evidence.delivery_attempt_id",
                "delivery_evidence.id",
            ],
        ),
        CheckConstraint(
            "evidence_type IN ('DELIVERY_PHOTO','SIGNATURE','EXCEPTION_PHOTO','OTHER_DELIVERY_EVIDENCE')",
            name="ck_evidence_type",
        ),
        CheckConstraint("status IN ('ACTIVE','SUPERSEDED')", name="ck_evidence_status"),
        CheckConstraint("file_size > 0 AND file_size <= 5242880", name="ck_evidence_size"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    trip_id: Mapped[uuid.UUID]
    delivery_attempt_id: Mapped[uuid.UUID]
    evidence_type: Mapped[str] = mapped_column(String(30))
    storage_key: Mapped[str] = mapped_column(String(160), unique=True)
    original_filename: Mapped[str] = mapped_column(String(160))
    content_type: Mapped[str] = mapped_column(String(30))
    file_size: Mapped[int] = mapped_column(Integer)
    checksum: Mapped[str] = mapped_column(String(64))
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    supersedes_id: Mapped[uuid.UUID | None]


class ProofOfDelivery(Base):
    __tablename__ = "proof_of_delivery"
    __table_args__ = (
        UniqueConstraint("organization_id", "trip_id", name="uq_pod_trip"),
        UniqueConstraint("organization_id", "delivery_attempt_id", name="uq_pod_attempt"),
        ForeignKeyConstraint(
            ["organization_id", "trip_id", "delivery_attempt_id"],
            [
                "delivery_attempts.organization_id",
                "delivery_attempts.trip_id",
                "delivery_attempts.id",
            ],
        ),
        ForeignKeyConstraint(
            ["organization_id", "trip_id", "delivery_attempt_id", "signature_evidence_id"],
            [
                "delivery_evidence.organization_id",
                "delivery_evidence.trip_id",
                "delivery_evidence.delivery_attempt_id",
                "delivery_evidence.id",
            ],
        ),
        ForeignKeyConstraint(
            ["organization_id", "confirmed_by_driver_id"], ["drivers.organization_id", "drivers.id"]
        ),
        CheckConstraint(
            "length(trim(recipient_name)) > 0 AND driver_confirmed", name="ck_pod_confirmation"
        ),
        CheckConstraint(
            "(status = 'SUBMITTED' AND reviewed_at IS NULL AND reviewed_by IS NULL) OR (status = 'REVIEWED' AND reviewed_at IS NOT NULL AND reviewed_by IS NOT NULL)",
            name="ck_pod_review",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    trip_id: Mapped[uuid.UUID]
    delivery_attempt_id: Mapped[uuid.UUID]
    recipient_name: Mapped[str] = mapped_column(String(160))
    recipient_role: Mapped[str | None] = mapped_column(String(120))
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confirmed_by_driver_id: Mapped[uuid.UUID]
    confirmed_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    driver_confirmed: Mapped[bool] = mapped_column(Boolean)
    signature_evidence_id: Mapped[uuid.UUID | None]
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="SUBMITTED")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DeliveryException(Base):
    __tablename__ = "delivery_exceptions"
    __table_args__ = (
        UniqueConstraint("organization_id", "delivery_attempt_id", name="uq_exception_attempt"),
        ForeignKeyConstraint(
            ["organization_id", "trip_id", "delivery_attempt_id"],
            [
                "delivery_attempts.organization_id",
                "delivery_attempts.trip_id",
                "delivery_attempts.id",
            ],
        ),
        CheckConstraint(
            "exception_type IN ('RECIPIENT_UNAVAILABLE','WRONG_ADDRESS','INCOMPLETE_ADDRESS','DELIVERY_REJECTED','DAMAGED_CARGO','PARTIAL_DELIVERY','SITE_ACCESS_ISSUE','VEHICLE_ISSUE','DRIVER_ISSUE','OTHER')",
            name="ck_delivery_exception_type",
        ),
        CheckConstraint(
            "exception_type <> 'OTHER' OR (notes IS NOT NULL AND length(trim(notes)) >= 3)",
            name="ck_exception_other_notes",
        ),
        CheckConstraint(
            "(status = 'OPEN' AND resolved_at IS NULL AND resolved_by IS NULL AND resolution_notes IS NULL) OR (status = 'RETRY_AUTHORIZED' AND resolved_at IS NOT NULL AND resolved_by IS NOT NULL AND length(trim(resolution_notes)) >= 3)",
            name="ck_exception_resolution",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    trip_id: Mapped[uuid.UUID]
    delivery_attempt_id: Mapped[uuid.UUID]
    exception_type: Mapped[str] = mapped_column(String(30))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    resolution_notes: Mapped[str | None] = mapped_column(Text)


Index(
    "uq_open_delivery_attempt",
    DeliveryAttempt.organization_id,
    DeliveryAttempt.trip_id,
    unique=True,
    postgresql_where=text("status = 'IN_PROGRESS'"),
)
Index(
    "ix_attempt_trip_history",
    DeliveryAttempt.organization_id,
    DeliveryAttempt.trip_id,
    DeliveryAttempt.created_at,
)
Index(
    "ix_evidence_attempt",
    DeliveryEvidence.organization_id,
    DeliveryEvidence.delivery_attempt_id,
    DeliveryEvidence.uploaded_at,
)
Index(
    "uq_active_signature",
    DeliveryEvidence.organization_id,
    DeliveryEvidence.delivery_attempt_id,
    unique=True,
    postgresql_where=text("status = 'ACTIVE' AND evidence_type = 'SIGNATURE'"),
)
Index(
    "ix_exception_trip_status",
    DeliveryException.organization_id,
    DeliveryException.trip_id,
    DeliveryException.status,
)
