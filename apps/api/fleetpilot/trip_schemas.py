import uuid
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, model_validator

from .master_schemas import Note, Phone
from .schemas import StrictModel


class TripFields(StrictModel):
    customer_id: uuid.UUID
    pickup_name: str = Field(min_length=2, max_length=160)
    pickup_address: str = Field(min_length=2, max_length=2000)
    pickup_latitude: Decimal | None = Field(None, ge=-90, le=90, decimal_places=6)
    pickup_longitude: Decimal | None = Field(None, ge=-180, le=180, decimal_places=6)
    pickup_contact_name: str | None = Field(None, max_length=120)
    pickup_contact_phone: Phone | None = None
    delivery_name: str = Field(min_length=2, max_length=160)
    delivery_address: str = Field(min_length=2, max_length=2000)
    delivery_latitude: Decimal | None = Field(None, ge=-90, le=90, decimal_places=6)
    delivery_longitude: Decimal | None = Field(None, ge=-180, le=180, decimal_places=6)
    delivery_contact_name: str | None = Field(None, max_length=120)
    delivery_contact_phone: Phone | None = None
    scheduled_pickup_at: AwareDatetime
    scheduled_delivery_at: AwareDatetime | None = None
    reference_number: str | None = Field(None, max_length=120)
    customer_reference: str | None = Field(None, max_length=120)
    cargo_description: Note | None = None
    cargo_weight: Decimal | None = Field(None, ge=0, max_digits=14, decimal_places=3)
    cargo_weight_unit: Literal["kg", "tonnes"] | None = None
    special_instructions: Note | None = None
    dispatcher_notes: Note | None = None

    @model_validator(mode="after")
    def consistent(self):
        if self.scheduled_delivery_at and self.scheduled_delivery_at <= self.scheduled_pickup_at:
            raise ValueError("Delivery must be after pickup")
        for prefix in ("pickup", "delivery"):
            if (getattr(self, f"{prefix}_latitude") is None) != (
                getattr(self, f"{prefix}_longitude") is None
            ):
                raise ValueError("Coordinates require both latitude and longitude")
        if (self.cargo_weight is None) != (self.cargo_weight_unit is None):
            raise ValueError("Cargo weight and unit must be supplied together")
        return self


class TripCreate(TripFields):
    vehicle_id: uuid.UUID | None = None
    driver_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def paired_assignment(self):
        if (self.vehicle_id is None) != (self.driver_id is None):
            raise ValueError("Assign a vehicle and driver together")
        return self


class VersionInput(StrictModel):
    expected_version: int = Field(ge=1)


class TripUpdate(TripFields, VersionInput):
    pass


class TripAssign(VersionInput):
    vehicle_id: uuid.UUID
    driver_id: uuid.UUID


class TripTransition(VersionInput):
    action: Literal[
        "dispatch",
        "start_pickup",
        "arrive_pickup",
        "start_loading",
        "finish_loading",
        "depart_pickup",
        "arrive_delivery",
        "start_unloading",
        "finish_unloading",
        "deliver",
    ]
    notes: Note | None = None


class TripCancel(VersionInput):
    reason: Annotated[str, Field(min_length=3, max_length=2000)]


class TripComplete(VersionInput):
    closeout_reviewed: Literal[True]
    notes: Note | None = None


class TripNotes(VersionInput):
    dispatcher_notes: Note | None = None
