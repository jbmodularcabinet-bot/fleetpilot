import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pycountry
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .permissions import Role


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OrganizationUpdate(StrictModel):
    name: str = Field(min_length=2, max_length=120)
    legal_name: str | None = Field(default=None, max_length=200)
    timezone: str = Field(max_length=80)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    country: str = Field(pattern=r"^[A-Z]{2}$")

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Unknown IANA timezone") from exc
        return value

    @field_validator("currency")
    @classmethod
    def valid_currency(cls, value: str) -> str:
        if pycountry.currencies.get(alpha_3=value) is None:
            raise ValueError("Unknown ISO currency")
        return value

    @field_validator("country")
    @classmethod
    def valid_country(cls, value: str) -> str:
        if pycountry.countries.get(alpha_2=value) is None:
            raise ValueError("Unknown ISO country")
        return value


class OrganizationCreate(OrganizationUpdate):
    slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class OrganizationOut(OrganizationCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    status: str


class MembershipCreate(StrictModel):
    email: EmailStr
    role: Role


class MembershipUpdate(StrictModel):
    role: Role
    active: bool


class OrganizationSelection(StrictModel):
    organization_id: uuid.UUID
