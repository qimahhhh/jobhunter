"""The billing contract the checkout page talks to.

Note what ``OrderCreate`` does not contain: the amount. A price in a request
body is a price the client chose, and a price the client chose is not a price —
the server computes it from the catalog and stores what it computed, so a later
price change cannot rewrite what someone already agreed to.

``PaymentRequest.provider`` is a one-value literal on purpose. Real channels
arrive as a callback from someone else, with a signature to check; sharing this
route with them would turn a provider's call into a call the buyer can make.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

OrderStatus = Literal["created", "paid", "cancelled", "refunded"]


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    description: str = ""
    price_cents: int
    currency: str = "CNY"
    unit: str = "份"
    grants: str
    features: list[str] = Field(default_factory=list)


class OrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    product_code: str
    quantity: int = Field(default=1, ge=1, le=20)
    # Lets a checkout page retry without creating a second order. Optional,
    # because a caller that sends nothing still gets a plain order.
    idempotency_key: str | None = Field(default=None, max_length=64)


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    product_code: str
    quantity: int
    amount_cents: int
    currency: str
    status: OrderStatus
    provider: str | None = None
    provider_ref: str | None = None
    created_at: datetime
    paid_at: datetime | None = None


class PaymentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["simulated"] = "simulated"


class DeliveryCreate(BaseModel):
    """Which artifact was delivered. The kind is derived from the product."""

    model_config = ConfigDict(extra="forbid")

    ref_id: str


class DeliveryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    order_id: str
    kind: str
    ref_id: str
    created_at: datetime


class QuotaLine(BaseModel):
    granted: int
    used: int
    remaining: int


class OrderHistory(BaseModel):
    """The transaction ledger a user page needs, with what it still buys."""

    user_id: str
    orders: list[OrderRead] = Field(default_factory=list)
    resume: QuotaLine
    interview: QuotaLine
