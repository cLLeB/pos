"""
Inventory Management module.
Tracks stock levels, logs every adjustment, and surfaces low-stock alerts.
Called automatically after every sale (wired in Day 6).
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_setup import get_connection, get_setting
from utils.helpers import current_timestamp


# ── Stock operations ──────────────────────────────────────────────────────────

def update_stock(product_id: int, quantity_change: int, reason: str) -> tuple[bool, str]:
    """
    Add or subtract stock for a product and log the adjustment.
    quantity_change: positive = restock, negative = deduction (sale/damage).
    Returns (success, message).
    """
    if quantity_change == 0:
        return False, "Quantity change cannot be zero."
    if not reason or not reason.strip():
        return False, "A reason is required for stock adjustments."

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT product_name, quantity FROM Products WHERE product_id = ?",
            (product_id,)
        ).fetchone()

        if not row:
            return False, "Product not found."

        new_qty = row["quantity"] + quantity_change
        if new_qty < 0:
            return False, (
                f"Insufficient stock. Current: {row['quantity']}, "
                f"requested deduction: {abs(quantity_change)}."
            )

        conn.execute(
            "UPDATE Products SET quantity = ? WHERE product_id = ?",
            (new_qty, product_id)
        )
        conn.execute(
            "INSERT INTO Inventory (product_id, adjustment, reason, date) VALUES (?, ?, ?, ?)",
            (product_id, quantity_change, reason.strip(), current_timestamp())
        )
        conn.commit()
        direction = "added" if quantity_change > 0 else "removed"
        return True, (
            f"{abs(quantity_change)} unit(s) {direction} for '{row['product_name']}'. "
            f"New stock: {new_qty}."
        )
    except Exception as e:
        return False, f"Database error: {e}"
    finally:
        conn.close()


def restock_product(product_id: int, quantity: int, supplier: str = "") -> tuple[bool, str]:
    """
    Convenience wrapper for adding stock (reorder / supplier delivery).
    """
    if quantity <= 0:
        return False, "Restock quantity must be greater than zero."
    reason = f"Restock" + (f" from {supplier}" if supplier else "")
    return update_stock(product_id, quantity, reason)


def deduct_stock_for_sale(product_id: int, quantity: int, sale_id: str) -> tuple[bool, str]:
    """
    Deduct stock after a completed sale. Called by the sales module (Day 6).
    """
    return update_stock(product_id, -quantity, f"Sale #{sale_id}")


# ── Stock queries ─────────────────────────────────────────────────────────────

def get_all_stock() -> list[dict]:
    """
    Return all products with current stock levels, sorted by name.
    Each dict includes product fields plus a 'status' key:
      'ok', 'low', or 'out'.
    """
    threshold = _get_threshold()
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM Products ORDER BY product_name"
    ).fetchall()
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        qty = d["quantity"]
        if qty == 0:
            d["status"] = "out"
        elif qty <= threshold:
            d["status"] = "low"
        else:
            d["status"] = "ok"
        result.append(d)
    return result


def check_low_stock(threshold: int = None) -> list[dict]:
    """
    Return all products whose quantity is at or below the threshold.
    If threshold is not given, uses the value from Settings.
    """
    if threshold is None:
        threshold = _get_threshold()
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM Products WHERE quantity <= ? ORDER BY quantity ASC",
        (threshold,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_inventory_log(product_id: int = None, limit: int = 200) -> list[dict]:
    """
    Return the stock adjustment history, newest first.
    Optionally filtered to a single product.
    Each row includes product_name joined from Products.
    """
    conn = get_connection()
    if product_id:
        rows = conn.execute(
            """SELECT i.*, p.product_name
               FROM Inventory i
               JOIN Products p ON i.product_id = p.product_id
               WHERE i.product_id = ?
               ORDER BY i.inventory_id DESC LIMIT ?""",
            (product_id, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT i.*, p.product_name
               FROM Inventory i
               JOIN Products p ON i.product_id = p.product_id
               ORDER BY i.inventory_id DESC LIMIT ?""",
            (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stock_summary() -> dict:
    """
    Return a summary dict for the dashboard:
      total_products, low_stock_count, out_of_stock_count, total_units.
    """
    threshold = _get_threshold()
    conn = get_connection()
    total_products   = conn.execute("SELECT COUNT(*) FROM Products").fetchone()[0]
    low_stock_count  = conn.execute(
        "SELECT COUNT(*) FROM Products WHERE quantity > 0 AND quantity <= ?", (threshold,)
    ).fetchone()[0]
    out_of_stock     = conn.execute(
        "SELECT COUNT(*) FROM Products WHERE quantity = 0"
    ).fetchone()[0]
    total_units      = conn.execute(
        "SELECT COALESCE(SUM(quantity), 0) FROM Products"
    ).fetchone()[0]
    conn.close()
    return {
        "total_products":   total_products,
        "low_stock_count":  low_stock_count,
        "out_of_stock":     out_of_stock,
        "total_units":      total_units,
        "threshold":        threshold,
    }


# ── Internal helper ───────────────────────────────────────────────────────────

def _get_threshold() -> int:
    """Read the low-stock threshold from Settings (default 5)."""
    try:
        return int(get_setting("low_stock_threshold") or 5)
    except ValueError:
        return 5
