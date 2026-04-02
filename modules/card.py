"""
Card Payment Module — abstraction stub, paused for future development.
======================================================================
Current mode: MANUAL — cashier confirms after the physical terminal approves.
              Transaction is recorded but not verified via any API.

When a card terminal (Verifone / PAX / Ingenico) is procured:
  1. Subclass CardProvider and implement charge().
  2. Change get_active_provider() to return your new class.
  3. Nothing else in the codebase changes.

Ghana-relevant terminal SDKs to research when ready:
  - Paystack Terminal API  → developer.paystack.com/docs/terminal-api
  - Slydepay               → slydepay.com/developer
  - Hubtel POS             → developers.hubtel.com
  - Interswitch Passport   → developer.interswitch.com

PCI-DSS reminder:
  Card data (full PAN, CVV) must NEVER be stored or logged.
  Only last-4 digits and masked references are saved here.
"""

import uuid
from abc import ABC, abstractmethod
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db_setup import get_connection
from utils.helpers import current_timestamp


# ── DB helpers ────────────────────────────────────────────────────────────────

def record_card_transaction(sale_id: str, card_type: str, amount: float,
                            last_four: str = "",
                            terminal_ref: str = "",
                            status: str = "MANUAL") -> str:
    """
    Store a card transaction record.
    Status values:
      MANUAL   — cashier manually confirmed (current mode)
      APPROVED — terminal confirmed approval (future)
      DECLINED — terminal declined (future)
      ERROR    — terminal communication error (future)
    Returns the txn_id.
    """
    txn_id = "CARD-" + str(uuid.uuid4()).upper()[:8]
    now    = current_timestamp()
    conn   = get_connection()
    conn.execute(
        """INSERT INTO Card_Transactions
               (txn_id, sale_id, card_type, last_four, amount,
                terminal_ref, status, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (txn_id, sale_id, card_type,
         last_four[-4:] if last_four else "",
         amount, terminal_ref, status, now)
    )
    conn.commit()
    conn.close()
    return txn_id


def get_card_transaction(txn_id: str) -> dict | None:
    conn = get_connection()
    row  = conn.execute(
        "SELECT * FROM Card_Transactions WHERE txn_id=?", (txn_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ── Provider abstraction ──────────────────────────────────────────────────────

class CardProvider(ABC):
    """Abstract base — all card terminal providers implement this."""

    @abstractmethod
    def charge(self, amount: float, currency: str = "GHS") -> dict:
        """
        Initiate a charge on the physical terminal.
        Returns {
            "approved": bool,
            "auth_code": str,
            "card_type": str,
            "last_four": str,
            "error": str,
        }
        """

    @property
    @abstractmethod
    def name(self) -> str:
        pass


# ── Manual provider (current behavior) ───────────────────────────────────────

class ManualCardProvider(CardProvider):
    """
    No terminal integration — cashier processes card on physical POS terminal
    and manually confirms in this software.
    All fields are entered by hand; no electronic verification occurs.
    """

    @property
    def name(self) -> str:
        return "Manual (no terminal)"

    def charge(self, amount: float, currency: str = "GHS") -> dict:
        # Manual mode: always returns "approved" because cashier clicked Confirm
        return {
            "approved":  True,
            "auth_code": "",
            "card_type": "",
            "last_four": "",
            "error":     "",
        }


# ── Paystack Terminal stub (fill in when terminal is procured) ────────────────

class PaystackTerminalProvider(CardProvider):
    """
    Paystack Terminal API stub.
    API reference: developer.paystack.com/docs/terminal-api

    To activate:
      1. Set PAYSTACK_SECRET_KEY environment variable.
      2. Register your terminal in Paystack dashboard.
      3. Implement charge() using the /terminal/action endpoint.
      4. Change get_active_provider() to return PaystackTerminalProvider().
    """

    SECRET_KEY  = os.getenv("PAYSTACK_SECRET_KEY", "")
    TERMINAL_ID = os.getenv("PAYSTACK_TERMINAL_ID", "")

    @property
    def name(self) -> str:
        return "Paystack Terminal"

    def charge(self, amount: float, currency: str = "GHS") -> dict:
        """
        TO DO: Implement when terminal is procured.

        Rough flow:
          POST https://api.paystack.co/terminal/{terminal_id}/event
          {
            "type": "invoke",
            "action": "process",
            "data": {
              "action": "purchase",
              "amount": int(amount * 100),  # kobo
              "currency": "GHS",
            }
          }
          Then poll /terminal/{terminal_id}/event/{event_id}/status
        """
        raise NotImplementedError(
            "Paystack Terminal not yet configured. "
            "Set PAYSTACK_SECRET_KEY and PAYSTACK_TERMINAL_ID."
        )


# ── Active provider selector ──────────────────────────────────────────────────

def get_active_provider() -> CardProvider:
    """
    Returns the active card provider.
    Swap this return value when a terminal is procured.
    """
    return ManualCardProvider()       # → swap to PaystackTerminalProvider()


# ── High-level charge orchestrator ────────────────────────────────────────────

def process_card_payment(sale_id: str, card_type: str, amount: float,
                         last_four: str = "") -> tuple[bool, str, str]:
    """
    Entry point called by the UI.

    1. Calls the active provider's charge() method.
    2. Records the transaction.
    3. Returns (success, message, txn_id).
    """
    provider = get_active_provider()

    result = provider.charge(amount)
    status = "APPROVED" if result["approved"] else "DECLINED"

    txn_id = record_card_transaction(
        sale_id      = sale_id,
        card_type    = card_type or result.get("card_type", ""),
        amount       = amount,
        last_four    = last_four or result.get("last_four", ""),
        terminal_ref = result.get("auth_code", ""),
        status       = status,
    )

    if result["approved"]:
        return True, "Card payment recorded.", txn_id
    return False, result.get("error", "Card declined."), txn_id
