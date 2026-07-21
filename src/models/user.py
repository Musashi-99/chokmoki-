from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class Address(BaseModel):
    """Shape mirrors ShippingAddressInOrder (src/models/order.py) field for
    field, so an address picked at checkout maps onto what orders already
    store with no translation layer.
    """

    id: str = Field(default_factory=lambda: uuid4().hex)
    label: str = "Home"
    full_name: str
    phone: str
    address_line1: str
    address_line2: Optional[str] = ""
    city: str
    state: str
    postal_code: str
    country: str = "India"
    is_default: bool = False


class AddressInput(BaseModel):
    label: str = "Home"
    full_name: str
    phone: str
    address_line1: str
    address_line2: Optional[str] = ""
    city: str
    state: str
    postal_code: str
    country: str = "India"
    is_default: bool = False


class User(BaseModel):
    id: str = Field(default_factory=lambda: f"usr_{uuid4().hex}")
    phone: str
    phone_verified: bool = True
    name: Optional[str] = None
    email: Optional[str] = None
    addresses: list[Address] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_login_at: Optional[datetime] = None

    model_config = {
        "json_encoders": {datetime: lambda v: v.isoformat()},
    }


class UserProfileUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None


@dataclass(frozen=True)
class CustomerPrincipal:
    user_id: str
    phone: str
    session_id: str
    jti: str


@dataclass(frozen=True)
class CustomerAuthTokens:
    access_token: str
    refresh_token: str
    session_id: str
    expires_in: int
    token_type: str = "Bearer"
