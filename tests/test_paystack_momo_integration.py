"""
Paystack + MoMo integration tests (offline, deterministic).
"""

import hashlib
import hmac
import json

from tests.test_base import PosTestCase
from modules import paystack
from modules.momo import (
    create_momo_transaction,
    get_momo_transaction,
    get_momo_by_reference,
    handle_paystack_webhook,
    handle_payment_callback,
)


class TestPaystackMomoWebhookFlow(PosTestCase):
    def test_paystack_webhook_success_updates_transaction(self):
        txn_id = create_momo_transaction(
            sale_id="",
            phone="+233200000001",
            amount=10.0,
            provider="MTN MoMo",
        )
        txn = get_momo_transaction(txn_id)
        reference = txn["reference"]

        payload = {
            "event": "charge.success",
            "data": {"reference": reference, "gateway_response": "Approved"},
        }
        raw_body = json.dumps(payload).encode("utf-8")

        original_key = paystack.SECRET_KEY
        try:
            paystack.SECRET_KEY = "test_secret"
            signature = hmac.new(
                paystack.SECRET_KEY.encode("utf-8"),
                raw_body,
                hashlib.sha512,
            ).hexdigest()

            ok, msg = handle_paystack_webhook(raw_body, signature)
            self.assertTrue(ok, msg)

            updated = get_momo_transaction(txn_id)
            self.assertEqual(updated["status"], "SUCCESS")
        finally:
            paystack.SECRET_KEY = original_key

    def test_terminal_status_is_idempotent(self):
        txn_id = create_momo_transaction(
            sale_id="",
            phone="+233200000002",
            amount=15.0,
            provider="MTN MoMo",
        )
        txn = get_momo_transaction(txn_id)
        reference = txn["reference"]

        ok_1 = handle_payment_callback(reference, "SUCCESS")
        ok_2 = handle_payment_callback(reference, "FAILED", "Late duplicate")

        self.assertTrue(ok_1)
        self.assertTrue(ok_2)

        updated = get_momo_transaction(txn_id)
        self.assertEqual(updated["status"], "SUCCESS")

    def test_webhook_signature_invalid_rejected(self):
        txn_id = create_momo_transaction(
            sale_id="",
            phone="+233200000003",
            amount=20.0,
            provider="Telecel Cash",
        )
        reference = get_momo_transaction(txn_id)["reference"]
        raw_body = json.dumps({"event": "charge.success", "data": {"reference": reference}}).encode("utf-8")

        original_key = paystack.SECRET_KEY
        try:
            paystack.SECRET_KEY = "test_secret"
            ok, msg = handle_paystack_webhook(raw_body, "bad_signature")
            self.assertFalse(ok)
            self.assertIn("Invalid", msg)
        finally:
            paystack.SECRET_KEY = original_key

    def test_webhook_event_mapping(self):
        ref, status, _ = paystack.webhook_event_to_status(
            {"event": "charge.success", "data": {"reference": "ABC"}}
        )
        self.assertEqual(ref, "ABC")
        self.assertEqual(status, "SUCCESS")

        ref2, status2, _ = paystack.webhook_event_to_status(
            {"event": "charge.failed", "data": {"reference": "XYZ"}}
        )
        self.assertEqual(ref2, "XYZ")
        self.assertEqual(status2, "FAILED")


class TestPaymentMetadataColumns(PosTestCase):
    def test_payment_record_supports_gateway_metadata(self):
        from modules.sales import create_sale
        from modules.auth import login, logout, get_current_user
        from modules.payments import record_payment, get_payment_by_sale

        login("cashier1", "cashier123")
        user = get_current_user()
        try:
            cart = [{"product_id": 1, "name": "Coke", "price": 1.5, "quantity": 1}]
            ok, msg, sale_id = create_sale(user["user_id"], cart, "Mobile Money (MTN MoMo)")
            self.assertTrue(ok, msg)

            ok_p, msg_p = record_payment(
                sale_id=sale_id,
                amount_paid=1.74,
                payment_type="Mobile Money (MTN MoMo)",
                reference="REF-123",
                status="COMPLETED",
                provider="paystack",
            )
            self.assertTrue(ok_p, msg_p)

            row = get_payment_by_sale(sale_id)
            self.assertEqual(row["payment_status"], "COMPLETED")
            self.assertEqual(row["provider"], "paystack")
            self.assertEqual(row["external_reference"], "REF-123")
        finally:
            logout()
