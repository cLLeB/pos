"""
Returns & Refunds Module
========================
Handles product returns, inventory restoration, and refund tracking.

Public API
----------
get_returnable_items(sale_id)                           -> list[dict]
process_return(sale_id, items, reason, user_id,
               restock=True)                            -> (bool, str, str)
get_return_by_id(return_id)                             -> dict | None
get_returns_by_sale(sale_id)                            -> list[dict]
get_recent_returns(limit=50)                            -> list[dict]
get_daily_return_summary(date_str)                      -> dict
"""

import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_setup import get_connection
from utils.helpers import current_timestamp


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_returnable_items(sale_id: str) -> list:
    """
    Returns the items from *sale_id* that still have returnable quantity.

    returnable_qty = original_qty - already_returned_qty

    Each dict: sale_item_id, product_id, product_name, original_qty,
               returned_qty, returnable_qty, price
    """
    conn = get_connection()
    try:
        if not conn.execute(
            "SELECT 1 FROM Sales WHERE sale_id=?", (sale_id,)
        ).fetchone():
            return []

        items = conn.execute(
            """
            SELECT si.sale_item_id,
                   si.product_id,
                   p.product_name,
                   si.quantity AS original_qty,
                   si.price
            FROM   Sales_Items si
            JOIN   Products p ON p.product_id = si.product_id
            WHERE  si.sale_id = ?
            """,
            (sale_id,)
        ).fetchall()

        result = []
        for row in items:
            already = conn.execute(
                """
                SELECT COALESCE(SUM(ri.quantity), 0)
                FROM   Return_Items ri
                JOIN   Returns r ON r.return_id = ri.return_id
                WHERE  ri.sale_item_id = ?
                  AND  r.status = 'completed'
                """,
                (row["sale_item_id"],)
            ).fetchone()[0]

            result.append({
                "sale_item_id":  row["sale_item_id"],
                "product_id":    row["product_id"],
                "product_name":  row["product_name"],
                "original_qty":  row["original_qty"],
                "returned_qty":  already,
                "returnable_qty": row["original_qty"] - already,
                "price":         row["price"],
            })
        return result
    finally:
        conn.close()


