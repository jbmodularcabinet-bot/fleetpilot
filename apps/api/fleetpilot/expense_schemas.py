"""Decimal strings are the wire contract; never accept binary floating point money."""

import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BeforeValidator, Field, model_validator

from .trip_schemas import VersionInput

Category = Literal[
    "FUEL",
    "TOLL",
    "PARKING",
    "DRIVER_ALLOWANCE",
    "DRIVER_CASH_ADVANCE",
    "HELPER_ALLOWANCE",
    "LOADING_FEE",
    "UNLOADING_FEE",
    "SUBCONTRACTOR",
    "OTHER",
]


def decimal_string(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,10}(\.\d{1,4})?", value):
        raise ValueError("Use a plain decimal string, without exponent or separators.")
    return Decimal(value)


Exact = Annotated[Decimal, BeforeValidator(decimal_string)]


class ExpenseInput(VersionInput):
    category: Category
    currency: Literal["PHP"] = "PHP"
    occurred_at: AwareDatetime
    amount: Exact | None = Field(None, gt=0, le=10000000, decimal_places=2)
    liters: Exact | None = Field(None, gt=0, le=10000, decimal_places=3)
    price_per_liter: Exact | None = Field(None, gt=0, le=10000, decimal_places=4)
    odometer: Exact | None = Field(None, ge=0, le=10000000, decimal_places=1)
    description: str | None = Field(None, max_length=2000)
    vendor_name: str | None = Field(None, max_length=160)
    reference_number: str | None = Field(None, max_length=120)

    @model_validator(mode="after")
    def category_fields(self):
        if self.category == "FUEL":
            if self.liters is None or self.price_per_liter is None or self.amount is not None:
                raise ValueError("Fuel requires liters and price; the server computes amount.")
            if not 0 < self.total <= 10000000:
                raise ValueError("Calculated fuel amount must be between 0.01 and 10000000 PHP.")
        elif self.amount is None or any(
            x is not None for x in (self.liters, self.price_per_liter, self.odometer)
        ):
            raise ValueError("Expense requires amount; fuel fields are only valid for Fuel.")
        if self.category == "OTHER" and len((self.description or "").strip()) < 3:
            raise ValueError("Other requires an explanation.")
        if self.category == "SUBCONTRACTOR" and not (self.vendor_name or "").strip():
            raise ValueError("Subcontractor requires a vendor/payee.")
        return self

    @property
    def total(self):
        return (
            (self.liters * self.price_per_liter) if self.category == "FUEL" else self.amount
        ).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)


class CorrectionInput(ExpenseInput):
    reason: str = Field(min_length=3, max_length=2000)


class ReviewInput(VersionInput):
    notes: str | None = Field(None, max_length=2000)


class VoidInput(VersionInput):
    reason: str = Field(min_length=3, max_length=2000)
