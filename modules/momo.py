"""
Mobile Money Payment Module
============================
Provider abstraction + transaction state machine.

Current provider mode:
    - mock      (default, no credentials needed — works offline)
    - paystack  (set MOMO_PROVIDER_MODE=paystack + PAYSTACK_SECRET_KEY)

Ready slots:   MTNMoMoProvider   (fill in when you receive API access)
                             TelecelProvider   (same pattern)
                             ATMoneyProvider   (same pattern)

Payment lifecycle (desktop POS):
  PENDING  → SUCCESS   customer approved on phone
  PENDING  → FAILED    customer declined / insufficient funds
  PENDING  → EXPIRED   no response within timeout window

How to switch from mock to real MTN:
  1. Fill in MTNMoMoProvider.request_to_pay() with the actual API call
  2. Change get_active_provider() to return MTNMoMoProvider()
  3. Nothing else in the codebase changes

Webhook note:
    When you run a web backend (Flask/FastAPI/http.server), your webhook route
    can call handle_paystack_webhook(raw_body, signature). The handler validates
    signature, normalizes status, and calls handle_payment_callback(...).
"""

import uuid
import time
import threading
import json
from abc import ABC, abstractmethod
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db_setup import get_connection
from utils.helpers import current_timestamp
from modules import paystack


# ── DB helpers ────────────────────────────────────────────────────────────────

def create_momo_transaction(sale_id: str, phone: str, amount: float,
                            provider: str) -> str:
    """
    Insert a PENDING MoMo transaction record.
    Returns the generated txn_id.
    """
    txn_id    = "MOMO-" + str(uuid.uuid4()).upper()[:8]
    reference = "REF-"  + str(uuid.uuid4()).upper()[:10]
    now       = current_timestamp()

    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO MoMo_Transactions
                   (txn_id, sale_id, phone, amount, provider, reference,
                    status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                txn_id,
                sale_id if sale_id else None,
                phone,
                amount,
                provider,
                reference,
                "PENDING",
                now,
                now,
            )
        )
        conn.commit()
    finally:
        conn.close()
    return txn_id


def update_momo_status(txn_id: str, status: str,
                       failure_reason: str = "") -> None:
    """Update a transaction's status (SUCCESS / FAILED / EXPIRED)."""
    conn = get_connection()
    conn.execute(
        """UPDATE MoMo_Transactions
           SET status=?, failure_reason=?, updated_at=?
           WHERE txn_id=?""",
        (status, failure_reason, current_timestamp(), txn_id)
    )
    conn.commit()
    conn.close()


def link_momo_sale(txn_id: str, sale_id: str) -> None:
    """Attach a finalized sale_id to an existing MoMo transaction."""
    conn = get_connection()
    conn.execute(
        """UPDATE MoMo_Transactions
           SET sale_id=?, updated_at=?
           WHERE txn_id=?""",
        (sale_id, current_timestamp(), txn_id)
    )
    conn.commit()
    conn.close()


