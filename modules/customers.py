"""
Customer Management module.
Handles registration, lookup, purchase history, and loyalty points.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_setup import get_connection, get_setting


def _currency_symbol() -> str:
    return get_setting("currency_symbol") or "₵"


# ── CRUD ──────────────────────────────────────────────────────────────────────

def register_customer(name: str, phone: str,
                      email: str = "", address: str = "") -> tuple[bool, str, int]:
    """
    Register a new customer.
    Returns (success, message, customer_id).
    customer_id is 0 on failure.
    """
    name  = name.strip()
    phone = phone.strip()

    if not name:
        return False, "Customer name is required.", 0
    if not phone:
        return False, "Phone number is required.", 0

    # Duplicate phone check
    if get_customer_by_phone(phone):
        return False, f"A customer with phone '{phone}' already exists.", 0

    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO Customers (name, phone, email, address, loyalty_points)
               VALUES (?, ?, ?, ?, 0)""",
            (name, phone, email.strip(), address.strip())
        )
        conn.commit()
        return True, f"Customer '{name}' registered.", cursor.lastrowid
    except Exception as e:
        return False, f"Database error: {e}", 0
    finally:
        conn.close()


def update_customer(customer_id: int, name: str, phone: str,
                    email: str = "", address: str = "") -> tuple[bool, str]:
    """Update an existing customer's details."""
    name  = name.strip()
    phone = phone.strip()

    if not name:
        return False, "Name is required."
    if not phone:
        return False, "Phone is required."

    # Duplicate phone check — exclude self
    conn = get_connection()
    existing = conn.execute(
        "SELECT customer_id FROM Customers WHERE phone = ? AND customer_id != ?",
        (phone, customer_id)
    ).fetchone()
    conn.close()
    if existing:
        return False, f"Phone '{phone}' is already used by another customer."

    conn = get_connection()
    conn.execute(
        "UPDATE Customers SET name=?, phone=?, email=?, address=? WHERE customer_id=?",
        (name, phone, email.strip(), address.strip(), customer_id)
    )
    conn.commit()
    conn.close()
    return True, "Customer updated."


def delete_customer(customer_id: int) -> tuple[bool, str]:
    """
    Delete a customer record.
    Blocked if the customer has linked sales (FK constraint).
    """
    conn = get_connection()
    linked = conn.execute(
        "SELECT COUNT(*) FROM Sales WHERE customer_id=?", (customer_id,)
    ).fetchone()[0]
    conn.close()

    if linked:
        return False, (
            f"Cannot delete — customer has {linked} sale record(s). "
            "Deactivate or anonymise instead."
        )

    conn = get_connection()
    conn.execute("DELETE FROM Customers WHERE customer_id=?", (customer_id,))
    conn.commit()
    conn.close()
    return True, "Customer deleted."


# ── Lookups ───────────────────────────────────────────────────────────────────

def get_all_customers() -> list[dict]:
    """Return all customers ordered by name."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM Customers ORDER BY name"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_customer_by_id(customer_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM Customers WHERE customer_id=?", (customer_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_customer_by_phone(phone: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM Customers WHERE phone=?", (phone.strip(),)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def search_customers(query: str) -> list[dict]:
    """Search by name, phone, or email (partial, case-insensitive)."""
    q = f"%{query.strip()}%"
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM Customers
           WHERE name LIKE ? OR phone LIKE ? OR email LIKE ?
           ORDER BY name LIMIT 50""",
        (q, q, q)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Purchase history ──────────────────────────────────────────────────────────

def get_purchase_history(customer_id: int) -> list[dict]:
    """
    Return all sales for a customer (newest first).
    Each entry includes a nested items list.
    """
    conn = get_connection()
    sales = conn.execute(
        """SELECT s.sale_id, s.date, s.subtotal, s.discount,
                  s.tax, s.total_amount, s.payment_method,
                  u.username AS cashier
           FROM Sales s
           LEFT JOIN Users u ON s.user_id = u.user_id
           WHERE s.customer_id = ?
           ORDER BY s.date DESC""",
        (customer_id,)
    ).fetchall()

    result = []
    for sale in sales:
        sale_dict = dict(sale)
        items = conn.execute(
            """SELECT si.quantity, si.price, p.product_name
               FROM Sales_Items si
               JOIN Products p ON si.product_id = p.product_id
               WHERE si.sale_id = ?""",
            (sale_dict["sale_id"],)
        ).fetchall()
        sale_dict["items"] = [dict(i) for i in items]
        result.append(sale_dict)

    conn.close()
    return result


def get_customer_stats(customer_id: int) -> dict:
    """Return total spend, visit count, and average basket for a customer."""
    conn = get_connection()
    row = conn.execute(
        """SELECT COUNT(*)                    AS visits,
                  COALESCE(SUM(total_amount), 0) AS total_spend,
                  COALESCE(AVG(total_amount), 0) AS avg_basket
           FROM Sales WHERE customer_id=?""",
        (customer_id,)
    ).fetchone()
    conn.close()
    return {
        "visits":      row["visits"],
        "total_spend": round(row["total_spend"], 2),
        "avg_basket":  round(row["avg_basket"],  2),
    }


# ── Loyalty points ────────────────────────────────────────────────────────────

def add_loyalty_points(customer_id: int, sale_total: float) -> int:
    """
    Award 1 point per 10 currency units spent (called automatically by sales module).
    Returns the number of points awarded.
    """
    points = int(sale_total // 10)
    if points <= 0:
        return 0
    conn = get_connection()
    conn.execute(
        "UPDATE Customers SET loyalty_points = loyalty_points + ? WHERE customer_id=?",
        (points, customer_id)
    )
    conn.commit()
    conn.close()
    return points


def redeem_loyalty_points(customer_id: int,
                          points_to_redeem: int) -> tuple[bool, str, float]:
    """
    Redeem loyalty points as a discount.
    Rate: 1 point = 0.10 in the configured currency.
    Returns (success, message, discount_amount).
    """
    customer = get_customer_by_id(customer_id)
    if not customer:
        return False, "Customer not found.", 0.0

    available = customer["loyalty_points"]
    if points_to_redeem <= 0:
        return False, "Enter a positive number of points to redeem.", 0.0
    if points_to_redeem > available:
        return False, (
            f"Only {available} point(s) available. "
            f"Cannot redeem {points_to_redeem}."
        ), 0.0

    discount = round(points_to_redeem * 0.10, 2)

    conn = get_connection()
    conn.execute(
        "UPDATE Customers SET loyalty_points = loyalty_points - ? WHERE customer_id=?",
        (points_to_redeem, customer_id)
    )
    conn.commit()
    conn.close()

    cur = _currency_symbol()
    return True, (
        f"{points_to_redeem} point(s) redeemed for {cur}{discount:.2f} discount."
    ), discount


def get_loyalty_balance(customer_id: int) -> int:
    """Return the current loyalty point balance for a customer."""
    customer = get_customer_by_id(customer_id)
    return customer["loyalty_points"] if customer else 0
