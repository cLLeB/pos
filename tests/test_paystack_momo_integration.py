"""
Paystack + MoMo integration tests (offline, deterministic).
"""

import hashlib
import hmac
import json
import modules.momo as momo_mod

from tests.test_base import PosTestCase
from modules import paystack
from modules.momo import (
    create_momo_transaction,
    get_momo_transaction,
    get_momo_by_reference,
    handle_paystack_webhook,
    handle_payment_callback,
    retry_verify_momo_transaction,
    submit_momo_challenge_code,
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


class TestPaystackVerifyNormalization(PosTestCase):
    def test_verify_reference_not_found_is_pending(self):
        original_request = paystack._request_json
        try:
            paystack._request_json = lambda method, path, payload=None: {
                "status": False,
                "message": "Transaction reference could not be found",
            }
            result = paystack.verify_transaction("REF-TEST")
            self.assertEqual(result["status"], "PENDING")
        finally:
            paystack._request_json = original_request


class TestManualRetryVerification(PosTestCase):
    def test_retry_verification_pending_keeps_transaction_open(self):
        txn_id = create_momo_transaction(
            sale_id="",
            phone="+233200000004",
            amount=12.0,
            provider="MTN MoMo",
        )

        original_verify = paystack.verify_transaction
        try:
            paystack.verify_transaction = lambda reference: {
                "success": False,
                "status": "PENDING",
                "reason": "Enter OTP on customer phone",
                "raw": {},
            }
            ok, status, msg = retry_verify_momo_transaction(txn_id)
            self.assertTrue(ok)
            self.assertEqual(status, "PENDING")
            self.assertIn("OTP", msg)

            txn = get_momo_transaction(txn_id)
            self.assertEqual(txn["status"], "PENDING")
        finally:
            paystack.verify_transaction = original_verify

    def test_retry_verification_success_finalizes_transaction(self):
        txn_id = create_momo_transaction(
            sale_id="",
            phone="+233200000005",
            amount=8.5,
            provider="MTN MoMo",
        )

        original_verify = paystack.verify_transaction
        try:
            paystack.verify_transaction = lambda reference: {
                "success": True,
                "status": "SUCCESS",
                "reason": "Approved",
                "raw": {},
            }
            ok, status, _ = retry_verify_momo_transaction(txn_id)
            self.assertTrue(ok)
            self.assertEqual(status, "SUCCESS")

            txn = get_momo_transaction(txn_id)
            self.assertEqual(txn["status"], "SUCCESS")
        finally:
            paystack.verify_transaction = original_verify

    def test_verify_send_otp_status_is_pending(self):
        original_request = paystack._request_json
        try:
            paystack._request_json = lambda method, path, payload=None: {
                "status": True,
                "data": {
                    "status": "send_otp",
                    "display_text": "Enter the OTP sent to your phone",
                },
            }
            result = paystack.verify_transaction("REF-OTP")
            self.assertEqual(result["status"], "PENDING")
            self.assertIn("OTP", result["reason"])
        finally:
            paystack._request_json = original_request


class TestTelecelChallengeSubmission(PosTestCase):
    def test_charge_detailed_marks_send_otp_as_challenge_required(self):
        original_request = paystack._request_json
        try:
            paystack._request_json = lambda method, path, payload=None: {
                "status": True,
                "data": {
                    "status": "send_otp",
                    "display_text": "Enter voucher code",
                },
                "message": "Charge initialized",
            }
            details = paystack.charge_mobile_money_detailed(
                amount=1.39,
                phone="0537270382",
                provider_name="Telecel Cash",
                email="tester@example.com",
                reference="REF-OTP-1",
            )
            self.assertTrue(details["ok"])
            self.assertTrue(details["challenge_required"])
            self.assertEqual(details["challenge_type"], "otp")
        finally:
            paystack._request_json = original_request

    def test_submit_momo_challenge_code_success_finalizes(self):
        txn_id = create_momo_transaction(
            sale_id="",
            phone="+233200000006",
            amount=5.0,
            provider="Telecel Cash",
        )
        txn = get_momo_transaction(txn_id)
        momo_mod._pending_challenges_by_txn[txn_id] = {
            "challenge_required": True,
            "challenge_type": "otp",
            "reference": txn["reference"],
            "provider": "Telecel Cash",
        }

        original_submit = paystack.submit_charge_challenge
        original_verify = paystack.verify_transaction
        try:
            paystack.submit_charge_challenge = lambda **kwargs: (True, "Code accepted", {})
            paystack.verify_transaction = lambda reference: {
                "status": "SUCCESS",
                "reason": "Approved",
            }

            ok, status, _ = submit_momo_challenge_code(txn_id, "123456")
            self.assertTrue(ok)
            self.assertEqual(status, "SUCCESS")

            updated = get_momo_transaction(txn_id)
            self.assertEqual(updated["status"], "SUCCESS")
        finally:
            paystack.submit_charge_challenge = original_submit
            paystack.verify_transaction = original_verify

    def test_submit_momo_challenge_code_without_pending_context_fails(self):
        txn_id = create_momo_transaction(
            sale_id="",
            phone="+233200000007",
            amount=6.0,
            provider="Telecel Cash",
        )

        ok, status, msg = submit_momo_challenge_code(txn_id, "123456")
        self.assertFalse(ok)
        self.assertEqual(status, "UNKNOWN")
        self.assertIn("No pending challenge", msg)
