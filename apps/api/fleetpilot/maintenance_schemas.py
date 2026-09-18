"""Strict maintenance commands and deterministic threshold calculations."""

import uuid
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .expense_schemas import decimal_string

Service = Literal[
    "ENGINE_OIL",
    "OIL_FILTER",
    "AIR_FILTER",
    "FUEL_FILTER",
    "BRAKES",
    "TIRES",
    "TRANSMISSION",
    "COOLING_SYSTEM",
    "BATTERY",
    "GENERAL_INSPECTION",
    "REGISTRATION_RELATED_CHECK",
    "OTHER",
]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ScheduleInput(Strict):
    service_type: Service
    interval_type: Literal["ODOMETER", "DATE", "ODOMETER_OR_DATE"]
    odometer_interval_km: int | None = Field(None, ge=1, le=1000000, strict=True)
    date_interval_days: int | None = Field(None, ge=1, le=3650, strict=True)
    last_service_odometer: Decimal | None = None
    last_service_at: date | None = None
    warning_km: int = Field(0, ge=0, le=1000000, strict=True)
    warning_days: int = Field(0, ge=0, le=3650, strict=True)
    is_active: bool = True
    notes: str | None = Field(None, max_length=2000)

    @field_validator("last_service_odometer", mode="before")
    @classmethod
    def odo(cls, v):
        return odometer(v)

    @model_validator(mode="after")
    def intervals(self):
        km = self.interval_type != "DATE"
        days = self.interval_type != "ODOMETER"
        if km != (
            self.odometer_interval_km is not None and self.last_service_odometer is not None
        ) or days != (self.date_interval_days is not None and self.last_service_at is not None):
            raise ValueError("Provide the baseline and interval for each selected threshold.")
        if (
            not km
            and (
                self.odometer_interval_km is not None
                or self.last_service_odometer is not None
                or self.warning_km
            )
        ) or (
            not days
            and (
                self.date_interval_days is not None
                or self.last_service_at is not None
                or self.warning_days
            )
        ):
            raise ValueError("Unused threshold fields must be empty.")
        if self.service_type == "OTHER" and not self.notes:
            raise ValueError("Other service requires a description.")
        if self.warning_km > (self.odometer_interval_km or 0) or self.warning_days > (
            self.date_interval_days or 0
        ):
            raise ValueError("Warning cannot exceed its interval.")
        return self


def odometer(v):
    if v is None:
        return None
    n = decimal_string(v)
    if n < 0 or n > 10000000 or n.as_tuple().exponent < -1:
        raise ValueError(
            "Odometer must be a decimal string, 0–10000000, at most one decimal place."
        )
    return n


def next_due(data, reading=None, completed=None):
    km = data.get("odometer_interval_km")
    days = data.get("date_interval_days")
    reading = data.get("last_service_odometer") if reading is None else reading
    completed = data.get("last_service_at") if completed is None else completed
    return {
        "next_due_odometer": reading + km if km else None,
        "next_due_at": completed + timedelta(days=days) if days else None,
    }


def schedule_state(row, reading, today):
    states = [0]
    for current, due, warning in [
        (reading, row.get("next_due_odometer"), row.get("warning_km", 0)),
        (today, row.get("next_due_at"), timedelta(days=row.get("warning_days", 0))),
    ]:
        if due is not None:
            states.append(
                3
                if current > due
                else 2
                if current == due
                else 1
                if current >= due - warning
                else 0
            )
    return ["OK", "UPCOMING", "DUE", "OVERDUE"][max(states)]


class WorkInput(Strict):
    vehicle_id: uuid.UUID
    maintenance_schedule_id: uuid.UUID | None = None
    defect_report_id: uuid.UUID | None = None
    trip_id: uuid.UUID | None = None
    type: Literal["PREVENTIVE", "REPAIR", "INSPECTION", "DEFECT_RESPONSE", "OTHER"]
    priority: Literal["LOW", "NORMAL", "HIGH", "CRITICAL"] = "NORMAL"
    title: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=3, max_length=4000)
    requires_vehicle_downtime: bool = False
    service_provider: str | None = Field(None, max_length=160)


class WorkAction(Strict):
    expected_version: int = Field(ge=1, strict=True)
    scheduled_at: datetime | None = None
    odometer_at_completion: Decimal | None = None
    work_performed: str | None = Field(None, max_length=4000)
    reason: str | None = Field(None, max_length=2000)

    @field_validator("odometer_at_completion", mode="before")
    @classmethod
    def odo(cls, v):
        return odometer(v)

    @field_validator("scheduled_at")
    @classmethod
    def zone(cls, v):
        if v and v.tzinfo is None:
            raise ValueError("Timezone required.")
        return v


class CostInput(Strict):
    type: Literal["PART", "LABOR", "OTHER"]
    description: str = Field(min_length=1, max_length=500)
    quantity: Decimal = Decimal("1")
    unit_cost: Decimal
    vendor: str | None = Field(None, max_length=160)
    reference: str | None = Field(None, max_length=120)

    @field_validator("quantity", "unit_cost", mode="before")
    @classmethod
    def number(cls, v):
        return decimal_string(v)

    @model_validator(mode="after")
    def bounds(self):
        if (
            not 0 < self.quantity <= 100000
            or not 0 <= self.unit_cost <= 10000000
            or self.quantity.as_tuple().exponent < -3
            or self.unit_cost.as_tuple().exponent < -4
            or self.total > 10000000
        ):
            raise ValueError("Cost quantity, amount or precision exceeds limit.")
        return self

    @property
    def total(self):
        return (self.quantity * self.unit_cost).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class DefectInput(Strict):
    vehicle_id: uuid.UUID
    trip_id: uuid.UUID | None = None
    severity: Literal["MINOR", "MODERATE", "SERIOUS", "CRITICAL"]
    category: Literal[
        "ENGINE",
        "BRAKES",
        "TIRES",
        "ELECTRICAL",
        "LIGHTS",
        "SUSPENSION",
        "STEERING",
        "COOLING",
        "TRANSMISSION",
        "BODY",
        "SAFETY_EQUIPMENT",
        "OTHER",
    ]
    description: str = Field(min_length=3, max_length=4000)
    reported_at_client: datetime

    @field_validator("reported_at_client")
    @classmethod
    def zone(cls, v):
        if v.tzinfo is None:
            raise ValueError("Timezone required.")
        return v


class ReviewInput(Strict):
    reason: str = Field(min_length=3, max_length=2000)
