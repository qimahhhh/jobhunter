"""Price list, orders and deliveries.

Three tables answer three different questions and are kept apart on purpose:

* ``products`` — what something costs;
* ``orders`` — what someone agreed to pay, at the price it was when they agreed;
* ``deliveries`` — what they actually got for it.

There is no fourth table for credits. A balance column drifts from its ledger
the first time a write half-succeeds, and then nobody can say which of the two
is true; what a user has left is therefore always derived as "granted by paid
orders minus deliveries recorded against them".

Two invariants are enforced in code rather than documented:

* the amount is computed from the price book, so a client cannot name a price;
* ``paid`` is only reached through the payment step, and a delivery requires it.
  Without that, "transaction → delivery" is two unrelated tables.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    Delivery,
    InterviewSession,
    Order,
    Product,
    Resume,
    UserProfile,
    utc_now,
)

# The seed price book. It is a starting point, not a source of truth: prices
# live in the table so they can change without a deploy, and seeding only ever
# inserts a missing code — it never overwrites an edited price.
PRICE_BOOK: tuple[dict[str, Any], ...] = (
    {
        "code": "resume_deep_optimize",
        "name": "简历深度优化",
        "description": "按目标岗位逐条改写要点，只改写法、不改事实。",
        "price_cents": 990,
        "unit": "份",
        "grants": "resume",
        "features": [
            "对着岗位要求逐条对照，标出缺什么",
            "改写后的每句话都能追溯到原简历某一段",
            "交付时附修改说明与引用对照",
        ],
    },
    {
        "code": "interview_pack_3",
        "name": "模拟面试 3 次",
        "description": "按岗位需求逐条提问，允许追问一层，结束后给逐条复盘。",
        "price_cents": 2990,
        "unit": "次",
        "grants": "interview",
        "features": [
            "问题对准岗位需求，不是通用题库",
            "会根据你的回答追问一层",
            "复盘逐条给判定，并引用你的原话",
        ],
    },
)

GRANT_KINDS = ("resume", "interview")
SIMULATED_PROVIDER = "simulated"


class BillingError(ValueError):
    """Base class for the rejections this module produces."""


class OrderNotFoundError(BillingError):
    """No such order."""


class PaymentNotAllowedError(BillingError):
    """The order is not in a state a payment can move."""


class DeliveryNotAllowedError(BillingError):
    """The order does not entitle the caller to this delivery."""


def _id() -> str:
    return uuid.uuid4().hex


def ensure_catalog(session: Session) -> None:
    """Insert any missing product, and leave existing rows alone.

    Called lazily on the paths that need a product rather than at startup, so a
    test that never touches billing does not seed a catalog it will not use.
    An existing row is not updated: a price someone changed by hand is the
    price, and a re-deploy is not a reason to revert it.
    """

    known = {code for (code,) in session.execute(select(Product.code))}
    missing = [item for item in PRICE_BOOK if item["code"] not in known]
    if not missing:
        return

    for item in missing:
        session.add(
            Product(
                id=_id(),
                code=item["code"],
                name=item["name"],
                description=item["description"],
                price_cents=item["price_cents"],
                unit=item["unit"],
                grants=item["grants"],
                features=list(item["features"]),
            )
        )
    session.commit()


def _product(session: Session, code: str) -> Product:
    product = session.scalar(select(Product).where(Product.code == code))
    if product is None or not product.active:
        raise BillingError(f"没有这个商品：{code}")
    return product


def list_products(session: Session) -> list[Product]:
    ensure_catalog(session)
    return list(
        session.scalars(
            select(Product).where(Product.active.is_(True)).order_by(Product.price_cents)
        )
    )


def create_order(
    session: Session,
    *,
    user_id: str,
    product_code: str,
    quantity: int = 1,
    idempotency_key: str | None = None,
) -> tuple[Order, bool]:
    """Create an order, or hand back the one this request already made.

    The second return value says which happened, so the route can answer ``201``
    for a new order and ``200`` for a replay instead of calling both "created".
    """

    ensure_catalog(session)

    if idempotency_key:
        existing = session.scalar(
            select(Order).where(
                Order.user_id == user_id,
                Order.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            return existing, False

    product = _product(session, product_code)

    order = Order(
        id=_id(),
        user_id=user_id,
        product_code=product.code,
        quantity=quantity,
        # The only place an amount is decided.
        amount_cents=product.price_cents * quantity,
        currency=product.currency,
        status="created",
        idempotency_key=idempotency_key,
    )
    session.add(order)
    try:
        session.commit()
    except Exception:
        # Two retries landing at once: the unique index decided, not us. The
        # other request's order is the answer for both.
        session.rollback()
        if idempotency_key:
            existing = session.scalar(
                select(Order).where(
                    Order.user_id == user_id,
                    Order.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                return existing, False
        raise
    session.refresh(order)
    return order, True


def get_order(session: Session, order_id: str) -> Order:
    order = session.get(Order, order_id)
    if order is None:
        raise OrderNotFoundError("order not found")
    return order


def mark_paid(session: Session, order_id: str) -> Order:
    """Move a new order to paid. Paying twice changes nothing the second time.

    A payment callback is retried by every provider in the world, so this has to
    be idempotent: the second call must not move ``paid_at`` or invent a second
    delivery slot.
    """

    order = get_order(session, order_id)
    if order.status == "paid":
        return order
    if order.status != "created":
        raise PaymentNotAllowedError(f"订单状态为 {order.status}，不能再支付")

    order.status = "paid"
    order.provider = SIMULATED_PROVIDER
    order.provider_ref = f"sim-{_id()[:12]}"
    order.paid_at = utc_now()
    session.commit()
    session.refresh(order)
    return order


def _grants_for(session: Session, product_code: str) -> str:
    product = session.scalar(select(Product).where(Product.code == product_code))
    if product is None:
        raise DeliveryNotAllowedError(f"订单指向的商品已不存在：{product_code}")
    return product.grants


def _ref_belongs_to_user(
    session: Session, kind: str, ref_id: str, user_id: str
) -> bool:
    """Whether the thing being delivered actually belongs to the buyer."""

    if kind == "resume":
        resume = session.get(Resume, ref_id)
        return resume is not None and resume.user_id == user_id
    if kind == "interview":
        interview = session.get(InterviewSession, ref_id)
        if interview is None:
            return False
        profile = session.get(UserProfile, interview.user_profile_id)
        return profile is not None and profile.user_id == user_id
    return False


def quota(session: Session, user_id: str) -> dict[str, tuple[int, int]]:
    """(granted, used) per kind, derived from paid orders and deliveries."""

    paid = list(
        session.scalars(
            select(Order).where(Order.user_id == user_id, Order.status == "paid")
        )
    )
    codes = {order.product_code for order in paid}
    grants: dict[str, str] = {}
    if codes:
        for product in session.scalars(select(Product).where(Product.code.in_(codes))):
            grants[product.code] = product.grants

    granted = {kind: 0 for kind in GRANT_KINDS}
    for order in paid:
        kind = grants.get(order.product_code)
        if kind in granted:
            granted[kind] += order.quantity

    used = {kind: 0 for kind in GRANT_KINDS}
    paid_ids = {order.id for order in paid}
    if paid_ids:
        for delivery in session.scalars(
            select(Delivery).where(Delivery.order_id.in_(paid_ids))
        ):
            if delivery.kind in used:
                used[delivery.kind] += 1

    return {kind: (granted[kind], used[kind]) for kind in GRANT_KINDS}


def add_delivery(session: Session, order_id: str, ref_id: str) -> Delivery:
    """Record what the buyer got, against the order that paid for it.

    The kind is derived from the product, not from the request: a caller that
    could name the kind could spend an interview credit on a resume.
    """

    order = get_order(session, order_id)
    if order.status != "paid":
        raise DeliveryNotAllowedError("订单未支付，不能交付")

    kind = _grants_for(session, order.product_code)
    if kind not in GRANT_KINDS:
        # A product whose grants is misspelled would otherwise be delivered
        # without ever being counted against anything.
        raise DeliveryNotAllowedError(f"商品没有对应的交付类型：{kind}")
    if not _ref_belongs_to_user(session, kind, ref_id, order.user_id):
        raise DeliveryNotAllowedError(f"找不到属于该用户的 {kind} 记录：{ref_id}")

    granted, used = quota(session, order.user_id)[kind]
    if used >= granted:
        raise DeliveryNotAllowedError(
            f"{kind} 次数已用完（已用 {used}/{granted}），先下单再交付"
        )

    delivery = Delivery(id=_id(), order_id=order.id, kind=kind, ref_id=ref_id)
    session.add(delivery)
    session.commit()
    session.refresh(delivery)
    return delivery


def order_history(
    session: Session, user_id: str
) -> tuple[list[Order], dict[str, tuple[int, int]]]:
    orders = list(
        session.scalars(
            select(Order)
            .where(Order.user_id == user_id)
            .order_by(Order.created_at.desc())
        )
    )
    return orders, quota(session, user_id)
