"""
Sales Processing module.
Handles creating sales, persisting them to the database, and triggering
inventory deductions. Called by the payment dialog after payment is confirmed.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_setup import get_connection
from utils.helpers import generate_transaction_id, current_timestamp, calculate_total
from modules.inventory import deduct_stock_for_sale


# ── Sale creation ─────────────────────────────────────────────────────────────

def create_sale(
    user_id: int,
    cart_items: list[dict],
    payment_method: str,
    discount: float = 0.0,
    tax_rate: float = 0.16,
    customer_id: int = None,
) -> tuple[bool, str, str]:
    """
    Persist a completed sale to the database.

    Steps:
      1. Validate the cart is not empty.
      2. Calculate totals (subtotal, discount, tax, total).
      3. Insert one row into Sales.
      4. Insert one row per cart item into Sales_Items.
      5. Deduct stock for every item via the inventory module.
      6. Update customer loyalty points if a customer is linked.

    Returns: (success, message, sale_id)
    """
    if not cart_items:
        return False, "Cannot create a sale with an empty cart.", ""

    if not payment_method:
        return False, "Payment method is required.", ""

    sale_id  = generate_transaction_id()
    date_now = current_timestamp()

    subtotal = sum(item["price"] * item["quantity"] for item in cart_items)
    totals   = calculate_total(subtotal, discount, tax_rate)

    conn = get_connection()
    try:
        # ── Insert sale header ────────────────────────────────────────────
        conn.execute(
            """INSERT INTO Sales
               (sale_id, date, user_id, customer_id,
                subtotal, discount, tax, total_amount, payment_method)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                sale_id, date_now, user_id, customer_id,
                totals["subtotal"], totals["discount"],
                totals["tax"],     totals["total"],
                payment_method,
            )
        )

        # ── Insert sale items ─────────────────────────────────────────────
        for item in cart_items:
            conn.execute(
                """INSERT INTO Sales_Items
                   (sale_id, product_id, quantity, price)
                   VALUES (?, ?, ?, ?)""",
                (sale_id, item["product_id"], item["quantity"], item["price"])
            )

        conn.commit()

    except Exception as e:
        conn.rollback()
        conn.close()
        return False, f"Database error while saving sale: {e}", ""
    finally:
        conn.close()

    # ── Deduct inventory (outside the main transaction so partial failures ──
    # ── are logged individually, not silently swallowed) ──────────────────
    for item in cart_items:
        ok, msg = deduct_stock_for_sale(item["product_id"], item["quantity"], sale_id)
        if not ok:
            # Log the failure — sale is already committed and payment collected.
            # A supervisor can manually adjust stock via the Inventory screen.
            try:
                from modules.backup import log_action
                log_action(user_id, "INVENTORY_WARNING", msg)
            except Exception:
                pass

    # ── Award loyalty points ───────────────────────────────────────────────
    if customer_id:
        _award_loyalty_points(customer_id, totals["total"])

    # ── Audit log ─────────────────────────────────────────────────────────
    try:
        from modules.backup import log_action
        log_action(user_id, "SALE",
                   f"{sale_id} | {len(cart_items)} items | ${totals['total']:.2f} | {payment_method}")
    except Exception:
        pass  # Audit failure must never block a completed sale

    return True, f"Sale {sale_id} recorded successfully.", sale_id


# ── Sale queries ──────────────────────────────────────────────────────────────

def get_sale_by_id(sale_id: str) -> dict | None:
    """
    Return a sale dict with a nested list of items.
    Returns None if the sale_id does not exist.
    """
    conn = get_connection()
    sale_row = conn.execute(
        """SELECT s.*, u.username AS cashier_name,
                  c.name AS customer_name
           FROM Sales s
           LEFT JOIN Users     u ON s.user_id     = u.user_id
           LEFT JOIN Customers c ON s.customer_id = c.customer_id
           WHERE s.sale_id = ?""",
        (sale_id,)
    ).fetchone()

    if not sale_row:
        conn.close()
        return None

    sale = dict(sale_row)

    items = conn.execute(
        """SELECT si.*, p.product_name
           FROM Sales_Items si
           JOIN Products p ON si.product_id = p.product_id
           WHERE si.sale_id = ?""",
        (sale_id,)
    ).fetchall()

    sale["items"] = [dict(i) for i in items]
    conn.close()
    return sale


def get_recent_sales(limit: int = 50) -> list[dict]:
    """Return the most recent sales (newest first), without items."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT s.sale_id, s.date, s.total_amount, s.payment_method,
                  u.username AS cashier_name,
                  c.name     AS customer_name
           FROM Sales s
           LEFT JOIN Users     u ON s.user_id     = u.user_id
           LEFT JOIN Customers c ON s.customer_id = c.customer_id
           ORDER BY s.date DESC LIMIT ?""",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_sales_by_date(date_str: str) -> list[dict]:
    """
    Return all sales for a given date (YYYY-MM-DD).
    Includes a nested items list for each sale.
    """
    conn = get_connection()
    rows = conn.execute(
        """SELECT s.*, u.username AS cashier_name,
                  c.name AS customer_name
           FROM Sales s
           LEFT JOIN Users     u ON s.user_id     = u.user_id
           LEFT JOIN Customers c ON s.customer_id = c.customer_id
           WHERE s.date LIKE ?
           ORDER BY s.date DESC""",
        (date_str + "%",)
    ).fetchall()

    sales = []
    for row in rows:
        sale = dict(row)
        items = conn.execute(
            """SELECT si.*, p.product_name
               FROM Sales_Items si
               JOIN Products p ON si.product_id = p.product_id
               WHERE si.sale_id = ?""",
            (sale["sale_id"],)
        ).fetchall()
        sale["items"] = [dict(i) for i in items]
        sales.append(sale)

    conn.close()
    return sales


def get_sales_between(start: str, end: str) -> list[dict]:
    """
    Return all sales between two datetime strings (inclusive).
    Used by the reports module.
    """
    conn = get_connection()
    rows = conn.execute(
        """SELECT s.*, u.username AS cashier_name
           FROM Sales s
           LEFT JOIN Users u ON s.user_id = u.user_id
           WHERE s.date BETWEEN ? AND ?
           ORDER BY s.date DESC""",
        (start, end)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_daily_summary(date_str: str) -> dict:
    """
    Return a summary for a given date:
    transaction_count, total_revenue, total_discount, total_tax.
    """
    conn = get_connection()
    row = conn.execute(
        """SELECT COUNT(*)            AS tx_count,
                  COALESCE(SUM(total_amount), 0) AS revenue,
                  COALESCE(SUM(discount),     0) AS discounts,
                  COALESCE(SUM(tax),          0) AS taxes
           FROM Sales WHERE date LIKE ?""",
        (date_str + "%",)
    ).fetchone()
    conn.close()
    return {
        "date":           date_str,
        "tx_count":       row["tx_count"],
        "revenue":        round(row["revenue"],   2),
        "discounts":      round(row["discounts"], 2),
        "taxes":          round(row["taxes"],     2),
    }


# ── Internal helpers ──────────────────────────────────────────────────────────

def _award_loyalty_points(customer_id: int, sale_total: float):
    """Award 1 loyalty point for every $10 spent (truncated)."""
    points = int(sale_total // 10)
    if points > 0:
        conn = get_connection()
        conn.execute(
            "UPDATE Customers SET loyalty_points = loyalty_points + ? WHERE customer_id = ?",
            (points, customer_id)
        )
        conn.commit()
        conn.close()
