"""Pydantic models for every request and response."""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .errors import Forbidden


class Unit(str, Enum):
    kg = "kg"
    bag = "bag"
    crate = "crate"


class Grade(str, Enum):
    A = "A"
    B = "B"
    C = "C"


class InventoryStatus(str, Enum):
    available = "available"
    reserved = "reserved"
    sold = "sold"


class FarmerStatus(str, Enum):
    active = "active"
    suspended = "suspended"
    inactive = "inactive"


class Role(str, Enum):
    farmer = "farmer"
    officer = "officer"
    admin = "admin"


# ---------------------------------------------------------------- validators
PHONE_RE = re.compile(r"^2547\d{8}$")
NATIONAL_ID_RE = re.compile(r"^\d{6,9}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalise_phone(raw: str) -> str:
    """07XXXXXXXX, +2547XXXXXXXX and 2547XXXXXXXX all become 2547XXXXXXXX."""
    p = re.sub(r"[\s\-()]", "", raw)
    if p.startswith("+"):
        p = p[1:]
    if re.fullmatch(r"07\d{8}", p):
        p = "254" + p[1:]
    return p


def _phone(v: str) -> str:
    p = normalise_phone(v)
    if not PHONE_RE.fullmatch(p):
        raise ValueError("Phone must be in 2547XXXXXXXX format (e.g. 254712345678)")
    return p


def _email(v: str | None) -> str | None:
    if v is None or v == "":
        return None
    v = v.strip().lower()
    if not EMAIL_RE.fullmatch(v) or len(v) > 254:
        raise ValueError("Enter a valid email address")
    return v


Phone = Annotated[str, Field(max_length=20)]
Quantity = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
PriceMinor = Annotated[int, Field(ge=0, le=10**12, description="KES cents (minor units), e.g. 4500 = KES 45.00")]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ---------------------------------------------------------------- auth
class RegisterRequest(Strict):
    full_name: str = Field(min_length=2, max_length=120)
    national_id: str
    phone: Phone
    email: str | None = None
    password: str = Field(min_length=8, max_length=72)
    ward_id: int = Field(gt=0)
    plot_name: str = Field(default="Home plot", min_length=1, max_length=80)

    @field_validator("national_id")
    @classmethod
    def _nid(cls, v: str) -> str:
        if not NATIONAL_ID_RE.fullmatch(v):
            raise ValueError("National ID must be 6-9 digits")
        return v

    @field_validator("phone")
    @classmethod
    def _ph(cls, v: str) -> str:
        return _phone(v)

    @field_validator("email")
    @classmethod
    def _em(cls, v: str | None) -> str | None:
        return _email(v)

    @field_validator("password")
    @classmethod
    def _pw(cls, v: str) -> str:
        if not (re.search(r"[A-Za-z]", v) and re.search(r"\d", v)):
            raise ValueError("Password must contain at least one letter and one number")
        return v


class LoginRequest(Strict):
    identifier: str = Field(min_length=3, max_length=254, description="Phone (2547XXXXXXXX / 07XXXXXXXX) or email")
    password: str = Field(min_length=1, max_length=72)


class RefreshRequest(Strict):
    refresh_token: str = Field(min_length=10, max_length=2048)


class SessionUser(BaseModel):
    id: UUID
    role: Role
    farmer_id: UUID | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    expires_at: int
    user: SessionUser | None = None


# ---------------------------------------------------------------- lookups
class LocationOut(BaseModel):
    ward_id: int
    ward: str
    sub_county_id: int
    sub_county: str
    county_id: int
    county: str


class ProduceTypeOut(BaseModel):
    id: int
    name: str
    category: str


# ---------------------------------------------------------------- farmers
class PlotOut(BaseModel):
    id: UUID
    name: str
    ward_id: int
    ward: str
    sub_county: str
    county: str
    size_acres: Decimal | None = None
    is_active: bool


class FarmerOut(BaseModel):
    id: UUID
    full_name: str
    national_id: str
    phone: str
    email: str | None = None
    ward_id: int
    ward: str
    sub_county: str
    county: str
    status: FarmerStatus
    created_at: datetime
    updated_at: datetime
    plots: list[PlotOut] = []


class PlotUpsert(Strict):
    id: UUID | None = Field(default=None, description="Omit to create a new plot; set to update one of your own")
    name: str = Field(min_length=1, max_length=80)
    ward_id: int = Field(gt=0)
    size_acres: Decimal | None = Field(default=None, gt=0, max_digits=8, decimal_places=2)
    is_active: bool = True


# Fields a farmer must never be able to set through the API.
PROTECTED_FARMER_FIELDS = {"status", "role", "user_id", "id", "farmer_id", "national_id", "created_at", "updated_at"}


class FarmerPatch(Strict):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    phone: Phone | None = None
    email: str | None = None
    plots: list[PlotUpsert] | None = Field(default=None, max_length=20)

    @model_validator(mode="before")
    @classmethod
    def _reject_protected(cls, data):
        # Runs before field validation: asking to change status/role is a PERMISSION problem (403),
        # not a typo (422).
        if isinstance(data, dict) and (hit := PROTECTED_FARMER_FIELDS & set(data)):
            raise Forbidden(f"You may not change: {', '.join(sorted(hit))}", code="FORBIDDEN_FIELD")
        return data

    @field_validator("phone")
    @classmethod
    def _ph(cls, v: str | None) -> str | None:
        return None if v is None else _phone(v)

    @field_validator("email")
    @classmethod
    def _em(cls, v: str | None) -> str | None:
        return _email(v)


# ---------------------------------------------------------------- inventory
class InventoryCreate(Strict):
    plot_id: UUID
    produce_type_id: int = Field(gt=0)
    quantity: Quantity
    unit: Unit
    grade: Grade
    expected_harvest_date: date
    asking_price_minor: PriceMinor
    client_request_id: UUID | None = Field(
        default=None, description="Client-generated UUID; repeating it returns the same record (double-tap safe)")


class InventoryPatch(Strict):
    plot_id: UUID | None = None
    produce_type_id: int | None = Field(default=None, gt=0)
    quantity: Quantity | None = None
    unit: Unit | None = None
    grade: Grade | None = None
    status: InventoryStatus | None = None
    expected_harvest_date: date | None = None
    asking_price_minor: PriceMinor | None = None

    @model_validator(mode="after")
    def _non_empty(self):
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update")
        for name in self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class InventoryOut(BaseModel):
    id: UUID
    farmer_id: UUID
    farmer_name: str
    plot_id: UUID
    plot_name: str
    ward_id: int
    ward: str
    produce_type_id: int
    produce_type: str
    quantity: Decimal
    unit: Unit
    grade: Grade
    status: InventoryStatus
    expected_harvest_date: date
    asking_price_minor: int
    currency: str
    sold_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int
    has_more: bool
