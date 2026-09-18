from typing import Literal

from pydantic import Field, model_validator

from .trip_schemas import VersionInput

ExceptionType = Literal[
    "RECIPIENT_UNAVAILABLE",
    "WRONG_ADDRESS",
    "INCOMPLETE_ADDRESS",
    "DELIVERY_REJECTED",
    "DAMAGED_CARGO",
    "PARTIAL_DELIVERY",
    "SITE_ACCESS_ISSUE",
    "VEHICLE_ISSUE",
    "DRIVER_ISSUE",
    "OTHER",
]
EvidenceType = Literal["DELIVERY_PHOTO", "SIGNATURE", "EXCEPTION_PHOTO", "OTHER_DELIVERY_EVIDENCE"]


class PODInput(VersionInput):
    recipient_name: str = Field(min_length=1, max_length=160)
    recipient_role: str | None = Field(None, max_length=120)
    driver_confirmed: Literal[True]
    signature_confirmed: bool = False
    notes: str | None = Field(None, max_length=4000)


class ExceptionInput(VersionInput):
    exception_type: ExceptionType
    notes: str | None = Field(None, max_length=4000)

    @model_validator(mode="after")
    def other_notes(self):
        if self.exception_type == "OTHER" and (not self.notes or len(self.notes.strip()) < 3):
            raise ValueError("Other requires notes")
        return self


class ResolveInput(VersionInput):
    resolution_notes: str = Field(min_length=3, max_length=4000)
