from __future__ import annotations

import unittest

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.billing import (
    PRICE_BOOK,
    DeliveryNotAllowedError,
    add_delivery,
    create_order,
    mark_paid,
    order_history,
)
from backend.app.models import Base
from backend.app.schemas_billing import OrderCreate
from backend.app.schemas_resources import ResumeCreate, UserCreate
from backend.app.services import create_resume, create_user

RESUME_PRICE = next(
    item["price_cents"] for item in PRICE_BOOK if item["code"] == "resume_deep_optimize"
)


class BillingTest(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.session = sessionmaker(
            bind=engine, autoflush=False, expire_on_commit=False
        )()
        self.user = create_user(
            self.session, UserCreate(email="buyer@example.com", display_name="Buyer")
        )

    def tearDown(self) -> None:
        self.session.close()

    def _order(self, *, key: str | None = None, quantity: int = 1):
        order, created = create_order(
            self.session,
            user_id=self.user.id,
            product_code="resume_deep_optimize",
            quantity=quantity,
            idempotency_key=key,
        )
        return order, created

    def _resume(self, user_id: str) -> str:
        resume = create_resume(
            self.session,
            ResumeCreate(user_id=user_id, source_name="resume.pdf", content={}),
        )
        return resume.id

    def test_the_amount_comes_from_the_catalog_not_the_client(self) -> None:
        # A price in the request body is a price the client chose.
        with self.assertRaises(ValidationError):
            OrderCreate(
                user_id=self.user.id,
                product_code="resume_deep_optimize",
                amount_cents=1,
            )

        order, created = self._order(quantity=2)

        self.assertTrue(created)
        self.assertEqual(order.amount_cents, RESUME_PRICE * 2)
        self.assertEqual(order.status, "created")
        self.assertIsNone(order.paid_at)

    def test_a_replayed_checkout_returns_the_order_it_already_made(self) -> None:
        first, created = self._order(key="attempt-1")
        second, created_again = self._order(key="attempt-1")
        other, other_created = self._order(key="attempt-2")

        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first.id, second.id)
        # A different key is a different purchase, not a duplicate.
        self.assertTrue(other_created)
        self.assertNotEqual(first.id, other.id)

    def test_paying_twice_does_not_move_the_payment(self) -> None:
        order, _ = self._order()

        paid = mark_paid(self.session, order.id)
        again = mark_paid(self.session, order.id)

        self.assertEqual(paid.status, "paid")
        self.assertEqual(paid.provider, "simulated")
        self.assertIsNotNone(paid.paid_at)
        self.assertEqual(again.paid_at, paid.paid_at)
        self.assertEqual(again.provider_ref, paid.provider_ref)

    def test_a_delivery_requires_a_paid_order(self) -> None:
        order, _ = self._order()
        resume_id = self._resume(self.user.id)

        with self.assertRaises(DeliveryNotAllowedError):
            add_delivery(self.session, order.id, resume_id)

    def test_a_delivery_consumes_a_credit_and_then_refuses_another(self) -> None:
        order, _ = self._order()
        mark_paid(self.session, order.id)
        resume_id = self._resume(self.user.id)

        delivery = add_delivery(self.session, order.id, resume_id)
        self.assertEqual(delivery.kind, "resume")

        _, quotas = order_history(self.session, self.user.id)
        granted, used = quotas["resume"]
        self.assertEqual((granted, used), (1, 1))

        with self.assertRaises(DeliveryNotAllowedError):
            add_delivery(self.session, order.id, resume_id)

    def test_a_delivery_cannot_point_at_another_users_work(self) -> None:
        order, _ = self._order()
        mark_paid(self.session, order.id)

        other_user = create_user(
            self.session, UserCreate(email="other@example.com", display_name="Other")
        )
        someone_elses_resume = self._resume(other_user.id)

        with self.assertRaises(DeliveryNotAllowedError):
            add_delivery(self.session, order.id, someone_elses_resume)


if __name__ == "__main__":
    unittest.main()
