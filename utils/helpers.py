"""
Shared utility functions used across the POS system.
"""

import uuid
from datetime import datetime


def generate_transaction_id() -> str:
    """Generate a unique transaction ID (e.g., TXN-3F2A...)."""
    return "TXN-" + str(uuid.uuid4()).upper()[:8]


def current_timestamp() -> str:
    """Return the current date and time as a formatted string."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def current_date() -> str:
    """Return today's date as a string (YYYY-MM-DD)."""
    return datetime.now().strftime("%Y-%m-%d")


def format_currency(amount: float) -> str:
    """Format a number as a currency string, reading the symbol from Settings."""
    try:
        from database.db_setup import get_setting
        sym = get_setting("currency_symbol") or "₵"
    except Exception:
        sym = "₵"
    return f"{sym}{amount:,.2f}"


def calculate_tax(subtotal: float, tax_rate: float = 0.16) -> float:
    """Calculate tax amount from subtotal and tax rate."""
    return round(subtotal * tax_rate, 2)


def calculate_total(subtotal: float, discount: float = 0.0, tax_rate: float = 0.16) -> dict:
    """
    Calculate full order totals.
    Returns a dict with subtotal, discount, tax, and total.
    """
    discounted = subtotal - discount
    tax = calculate_tax(discounted, tax_rate)
    total = round(discounted + tax, 2)
    return {
        "subtotal": round(subtotal, 2),
        "discount": round(discount, 2),
        "tax": round(tax, 2),
        "total": total
    }