def get_momo_transaction(txn_id: str) -> dict | None:
    """Return the full transaction record or None."""
    conn = get_connection()
    row  = conn.execute(
        "SELECT * FROM MoMo_Transactions WHERE txn_id=?", (txn_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_momo_by_reference(reference: str) -> dict | None:
    """Look up a transaction by its external reference code."""
    conn = get_connection()
    row  = conn.execute(
        "SELECT * FROM MoMo_Transactions WHERE reference=?", (reference,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ── Webhook / callback entry point ────────────────────────────────────────────

def handle_payment_callback(reference: str, status: str,
                             reason: str = "") -> bool:
    """
    Called by:
      - the mock provider's background thread (now)
      - your future Flask/FastAPI webhook route (later)

    Updates the transaction and fires any registered callbacks.
    Returns True if the reference was found, False otherwise.
    """
    txn = get_momo_by_reference(reference)
    if not txn:
        return False

    normalized = status.upper()
    if normalized not in ("SUCCESS", "FAILED", "EXPIRED"):
        normalized = "FAILED"

    # Idempotency and terminal-state protection.
    current_status = (txn.get("status") or "").upper()
    if current_status in ("SUCCESS", "FAILED", "EXPIRED"):
        return True

    update_momo_status(txn["txn_id"], normalized, reason)
    _clear_pending_challenge(txn["txn_id"])

    # Notify any registered listener for this txn_id
    _fire_callback(txn["txn_id"], normalized, reason)
    return True


def handle_paystack_webhook(raw_body: bytes, signature: str) -> tuple[bool, str]:
    """
    Validate and process a Paystack webhook payload.

    Returns (processed, message).
    """
    if not paystack.verify_webhook_signature(raw_body, signature):
        return False, "Invalid Paystack webhook signature."

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        return False, "Invalid JSON payload."

    reference, status, reason = paystack.webhook_event_to_status(payload)
    if not reference:
        return False, "No transaction reference in webhook payload."

    if status == "PENDING":
        return True, "Ignored non-terminal webhook event."

    ok = handle_payment_callback(reference, status, reason)
    if not ok:
        return False, "Reference not found in local transaction table."
    return True, "Webhook processed successfully."


# ── In-process callback registry (desktop polling) ───────────────────────────
# Maps txn_id → callable(status, reason) so the UI can react immediately.

_callbacks: dict[str, callable] = {}
_pending_challenges_by_reference: dict[str, dict] = {}
_pending_challenges_by_txn: dict[str, dict] = {}


def register_callback(txn_id: str, fn) -> None:
    _callbacks[txn_id] = fn


def unregister_callback(txn_id: str) -> None:
    _callbacks.pop(txn_id, None)


def _fire_callback(txn_id: str, status: str, reason: str) -> None:
    fn = _callbacks.pop(txn_id, None)
    if fn:
        fn(status, reason)


def _stage_challenge_for_reference(reference: str, challenge: dict) -> None:
    _pending_challenges_by_reference[reference] = dict(challenge)


def _assign_staged_challenge(txn_id: str, reference: str) -> None:
    challenge = _pending_challenges_by_reference.pop(reference, None)
    if challenge:
        _pending_challenges_by_txn[txn_id] = challenge


def _clear_pending_challenge(txn_id: str) -> None:
    _pending_challenges_by_txn.pop(txn_id, None)


def get_pending_momo_challenge(txn_id: str) -> dict | None:
    """Return pending challenge metadata for a transaction (if any)."""
    challenge = _pending_challenges_by_txn.get(txn_id)
    return dict(challenge) if challenge else None


# ── Provider abstraction ──────────────────────────────────────────────────────

class MoMoProvider(ABC):
    """Abstract base — all providers implement this interface."""

    @abstractmethod
    def request_to_pay(self, phone: str, amount: float,
                       reference: str, currency: str = "GHS") -> tuple[bool, str]:
        """
        Send a payment prompt to the customer's phone.
        Returns (initiated: bool, error_message: str).
        Payment result arrives later via handle_payment_callback().
        """

    @abstractmethod
    def check_status(self, reference: str) -> str:
        """
        Poll for payment status.
        Returns one of: 'PENDING', 'SUCCESS', 'FAILED', 'EXPIRED'
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""


# ── Mock provider (use this now, replace later) ───────────────────────────────

class MockMoMoProvider(MoMoProvider):
    """
    Simulates a MoMo provider for offline development and testing.
    Automatically resolves payments as SUCCESS after a short delay.
    Set MOCK_FAIL = True to simulate failures.
    Set MOCK_DELAY = N to control seconds before callback fires.
    """

    MOCK_DELAY   = 3      # seconds to simulate network round-trip
    MOCK_FAIL    = False  # set True to test failure paths

    @property
    def name(self) -> str:
        return "Mock MoMo (Test Mode)"

    def request_to_pay(self, phone: str, amount: float,
                       reference: str, currency: str = "GHS") -> tuple[bool, str]:
        """Immediately returns True; fires success/failure after MOCK_DELAY."""
        def _delayed_callback():
            time.sleep(self.MOCK_DELAY)
            if self.MOCK_FAIL:
                handle_payment_callback(reference, "FAILED",
                                        "Simulated failure (MOCK_FAIL=True)")
            else:
                handle_payment_callback(reference, "SUCCESS")

        t = threading.Thread(target=_delayed_callback, daemon=True)
        t.start()
        return True, ""

    def check_status(self, reference: str) -> str:
        txn = get_momo_by_reference(reference)
        return txn["status"] if txn else "FAILED"


class PaystackMoMoProvider(MoMoProvider):
    """
    Paystack-backed MoMo collections provider (Ghana).

    Uses /charge for initiation and /transaction/verify polling for final state.
    Real-time updates are completed by calling handle_payment_callback().
    """

    POLL_INTERVAL = 4    # seconds
    TIMEOUT       = 150  # seconds
    DEFAULT_EMAIL = os.getenv("PAYSTACK_CUSTOMER_EMAIL", "customer@pos.local")

    @property
    def name(self) -> str:
        return "Paystack MoMo"

    def request_to_pay(self, phone: str, amount: float,
                       reference: str, currency: str = "GHS") -> tuple[bool, str]:
        if not paystack.is_configured():
            return False, "PAYSTACK_SECRET_KEY is not configured."

        txn = get_momo_by_reference(reference)
        metadata = {
            "source": "POS_System",
            "local_txn_id": txn["txn_id"] if txn else "",
            "local_sale_id": txn["sale_id"] if txn else "",
            "momo_provider": txn["provider"] if txn else "",
        }

        try:
            details = paystack.charge_mobile_money_detailed(
                amount=amount,
                phone=phone,
                provider_name=(txn["provider"] if txn else "MTN MoMo"),
                email=self.DEFAULT_EMAIL,
                reference=reference,
                currency=currency,
                metadata=metadata,
            )
        except Exception as e:
            return False, f"Paystack charge error: {e}"

        if not details.get("ok"):
            return False, details.get("message", "Charge initialization failed.")

        if details.get("challenge_required"):
            _stage_challenge_for_reference(
                reference,
                {
                    "challenge_required": True,
                    "challenge_type": details.get("challenge_type", "otp"),
                    "message": details.get("message", "Additional confirmation required."),
                    "reference": reference,
                    "provider": txn["provider"] if txn else "",
                },
            )

        threading.Thread(
            target=self._poll_until_final,
            args=(reference,),
            daemon=True,
        ).start()
        return True, details.get("message", "Request sent.")

    def check_status(self, reference: str) -> str:
        try:
            result = paystack.verify_transaction(reference)
            return result["status"]
        except Exception:
            return "PENDING"

    def _poll_until_final(self, reference: str) -> None:
        elapsed = 0
        while elapsed < self.TIMEOUT:
            time.sleep(self.POLL_INTERVAL)
            elapsed += self.POLL_INTERVAL
            try:
                result = paystack.verify_transaction(reference)
            except Exception:
                # Keep waiting for webhook or next poll rather than failing hard.
                continue

            status = result.get("status", "PENDING")
            reason = result.get("reason", "")
            if status in ("SUCCESS", "FAILED"):
                handle_payment_callback(reference, status, reason)
                return
        handle_payment_callback(reference, "EXPIRED", "Paystack confirmation timed out.")


# ── MTN MoMo provider stub (fill in when you get API access) ─────────────────

class MTNMoMoProvider(MoMoProvider):
    """
    Real MTN MoMo Collections API.

    To activate:
      1. Get your Subscription-Key and API credentials from
         developer.mtn.com/products/collections
      2. Set environment variables:
           MOMO_API_KEY     = your subscription key
           MOMO_USER_ID     = your API user ID
           MOMO_USER_SECRET = your API user secret
           MOMO_BASE_URL    = https://sandbox.momodeveloper.mtn.com  (sandbox)
                              https://proxy.momodeveloper.mtn.com     (prod)
           MOMO_CALLBACK_URL = https://yourserver.com/momo/webhook
      3. Change get_active_provider() below to return MTNMoMoProvider()

    MTN API Reference:
      POST /collection/v1_0/requesttopay
      GET  /collection/v1_0/requesttopay/{referenceId}
    """

    BASE_URL     = os.getenv("MOMO_BASE_URL", "https://sandbox.momodeveloper.mtn.com")
    API_KEY      = os.getenv("MOMO_API_KEY", "")
    USER_ID      = os.getenv("MOMO_USER_ID", "")
    USER_SECRET  = os.getenv("MOMO_USER_SECRET", "")
    CALLBACK_URL = os.getenv("MOMO_CALLBACK_URL", "")
    POLL_INTERVAL = 5    # seconds between status polls
    TIMEOUT       = 120  # seconds before marking EXPIRED

    @property
    def name(self) -> str:
        return "MTN MoMo"

    def _get_access_token(self) -> str:
        """
        Exchange credentials for an OAuth2 access token.
        TO DO: implement when API credentials are available.
        """
        # import requests, base64
        # credentials = base64.b64encode(
        #     f"{self.USER_ID}:{self.USER_SECRET}".encode()
        # ).decode()
        # resp = requests.post(
        #     f"{self.BASE_URL}/collection/token/",
        #     headers={
        #         "Authorization": f"Basic {credentials}",
        #         "Ocp-Apim-Subscription-Key": self.API_KEY,
        #     }
        # )
        # resp.raise_for_status()
        # return resp.json()["access_token"]
        raise NotImplementedError("MTN MoMo credentials not yet configured.")

    def request_to_pay(self, phone: str, amount: float,
                       reference: str, currency: str = "GHS") -> tuple[bool, str]:
        """
        POST /collection/v1_0/requesttopay
        TO DO: implement when API credentials are available.
        """
        # token = self._get_access_token()
        # payload = {
        #     "amount":    str(amount),
        #     "currency":  currency,
        #     "externalId": reference,
        #     "payer": {
        #         "partyIdType": "MSISDN",
        #         "partyId": phone.replace("+", "").replace(" ", ""),
        #     },
        #     "payerMessage": "Payment at POS",
        #     "payeeNote":    "POS Transaction",
        # }
        # if self.CALLBACK_URL:
        #     payload["callbackUrl"] = self.CALLBACK_URL
        #
        # resp = requests.post(
        #     f"{self.BASE_URL}/collection/v1_0/requesttopay",
        #     json=payload,
        #     headers={
        #         "Authorization":             f"Bearer {token}",
        #         "X-Reference-Id":            reference,
        #         "X-Target-Environment":      "sandbox",  # change to "mtncongo" etc for prod
        #         "Ocp-Apim-Subscription-Key": self.API_KEY,
        #         "Content-Type":              "application/json",
        #     }
        # )
        # if resp.status_code == 202:
        #     # Start polling in background if no webhook configured
        #     if not self.CALLBACK_URL:
        #         threading.Thread(
        #             target=self._poll_until_final,
        #             args=(reference,), daemon=True
        #         ).start()
        #     return True, ""
        # return False, f"MTN API error: {resp.status_code} {resp.text}"
        raise NotImplementedError("MTN MoMo credentials not yet configured.")

    def check_status(self, reference: str) -> str:
        """
        GET /collection/v1_0/requesttopay/{referenceId}
        TO DO: implement when API credentials are available.
        """
        # token = self._get_access_token()
        # resp = requests.get(
        #     f"{self.BASE_URL}/collection/v1_0/requesttopay/{reference}",
        #     headers={
        #         "Authorization":             f"Bearer {token}",
        #         "X-Target-Environment":      "sandbox",
        #         "Ocp-Apim-Subscription-Key": self.API_KEY,
        #     }
        # )
        # if resp.status_code == 200:
        #     mtn_status = resp.json().get("status", "FAILED")
        #     # MTN returns: SUCCESSFUL / FAILED / PENDING
        #     mapping = {"SUCCESSFUL": "SUCCESS", "FAILED": "FAILED", "PENDING": "PENDING"}
        #     return mapping.get(mtn_status, "FAILED")
        # return "FAILED"
        raise NotImplementedError("MTN MoMo credentials not yet configured.")

    def _poll_until_final(self, reference: str) -> None:
        """Background polling when no callback URL is registered."""
        elapsed = 0
        while elapsed < self.TIMEOUT:
            time.sleep(self.POLL_INTERVAL)
            elapsed += self.POLL_INTERVAL
            status = self.check_status(reference)
            if status in ("SUCCESS", "FAILED"):
                handle_payment_callback(reference, status)
                return
        handle_payment_callback(reference, "EXPIRED",
                                "Customer did not respond within timeout.")


# ── Telecel Cash stub (same pattern as MTN) ───────────────────────────────────

class TelecelProvider(MoMoProvider):
    """
    Telecel Cash (formerly Vodafone Cash) — stub ready for API integration.
    Telecel uses the Hubtel Payments API for merchant integrations in Ghana.
    API docs: developers.hubtel.com
    """

    @property
    def name(self) -> str:
        return "Telecel Cash"

    def request_to_pay(self, phone: str, amount: float,
                       reference: str, currency: str = "GHS") -> tuple[bool, str]:
        raise NotImplementedError("Telecel Cash API not yet configured.")

    def check_status(self, reference: str) -> str:
        raise NotImplementedError("Telecel Cash API not yet configured.")


# ── AT Money stub ─────────────────────────────────────────────────────────────

class ATMoneyProvider(MoMoProvider):
    """
    AT Money (AirtelTigo) — stub ready for API integration.
    AirtelTigo uses the Hubtel Payments API for Ghana merchant integrations.
    API docs: developers.hubtel.com
    """

    @property
    def name(self) -> str:
        return "AT Money (AirtelTigo)"

    def request_to_pay(self, phone: str, amount: float,
                       reference: str, currency: str = "GHS") -> tuple[bool, str]:
        raise NotImplementedError("AT Money API not yet configured.")

    def check_status(self, reference: str) -> str:
        raise NotImplementedError("AT Money API not yet configured.")


# ── Provider registry ─────────────────────────────────────────────────────────

_MOMO_MODE = os.getenv("MOMO_PROVIDER_MODE", "mock").strip().lower()
_ACTIVE_REAL_PROVIDER: MoMoProvider
if _MOMO_MODE == "paystack":
    _ACTIVE_REAL_PROVIDER = PaystackMoMoProvider()
else:
    _ACTIVE_REAL_PROVIDER = MockMoMoProvider()

_PROVIDER_MAP: dict[str, MoMoProvider] = {
    "MTN MoMo":              _ACTIVE_REAL_PROVIDER,
    "Telecel Cash":          _ACTIVE_REAL_PROVIDER,
    "AT Money (AirtelTigo)": _ACTIVE_REAL_PROVIDER,
    "Other":                 MockMoMoProvider(),
}


def get_provider(provider_name: str) -> MoMoProvider:
    """Return the active provider for the given name. Falls back to mock."""
    return _PROVIDER_MAP.get(provider_name, MockMoMoProvider())


# ── High-level payment orchestrator ──────────────────────────────────────────

def initiate_momo_payment(
    sale_id: str,
    phone: str,
    amount: float,
    provider_name: str,
    on_result,          # callable(txn_id, status, reason)
    currency: str = "GHS",
) -> tuple[bool, str, str]:
    """
    One-call entry point used by the UI.

    1. Creates a PENDING DB record.
    2. Registers the on_result callback.
    3. Calls the provider's request_to_pay().
    4. Returns (initiated, provider_message_or_error, txn_id).

    The on_result callback fires automatically when the payment resolves
    (either from the mock thread or a real provider callback).
    """
    provider = get_provider(provider_name)

    txn_id = create_momo_transaction(sale_id, phone, amount, provider_name)
    txn    = get_momo_transaction(txn_id)
    ref    = txn["reference"]

    # Wrap the callback to include txn_id
    def _on_resolved(status: str, reason: str):
        on_result(txn_id, status, reason)

    register_callback(txn_id, _on_resolved)

    ok, provider_msg = provider.request_to_pay(phone, amount, ref, currency)
    if not ok:
        unregister_callback(txn_id)
        update_momo_status(txn_id, "FAILED", provider_msg)
        return False, provider_msg, txn_id

    _assign_staged_challenge(txn_id, ref)

    return True, provider_msg, txn_id


def submit_momo_challenge_code(txn_id: str, code: str) -> tuple[bool, str, str]:
    """
    Submit pending challenge input (e.g. Telecel voucher/OTP) for a transaction.

    Returns (ok, status, message).
    """
    txn = get_momo_transaction(txn_id)
    if not txn:
        return False, "UNKNOWN", "Transaction not found."

    normalized_code = "".join(str(code or "").split())
    if not normalized_code:
        return False, "UNKNOWN", "OTP/voucher code is required."

    current_status = (txn.get("status") or "").upper()
    if current_status in ("SUCCESS", "FAILED", "EXPIRED"):
        return True, current_status, "Transaction already finalized."

    challenge = get_pending_momo_challenge(txn_id) or {}

    reference = challenge.get("reference") or txn.get("reference") or ""
    if not reference:
        return False, "UNKNOWN", "Transaction reference is missing."
    challenge_type = (challenge.get("challenge_type") or "otp").lower()
    if challenge_type not in {"otp", "phone"}:
        challenge_type = "otp"

    try:
        ok_submit, submit_msg, _ = paystack.submit_charge_challenge(
            reference=reference,
            challenge_value=normalized_code,
            challenge_type=challenge_type,
        )
    except Exception as e:
        return False, "UNKNOWN", f"Challenge submission failed: {e}"

    if not ok_submit:
        return False, "FAILED", submit_msg

    try:
        verification = paystack.verify_transaction(reference)
    except Exception:
        verification = {"status": "PENDING", "reason": submit_msg}

    status = (verification.get("status") or "PENDING").upper()
    reason = verification.get("reason") or submit_msg
    if status in ("SUCCESS", "FAILED", "EXPIRED"):
        handle_payment_callback(reference, status, reason)
        return True, status, reason

    # Keep checking in background so cashier doesn't depend only on manual retry.
    threading.Thread(
        target=_poll_after_challenge_submit,
        args=(reference,),
        daemon=True,
    ).start()

    return True, "PENDING", reason


def _poll_after_challenge_submit(reference: str, timeout: int = 90, interval: int = 4) -> None:
    """Background verification after challenge submission until terminal state."""
    elapsed = 0
    while elapsed < timeout:
        time.sleep(interval)
        elapsed += interval
        try:
            result = paystack.verify_transaction(reference)
        except Exception:
            continue

        status = (result.get("status") or "PENDING").upper()
        reason = result.get("reason") or ""
        if status in ("SUCCESS", "FAILED", "EXPIRED"):
            handle_payment_callback(reference, status, reason)
            return


def retry_verify_momo_transaction(txn_id: str) -> tuple[bool, str, str]:
    """
    Manually trigger a verification check for an existing MoMo transaction.

    Returns:
      (ok, status, message)
      - ok=False means lookup/provider call failed.
      - status is one of PENDING/SUCCESS/FAILED/EXPIRED (or UNKNOWN on hard error).
    """
    txn = get_momo_transaction(txn_id)
    if not txn:
        return False, "UNKNOWN", "Transaction not found."

    current_status = (txn.get("status") or "").upper()
    if current_status in ("SUCCESS", "FAILED", "EXPIRED"):
        return True, current_status, "Transaction already finalized."

    provider_name = txn.get("provider") or "MTN MoMo"
    provider = get_provider(provider_name)
    reference = txn.get("reference") or ""

    try:
        if isinstance(provider, PaystackMoMoProvider):
            result = paystack.verify_transaction(reference)
            status = (result.get("status") or "PENDING").upper()
            reason = result.get("reason") or ""
        else:
            status = (provider.check_status(reference) or "PENDING").upper()
            reason = ""
    except Exception as e:
        return False, "UNKNOWN", f"Verification check failed: {e}"

    if status in ("SUCCESS", "FAILED", "EXPIRED"):
        handle_payment_callback(reference, status, reason)
        return True, status, reason

    return True, "PENDING", reason or "Still awaiting customer confirmation."
