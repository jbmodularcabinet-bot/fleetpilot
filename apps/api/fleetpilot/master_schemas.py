import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, model_validator

from .schemas import StrictModel


def normalized_code(value: str) -> str:
    return value.upper()


Code = Annotated[
    str,
    Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9][A-Za-z0-9 -]*$"),
    AfterValidator(normalized_code),
]
Phone = Annotated[str, Field(max_length=30, pattern=r"^[+0-9() .-]{3,30}$")]
Note = Annotated[str, Field(max_length=4000)]


class CustomerInput(StrictModel):
    customer_code: Code
    company_name: str = Field(min_length=2, max_length=160)
    contact_person: str | None = Field(default=None, max_length=120)
    phone: Phone | None = None
    email: EmailStr | None = None
    billing_address: Note | None = None
    pickup_notes: Note | None = None
    delivery_notes: Note | None = None
    payment_terms: str | None = Field(default=None, max_length=120)
    notes: Note | None = None


class VehicleInput(StrictModel):
    unit_number: Code
    plate_number: Annotated[
        str,
        Field(min_length=2, max_length=30, pattern=r"^[A-Za-z0-9][A-Za-z0-9 -]*$"),
        AfterValidator(normalized_code),
    ]
    vehicle_type: str = Field(min_length=2, max_length=80)
    make: str | None = Field(default=None, max_length=80)
    model: str | None = Field(default=None, max_length=80)
    year: int | None = Field(default=None, ge=1900, le=2100)
    capacity: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=3)
    capacity_unit: Literal["kg", "tonnes", "m3", "pallets"] | None = None
    odometer: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=1)
    registration_expiry: date | None = None
    notes: Note | None = None

    @model_validator(mode="after")
    def capacity_pair(self):
        if (self.capacity is None) != (self.capacity_unit is None):
            raise ValueError("Capacity and capacity unit must be supplied together")
        return self


class DriverInput(StrictModel):
    user_id: uuid.UUID | None = None
    employee_number: Code
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    phone: Phone | None = None
    email: EmailStr | None = None
    license_number: Code | None = None
    license_type: str | None = Field(default=None, max_length=80)
    license_expiry: date | None = None
    employment_status: Literal["ACTIVE", "ON_LEAVE", "SUSPENDED"] = "ACTIVE"
    emergency_contact_name: str | None = Field(default=None, max_length=120)
    emergency_contact_phone: Phone | None = None
    notes: Note | None = None


class AssignmentInput(StrictModel):
    vehicle_id: uuid.UUID
    driver_id: uuid.UUID
    notes: Note | None = None


class RecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    organization_id: uuid.UUID
    created_by: uuid.UUID
    updated_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class CustomerOut(CustomerInput, RecordOut):
    status: Literal["ACTIVE", "INACTIVE"]


class VehicleOut(VehicleInput, RecordOut):
    status: Literal["AVAILABLE", "ASSIGNED", "MAINTENANCE", "INACTIVE"]


class DriverOut(DriverInput, RecordOut):
    employment_status: Literal["ACTIVE", "ON_LEAVE", "SUSPENDED", "INACTIVE"]
    operational_status: Literal["UNASSIGNED", "ASSIGNED", "INACTIVE"]


class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    organization_id: uuid.UUID
    vehicle_id: uuid.UUID
    driver_id: uuid.UUID
    assigned_at: datetime
    unassigned_at: datetime | None
    is_current: bool
    notes: str | None
    created_by: uuid.UUID
    created_at: datetime
