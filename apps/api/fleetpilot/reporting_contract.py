"""MVP1 report contract. Canonical money remains server-side Decimal."""

import re
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

VERSION = "mvp1-contribution-v1"
ZERO = Decimal("0.00")
CENT = Decimal("0.01")
QUALIFICATION = (
    "Contribution equals reviewed operational revenue minus reviewed direct trip costs. "
    "It excludes maintenance allocation, depreciation, financing, insurance, company "
    "overhead, and taxes. It is not net profit or cash collected."
)
LIFECYCLES = (
    "SCHEDULED",
    "DISPATCHED",
    "PICKUP",
    "LOADED",
    "IN_TRANSIT",
    "DELIVERED",
    "COMPLETED",
    "CANCELLED",
)
REPORTS = (
    "executive-contribution",
    "trip-contribution",
    "customer-contribution",
    "direct-costs",
    "financial-exceptions",
    "cash-advances",
)
REQUIRED_ACCESS = (
    "trip_financials.read",
    "trip_profitability.read",
    "expenses.read",
    "fuel.read",
    "cash_advance.read",
    "financial_review.read",
)
MAX_COHORT = 5000
MAX_EXPORT_ROWS = 20000


def money(value: Decimal) -> str:
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def percent(numerator: Decimal, denominator: Decimal) -> str | None:
    return money(numerator / denominator * Decimal("100")) if denominator else None


class ReportFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date_from: date | None = None
    date_to: date | None = None
    trip_id: UUID | None = None
    customer_id: UUID | None = None
    vehicle_id: UUID | None = None
    lifecycle: str | None = Field(None, max_length=30)
    financial_status: Literal["FINAL", "PROVISIONAL"] | None = None
    dataset: Literal["business", "synthetic"] = "business"
    limit: int = Field(50, ge=1, le=100)
    offset: int = Field(0, ge=0, le=MAX_EXPORT_ROWS)
    format: Literal["json", "csv", "print"] = "json"

    @field_validator("lifecycle")
    @classmethod
    def valid_lifecycle(cls, value):
        if value is not None and value not in LIFECYCLES:
            raise ValueError("Unknown trip lifecycle status")
        return value

    @model_validator(mode="after")
    def ordered(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("Start date must not follow end date")
        return self

    def bounds(self, zone: str):
        tz = ZoneInfo(zone)
        today = datetime.now(tz).date()
        last = self.date_to or today
        first = self.date_from or last.replace(day=1)
        if first > last or (last - first).days > 366 or last == date.max:
            raise ValueError("Select an ordered date range of at most 367 days")
        return (
            first,
            last,
            datetime.combine(first, time.min, tz).astimezone(timezone.utc),
            datetime.combine(last + timedelta(days=1), time.min, tz).astimezone(timezone.utc),
        )


class ReportingPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    low_margin_percent: Decimal = Field(Decimal("15.00"), ge=0, le=100, decimal_places=2)
    direct_cost_pressure_percent: Decimal = Field(Decimal("70.00"), ge=0, le=100, decimal_places=2)
    cost_concentration_percent: Decimal = Field(Decimal("50.00"), ge=0, le=100, decimal_places=2)
    material_change_php: Decimal = Field(Decimal("1000.00"), gt=0, le=10000000, decimal_places=2)

    @field_validator(
        "low_margin_percent",
        "direct_cost_pressure_percent",
        "cost_concentration_percent",
        "material_change_php",
        mode="before",
    )
    @classmethod
    def exact_input(cls, value):
        if not isinstance(value, (str, Decimal)):
            raise ValueError("Thresholds must be exact decimal strings")
        if not re.fullmatch(r"[0-9]{1,8}(?:\.[0-9]{1,2})?", str(value)):
            raise ValueError("Use a non-negative decimal string with at most two places")
        return value
