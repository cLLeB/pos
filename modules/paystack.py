"""
Paystack integration helpers for real-time payment processing.

Scope
-----
- Mobile Money charge initialization (MTN / Telecel / AT)
- Transaction verification
- Webhook signature verification (X-Paystack-Signature)

Design notes
------------
- Uses only Python standard library (urllib/json/hmac/hashlib)
- Reads secrets from environment variables
- Returns plain dicts/tuples to keep call-sites simple
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_URL = os.getenv("PAYSTACK_BASE_URL", "https://api.paystack.co").rstrip("/")
# Backward-compatible module fallback used by legacy tests/mocks.
SECRET_KEY = (os.getenv("PAYSTACK_SECRET_KEY", "") or "").strip()


def _secret_key() -> str:
    """Read Paystack secret key dynamically from environment."""
    return SECRET_KEY or (os.getenv("PAYSTACK_SECRET_KEY", "") or "").strip()

_PROVIDER_MAP = {
    "MTN MoMo": "mtn",
    "Telecel Cash": "vod",
    "AT Money (AirtelTigo)": "tgo",
}


class PaystackError(Exception):
    """Raised for recoverable Paystack integration errors."""


def is_configured() -> bool:
    """Return True when Paystack credentials are available."""
    return bool(_secret_key())


def provider_code(provider_name: str) -> str:
    """Map UI provider names to Paystack provider codes."""
    return _PROVIDER_MAP.get(provider_name, "mtn")


def generate_reference(prefix: str = "PSK") -> str:
    """Create a unique external reference for Paystack transactions."""
    return f"{prefix}-{str(uuid.uuid4()).upper()[:12]}"


def _headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    secret = _secret_key()
    if not is_configured():
        raise PaystackError("PAYSTACK_SECRET_KEY is not set.")

    base = {
        "Authorization": f"Bearer {secret}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": os.getenv(
            "PAYSTACK_USER_AGENT",
            "POS-System/1.0 (+https://github.com/cLLeB/pos)"
        ),
    }
    if extra:
        base.update(extra)
    return base


def _request_json(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    req = Request(
        url=f"{BASE_URL}{path}",
        method=method,
        headers=_headers(),
        data=data,
    )

    try:
        with urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        try:
            parsed = json.loads(body)
            msg = parsed.get("message") or body
        except Exception:
            msg = body or str(e)
        raise PaystackError(f"HTTP {e.code}: {msg}") from e
    except URLError as e:
        raise PaystackError(f"Network error: {e.reason}") from e


def charge_mobile_money(
    *,
    amount: float,
    phone: str,
    provider_name: str,
    email: str,
    reference: str,
    currency: str = "GHS",
    metadata: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """
    Trigger a direct MoMo charge attempt.

    Returns (ok, message). If ok=True, final status is obtained via verify_transaction
    polling or webhook callback.
    """
    payload = {
        "email": email,
        "amount": int(round(amount * 100)),  # pesewas
        "currency": currency,
        "reference": reference,
        "mobile_money": {
            "phone": phone,
            "provider": provider_code(provider_name),
        },
    }
    if metadata:
        payload["metadata"] = metadata

    result = _request_json("POST", "/charge", payload)
    if not result.get("status"):
        return False, result.get("message", "Charge initialization failed.")

    data = result.get("data", {})
    status = (data.get("status") or "").lower()

    # Accept statuses where Paystack has received the request and waits for customer action.
    if status in {"pending", "send_otp", "send_phone", "open_url", "pay_offline", "success"}:
        return True, data.get("display_text") or result.get("message") or "Request sent."

    return False, data.get("gateway_response") or result.get("message", "Charge was not accepted.")


def verify_transaction(reference: str) -> dict[str, Any]:
    """
    Verify a transaction reference and normalize outcome fields.

    Returns:
      {
        "success": bool,
        "status": "SUCCESS"|"FAILED"|"PENDING",
        "reason": str,
        "raw": dict,
      }
    """
    result = _request_json("GET", f"/transaction/verify/{reference}")
    if not result.get("status"):
        return {
            "success": False,
            "status": "FAILED",
            "reason": result.get("message", "Verification failed."),
            "raw": result,
        }

    data = result.get("data", {})
    paystack_status = (data.get("status") or "").lower()

    if paystack_status == "success":
        return {
            "success": True,
            "status": "SUCCESS",
            "reason": "",
            "raw": data,
        }
    if paystack_status in {"failed", "abandoned", "reversed"}:
        return {
            "success": False,
            "status": "FAILED",
            "reason": data.get("gateway_response", "Payment failed."),
            "raw": data,
        }

    return {
        "success": False,
        "status": "PENDING",
        "reason": data.get("gateway_response", "Pending customer confirmation."),
        "raw": data,
    }


def verify_webhook_signature(raw_body: bytes, provided_signature: str) -> bool:
    """Validate X-Paystack-Signature using HMAC-SHA512."""
    secret = _secret_key()
    if not is_configured() or not provided_signature:
        return False

    expected = hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha512,
    ).hexdigest()
    return hmac.compare_digest(expected, provided_signature.strip())


def webhook_event_to_status(event_payload: dict[str, Any]) -> tuple[str, str, str]:
    """
    Convert Paystack webhook payload to (reference, status, reason).

    status is one of SUCCESS / FAILED / PENDING.
    """
    event = (event_payload.get("event") or "").lower()
    data = event_payload.get("data") or {}
    reference = data.get("reference") or ""

    if event in {"charge.success", "charge.completed"}:
        return reference, "SUCCESS", ""
    if event in {"charge.failed", "charge.dispute.create"}:
        return reference, "FAILED", data.get("gateway_response", "Charge failed")

    # Unknown/non-terminal events should not force failure.
    return reference, "PENDING", data.get("gateway_response", "Awaiting final status")