def process_return(
    sale_id: str,
    return_items: list,
    reason: str,
    user_id: int,
    restock: bool = True,
) -> tuple:
    """
    Creates a completed return record and optionally restores stock.

    Parameters
    ----------
    sale_id      : original sale identifier
    return_items : list[dict] — each must have:
                   {sale_item_id, product_id, quantity, price}
    reason       : free-text return reason (required)
    user_id      : user processing the return
    restock      : True  -> restore quantity to Products (default)
                   False -> item is damaged / write-off, no restock

    Returns
    -------
    (success: bool, message: str, return_id: str)
    return_id is "" on failure.
    """
    if not return_items:
        return False, "No items selected for return.", ""

    conn = get_connection()
    try:
        sale = conn.execute(
            "SELECT sale_id, customer_id FROM Sales WHERE sale_id=?",
            (sale_id,)
        ).fetchone()
        if not sale:
            return False, f"Sale '{sale_id}' not found.", ""

        # -- Validate all quantities before touching any data --
        for item in return_items:
            original_row = conn.execute(
                "SELECT quantity FROM Sales_Items WHERE sale_item_id=?",
                (item["sale_item_id"],)
            ).fetchone()
            if not original_row:
                return (
                    False,
                    f"Sale item {item['sale_item_id']} not found.",
                    ""
                )
            already = conn.execute(
                """
                SELECT COALESCE(SUM(ri.quantity), 0)
                FROM   Return_Items ri
                JOIN   Returns r ON r.return_id = ri.return_id
                WHERE  ri.sale_item_id = ?
                  AND  r.status = 'completed'
                """,
                (item["sale_item_id"],)
            ).fetchone()[0]

            max_returnable = original_row["quantity"] - already
            if item["quantity"] > max_returnable:
                return (
                    False,
                    f"Return quantity ({item['quantity']}) would exceed "
                    f"returnable amount ({max_returnable}).",
                    ""
                )

        # -- Write the return --
        return_id    = "RTN-" + str(uuid.uuid4()).upper()[:8]
        total_refund = sum(i["quantity"] * i["price"] for i in return_items)
        now          = current_timestamp()

        conn.execute(
            """
            INSERT INTO Returns
                (return_id, sale_id, date, user_id, customer_id,
                 reason, total_refund, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'completed')
            """,
            (
                return_id, sale_id, now, user_id,
                sale["customer_id"], reason, total_refund,
            )
        )

        for item in return_items:
            conn.execute(
                """
                INSERT INTO Return_Items
                    (return_id, sale_item_id, product_id,
                     quantity, price, restocked)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    return_id,
                    item["sale_item_id"],
                    item["product_id"],
                    item["quantity"],
                    item["price"],
                    1 if restock else 0,
                )
            )

            if restock:
                conn.execute(
                    "UPDATE Products "
                    "SET quantity = quantity + ? "
                    "WHERE product_id = ?",
                    (item["quantity"], item["product_id"])
                )
                conn.execute(
                    "INSERT INTO Inventory "
                    "    (product_id, adjustment, reason, date) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        item["product_id"],
                        item["quantity"],
                        f"Return #{return_id}",
                        now,
                    )
                )

        conn.commit()
        return True, "Return processed successfully.", return_id

    except Exception as exc:
        conn.rollback()
        return False, f"Error processing return: {exc}", ""
    finally:
        conn.close()


def get_return_by_id(return_id: str) -> dict | None:
    """Returns the full return record including line items, or None."""
    conn = get_connection()
    try:
        ret = conn.execute(
            """
            SELECT r.*, u.username AS cashier_name
            FROM   Returns r
            JOIN   Users u ON u.user_id = r.user_id
            WHERE  r.return_id = ?
            """,
            (return_id,)
        ).fetchone()
        if not ret:
            return None

        result = dict(ret)
        result["items"] = [
            dict(row)
            for row in conn.execute(
                """
                SELECT ri.*, p.product_name
                FROM   Return_Items ri
                JOIN   Products p ON p.product_id = ri.product_id
                WHERE  ri.return_id = ?
                """,
                (return_id,)
            ).fetchall()
        ]
        return result
    finally:
        conn.close()


def get_returns_by_sale(sale_id: str) -> list:
    """Returns all return records for a given sale, newest first."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM Returns WHERE sale_id=? ORDER BY date DESC",
            (sale_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_recent_returns(limit: int = 50) -> list:
    """Returns the most recent return records, newest first."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT r.*, u.username AS cashier_name
            FROM   Returns r
            JOIN   Users u ON u.user_id = r.user_id
            ORDER  BY r.date DESC
            LIMIT  ?
            """,
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_daily_return_summary(date_str: str) -> dict:
    """
    Summary of completed returns for date_str (YYYY-MM-DD).

    Keys: date, count, total_refunded, items_restocked
    """
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count,
                   COALESCE(SUM(total_refund), 0) AS total_refunded
            FROM   Returns
            WHERE  date LIKE ? AND status = 'completed'
            """,
            (f"{date_str}%",)
        ).fetchone()

        restocked = conn.execute(
            """
            SELECT COALESCE(SUM(ri.quantity), 0)
            FROM   Return_Items ri
            JOIN   Returns r ON r.return_id = ri.return_id
            WHERE  r.date LIKE ?
              AND  ri.restocked = 1
              AND  r.status = 'completed'
            """,
            (f"{date_str}%",)
        ).fetchone()[0]

        return {
            "date":            date_str,
            "count":           row["count"],
            "total_refunded":  row["total_refunded"],
            "items_restocked": restocked,
        }
    finally:
        conn.close()
