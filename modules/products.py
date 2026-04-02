"""
Product Management module.
Handles all CRUD operations for products in the POS system.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db_setup import get_connection


# ── Read operations ───────────────────────────────────────────────────────────

def get_all_products() -> list[dict]:
    """Return all products ordered by name."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM Products ORDER BY product_name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_product_by_id(product_id: int) -> dict | None:
    """Return a single product by its ID, or None if not found."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM Products WHERE product_id = ?", (product_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_product_by_barcode(barcode: str) -> dict | None:
    """Return a product matching the given barcode, or None if not found."""
    if not barcode:
        return None
    conn = get_connection()
    row = conn.execute("SELECT * FROM Products WHERE barcode = ?", (barcode.strip(),)).fetchone()
    conn.close()
    return dict(row) if row else None


def search_product(query: str) -> list[dict]:
    """
    Search products by name or barcode (case-insensitive partial match).
    Returns up to 30 results ordered by name.
    """
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM Products
           WHERE product_name LIKE ? OR barcode LIKE ?
           ORDER BY product_name LIMIT 30""",
        (f"%{query}%", f"%{query}%")
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_categories() -> list[str]:
    """Return all distinct product categories currently in the database."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT category FROM Products ORDER BY category"
    ).fetchall()
    conn.close()
    categories = [r["category"] for r in rows]
    # Always include these defaults even if no products exist
    defaults = ["Beverages", "Bakery", "Dairy", "Grains", "Snacks",
                "Household", "Personal Care", "Electronics", "Other"]
    for d in defaults:
        if d not in categories:
            categories.append(d)
    return sorted(set(categories))


# ── Write operations ──────────────────────────────────────────────────────────

def add_product(name: str, category: str, price: float,
                quantity: int, barcode: str) -> tuple[bool, str]:
    """
    Add a new product to the database.
    Returns (success, message).
    """
    # Validate inputs
    name = name.strip()
    barcode = barcode.strip() if barcode else None

    if not name:
        return False, "Product name is required."
    if not category:
        return False, "Category is required."
    try:
        price = float(price)
        quantity = int(quantity)
    except (ValueError, TypeError):
        return False, "Price and quantity must be numbers."
    if price < 0:
        return False, "Price cannot be negative."
    if quantity < 0:
        return False, "Quantity cannot be negative."

    # Check for duplicate barcode
    if barcode and get_product_by_barcode(barcode):
        return False, f"A product with barcode '{barcode}' already exists."

    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO Products (product_name, category, price, quantity, barcode) VALUES (?, ?, ?, ?, ?)",
            (name, category, round(price, 2), quantity, barcode)
        )
        conn.commit()
        return True, f"Product '{name}' added successfully."
    except Exception as e:
        return False, f"Database error: {e}"
    finally:
        conn.close()


def update_product(product_id: int, name: str, category: str,
                   price: float, quantity: int, barcode: str) -> tuple[bool, str]:
    """
    Update all fields of an existing product.
    Returns (success, message).
    """
    name = name.strip()
    barcode = barcode.strip() if barcode else None

    if not name:
        return False, "Product name is required."
    try:
        price = float(price)
        quantity = int(quantity)
    except (ValueError, TypeError):
        return False, "Price and quantity must be numbers."
    if price < 0:
        return False, "Price cannot be negative."
    if quantity < 0:
        return False, "Quantity cannot be negative."

    # Check for duplicate barcode (exclude the current product)
    if barcode:
        conn = get_connection()
        existing = conn.execute(
            "SELECT product_id FROM Products WHERE barcode = ? AND product_id != ?",
            (barcode, product_id)
        ).fetchone()
        conn.close()
        if existing:
            return False, f"Barcode '{barcode}' is already used by another product."

    conn = get_connection()
    try:
        conn.execute(
            """UPDATE Products
               SET product_name = ?, category = ?, price = ?, quantity = ?, barcode = ?
               WHERE product_id = ?""",
            (name, category, round(price, 2), quantity, barcode, product_id)
        )
        conn.commit()
        return True, f"Product '{name}' updated successfully."
    except Exception as e:
        return False, f"Database error: {e}"
    finally:
        conn.close()


def delete_product(product_id: int) -> tuple[bool, str]:
    """
    Delete a product by ID.
    Returns (success, message).
    """
    product = get_product_by_id(product_id)
    if not product:
        return False, "Product not found."

    conn = get_connection()
    try:
        conn.execute("DELETE FROM Products WHERE product_id = ?", (product_id,))
        conn.commit()
        return True, f"Product '{product['product_name']}' deleted."
    except Exception as e:
        return False, f"Cannot delete: {e}"
    finally:
        conn.close()
