"""
Home panel shown after admin/manager login.
Displays quick-summary cards: total products, today's sales, low-stock count.
"""

import tkinter as tk
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ui.login_screen import COLORS
from database.db_setup import get_connection
from utils.helpers import current_date, format_currency


def _fetch_summary() -> dict:
    """Query the DB for dashboard summary numbers."""
    conn = get_connection()
    products     = conn.execute("SELECT COUNT(*) FROM Products").fetchone()[0]
    low_stock_th = int(conn.execute("SELECT value FROM Settings WHERE key='low_stock_threshold'").fetchone()[0])
    low_stock    = conn.execute("SELECT COUNT(*) FROM Products WHERE quantity <= ?", (low_stock_th,)).fetchone()[0]
    today        = current_date()
    sales_today  = conn.execute("SELECT COUNT(*) FROM Sales WHERE date LIKE ?", (today + "%",)).fetchone()[0]
    revenue_row  = conn.execute("SELECT SUM(total_amount) FROM Sales WHERE date LIKE ?", (today + "%",)).fetchone()[0]
    revenue_today = revenue_row if revenue_row else 0.0
    customers    = conn.execute("SELECT COUNT(*) FROM Customers").fetchone()[0]
    from datetime import date as _date
    today = _date.today().strftime("%Y-%m-%d")
    returns_today = conn.execute(
        "SELECT COUNT(*) FROM Returns "
        "WHERE date LIKE ? AND status='completed'",
        (f"{today}%",)
    ).fetchone()[0]
    conn.close()
    return {
        "products":      products,
        "low_stock":     low_stock,
        "sales_today":   sales_today,
        "revenue_today": revenue_today,
        "customers":     customers,
        "returns_today": returns_today,
    }


class HomePanel:
    def __init__(self, parent: tk.Frame):
        self.parent = parent
        self._build_ui()

    def _build_ui(self):
        summary = _fetch_summary()

        tk.Label(
            self.parent, text="Dashboard Overview",
            font=("Segoe UI", 18, "bold"),
            bg=COLORS["bg"], fg=COLORS["white"]
        ).pack(anchor="w", padx=32, pady=(28, 4))

        tk.Label(
            self.parent, text=f"Welcome back!  |  Today: {current_date()}",
            font=("Segoe UI", 10),
            bg=COLORS["bg"], fg=COLORS["muted"]
        ).pack(anchor="w", padx=32, pady=(0, 24))

        # Cards row
        cards_frame = tk.Frame(self.parent, bg=COLORS["bg"])
        cards_frame.pack(fill="x", padx=32)

        cards = [
            ("📦 Products",      str(summary["products"]),          COLORS["accent"]),
            ("⚠️ Low Stock",     str(summary["low_stock"]),         "#c0392b"),
            ("🧾 Sales Today",   str(summary["sales_today"]),       "#27ae60"),
            ("💰 Revenue Today", format_currency(summary["revenue_today"]), "#8e44ad"),
            ("👥 Customers",     str(summary["customers"]),         "#2980b9"),
            ("↩ Returns Today", str(summary["returns_today"]),     "#e74c3c"),
        ]

        for title, value, color in cards:
            card = tk.Frame(cards_frame, bg=color, padx=20, pady=20, relief="flat")
            card.pack(side="left", padx=8, pady=8, ipadx=10, ipady=10)
            tk.Label(card, text=title,  font=("Segoe UI", 9),  bg=color, fg=COLORS["white"]).pack(anchor="w")
            tk.Label(card, text=value,  font=("Segoe UI", 22, "bold"), bg=color, fg=COLORS["white"]).pack(anchor="w")

        # Quick-tip text
        tk.Label(
            self.parent,
            text="Use the sidebar to navigate between modules.",
            font=("Segoe UI", 10), bg=COLORS["bg"], fg=COLORS["muted"]
        ).pack(anchor="w", padx=32, pady=(32, 0))
