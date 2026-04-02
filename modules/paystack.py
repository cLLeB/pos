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


def _is_temporary_verify_message(message: str) -> bool:
    """Return True when verify response suggests eventual consistency / in-flight state."""
    text = (message or "").strip().lower()
    if not text:
        return False

    pending_markers = (
        "reference",
        "not found",
        "could not be found",
        "still processing",
        "processing",
        "pending",
        "try again",
        "timeout",
        "temporar",
    )
    return any(marker in text for marker in pending_markers)


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
    details = charge_mobile_money_detailed(
        amount=amount,
        phone=phone,
        provider_name=provider_name,
        email=email,
        reference=reference,
        currency=currency,
        metadata=metadata,
    )
    return details["ok"], details["message"]


def charge_mobile_money_detailed(
    *,
    amount: float,
    phone: str,
    provider_name: str,
    email: str,
    reference: str,
    currency: str = "GHS",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Trigger a direct MoMo charge attempt and return normalized details.

    Returns:
      {
        "ok": bool,
        "message": str,
        "status": str,               # raw lower-case paystack status
        "challenge_required": bool,
        "challenge_type": str,       # otp|phone|url|none
        "raw": dict,
      }
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
        return {
            "ok": False,
            "message": result.get("message", "Charge initialization failed."),
            "status": "",
            "challenge_required": False,
            "challenge_type": "none",
            "raw": result,
        }

    data = result.get("data", {})
    status = (data.get("status") or "").lower()
    display_text = data.get("display_text") or result.get("message") or "Request sent."

    challenge_type = "none"
    if status == "send_otp":
        challenge_type = "otp"
    elif status == "send_phone":
        challenge_type = "phone"
    elif status == "open_url":
        challenge_type = "url"

    accepted_statuses = {"pending", "send_otp", "send_phone", "open_url", "pay_offline", "success"}
    if status in accepted_statuses:
        return {
            "ok": True,
            "message": display_text,
            "status": status,
            "challenge_required": challenge_type in {"otp", "phone", "url"},
            "challenge_type": challenge_type,
            "raw": data,
        }

    return {
        "ok": False,
        "message": data.get("gateway_response") or result.get("message", "Charge was not accepted."),
        "status": status,
        "challenge_required": False,
        "challenge_type": "none",
        "raw": data,
    }


def submit_charge_challenge(
    *,
    reference: str,
    challenge_value: str,
    challenge_type: str = "otp",
) -> tuple[bool, str, dict[str, Any]]:
    """
    Submit a follow-up challenge code for a charge.

    Supported challenge types:
      - otp   -> POST /charge/submit_otp with {otp, reference}
      - phone -> POST /charge/submit_phone with {phone, reference}
    """
    ctype = (challenge_type or "otp").strip().lower()
    if ctype not in {"otp", "phone"}:
        return False, f"Unsupported challenge type: {challenge_type}", {}

    path = "/charge/submit_otp" if ctype == "otp" else "/charge/submit_phone"
    payload_key = "otp" if ctype == "otp" else "phone"
    payload = {
        payload_key: challenge_value,
        "reference": reference,
    }

    result = _request_json("POST", path, payload)
    if not result.get("status"):
        return False, result.get("message", "Challenge submission failed."), result

    data = result.get("data", {})
    status = (data.get("status") or "").lower()
    message = data.get("display_text") or result.get("message") or "Challenge submitted."
    ok = status in {"pending", "success", "send_otp", "send_phone", "open_url", "pay_offline"}
    return ok, message, data


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
        msg = result.get("message", "Verification failed.")
        if _is_temporary_verify_message(msg):
            return {
                "success": False,
                "status": "PENDING",
                "reason": msg,
                "raw": result,
            }
        return {
            "success": False,
            "status": "FAILED",
            "reason": msg,
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

    if paystack_status in {
        "pending",
        "ongoing",
        "processing",
        "queued",
        "send_otp",
        "send_phone",
        "open_url",
        "pay_offline",
    }:
        return {
            "success": False,
            "status": "PENDING",
            "reason": data.get("display_text")
            or data.get("gateway_response")
            or "Pending customer confirmation.",
            "raw": data,
        }

    return {
        "success": False,
        "status": "PENDING",
        "reason": data.get("display_text")
        or data.get("gateway_response")
        or "Pending customer confirmation.",
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
