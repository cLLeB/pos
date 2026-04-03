"""
Payment Processing module.
Handles saving payment records and retrieving payment details per sale.
Called by the payment dialog after the cashier confirms payment.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_setup import get_connection, get_setting
from utils.helpers import current_timestamp


def _currency_symbol() -> str:
    return get_setting("currency_symbol") or "₵"


# ── Payment processors ────────────────────────────────────────────────────────

def process_cash_payment(sale_id: str, amount_paid: float,
                         total: float) -> tuple[bool, str, float]:
    """
    Record a cash payment and calculate change.

    Returns (success, message, change_given).
    """
    cur = _currency_symbol()
    if amount_paid < total:
        return False, (
            f"Insufficient cash. Total is {cur}{total:.2f} "
            f"but only {cur}{amount_paid:.2f} was tendered."
        ), 0.0

    change = round(amount_paid - total, 2)

    ok, msg = _save_payment(
        sale_id,
        amount_paid,
        change,
        "Cash",
        status="COMPLETED",
        provider="Cash Drawer",
        paid_at=current_timestamp(),
    )
    if not ok:
        return False, msg, 0.0

    return True, f"Cash payment accepted. Change: {cur}{change:.2f}.", change


def process_mobile_payment(sale_id: str, amount: float,
                           provider: str, reference: str) -> tuple[bool, str]:
    """
    Record a mobile money payment.
    `reference` is the transaction code from the mobile platform.

    Returns (success, message).
    """
    if not reference.strip():
        return False, "A transaction reference is required for mobile money."

    ok, msg = _save_payment(
        sale_id,
        amount,
        0.0,
        f"Mobile Money ({provider})",
        reference=reference.strip(),
        status="COMPLETED",
        provider=provider,
        paid_at=current_timestamp(),
    )
    return ok, msg


def process_card_payment(sale_id: str, amount: float,
                         card_type: str = "Card") -> tuple[bool, str]:
    """
    Record a card payment.

    Returns (success, message).
    """
    ok, msg = _save_payment(
        sale_id,
        amount,
        0.0,
        card_type,
        status="COMPLETED",
        provider="Card Terminal",
        paid_at=current_timestamp(),
    )
    return ok, msg


def record_payment(
    sale_id: str,
    amount_paid: float,
    payment_type: str,
    *,
    change_given: float = 0.0,
    reference: str = "",
    status: str = "COMPLETED",
    provider: str = "",
    paid_at: str | None = None,
) -> tuple[bool, str]:
    """Public helper to store any payment with optional gateway metadata."""
    return _save_payment(
        sale_id,
        amount_paid,
        change_given,
        payment_type,
        reference=reference,
        status=status,
        provider=provider,
        paid_at=paid_at or (current_timestamp() if status == "COMPLETED" else ""),
    )


def log_payment_event(
    payment_ref: str,
    source: str,
    event_type: str,
    event_status: str,
    payload_json: str = "",
) -> None:
    """Store raw payment webhook/provider events for reconciliation."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO Payment_Events
               (payment_ref, source, event_type, event_status, payload_json, received_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (payment_ref, source, event_type, event_status, payload_json, current_timestamp())
        )
        conn.commit()
    finally:
        conn.close()


# ── Payment queries ───────────────────────────────────────────────────────────

def get_payment_by_sale(sale_id: str) -> dict | None:
    """Return the payment record for a given sale, or None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM Payments WHERE sale_id = ?", (sale_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_payments_summary(start: str, end: str) -> dict:
    """
    Return totals grouped by payment type between two datetime strings.
    Used by the reports module.
    """
    conn = get_connection()
    rows = conn.execute(
        """SELECT payment_type,
                  COUNT(*)           AS tx_count,
                  SUM(amount_paid)   AS total_collected
           FROM Payments p
           JOIN Sales s ON p.sale_id = s.sale_id
           WHERE s.date BETWEEN ? AND ?
           GROUP BY payment_type
           ORDER BY total_collected DESC""",
        (start, end)
    ).fetchall()
    conn.close()
    return {
        r["payment_type"]: {
            "count":     r["tx_count"],
            "collected": round(r["total_collected"], 2),
        }
        for r in rows
    }


def get_recent_payments(limit: int = 100) -> list[dict]:
    """Return recent payment records with sale timestamp for monitoring views."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT p.payment_id, p.sale_id, p.amount_paid, p.payment_type,
                  p.payment_status, p.provider, p.external_reference, p.paid_at,
                  s.date AS sale_date
           FROM Payments p
           LEFT JOIN Sales s ON p.sale_id = s.sale_id
           ORDER BY COALESCE(NULLIF(p.paid_at, ''), s.date) DESC, p.payment_id DESC
           LIMIT ?""",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_payment_events(limit: int = 150) -> list[dict]:
    """Return recent webhook/provider payment events for reconciliation."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT *
           FROM Payment_Events
           ORDER BY received_at DESC, event_id DESC
           LIMIT ?""",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_momo_transactions(limit: int = 100) -> list[dict]:
    """Return recent MoMo transactions with status progression metadata."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT txn_id, sale_id, phone, amount, provider, reference,
                  status, failure_reason, created_at, updated_at
           FROM MoMo_Transactions
           ORDER BY updated_at DESC, created_at DESC
           LIMIT ?""",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Internal helper ───────────────────────────────────────────────────────────

def _save_payment(sale_id: str, amount_paid: float, change_given: float,
                  payment_type: str, reference: str = "",
                  status: str = "COMPLETED",
                  provider: str = "",
                  paid_at: str = "") -> tuple[bool, str]:
    """Insert a row into the Payments table."""
    conn = get_connection()
    try:
        # Store reference in payment_type field if provided
        ptype = f"{payment_type} | ref:{reference}" if reference else payment_type
        conn.execute(
            """INSERT INTO Payments
               (sale_id, amount_paid, change_given, payment_type,
                payment_status, provider, external_reference, paid_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                sale_id,
                round(amount_paid, 2),
                round(change_given, 2),
                ptype,
                status,
                provider,
                reference.strip() if reference else "",
                paid_at,
            )
        )
        conn.commit()
        return True, "Payment recorded."
    except Exception as e:
        return False, f"Failed to record payment: {e}"
    finally:
        conn.close()
