"""
Reports UI.
Date-range picker, report-type selector, results table, summary cards,
and CSV export.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ui.login_screen import COLORS
from database.db_setup import get_setting
from modules.reports import (
    daily_sales_report, weekly_sales_report,
    product_performance_report, inventory_report,
    cashier_performance_report, profit_report,
    export_report_to_csv,
)


REPORT_TYPES = [
    "Daily Sales",
    "Weekly / Period Sales",
    "Product Performance",
    "Inventory Status",
    "Cashier Performance",
    "Profit Report",
]


class ReportsUI(tk.Frame):
    """Main reports panel embedded in the admin dashboard."""

    def __init__(self, parent):
        super().__init__(parent, bg=COLORS["bg"])
        self.pack(fill="both", expand=True)
        self._current_data = None
        self._build()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        # ── Control bar ───────────────────────────────────────────────────
        ctrl = tk.Frame(self, bg=COLORS["panel"], padx=16, pady=12)
        ctrl.pack(fill="x")

        tk.Label(ctrl, text="Report Type:", bg=COLORS["panel"],
                 fg=COLORS["muted"], font=("Segoe UI", 9)).grid(
                     row=0, column=0, sticky="w", padx=(0, 6))

        self._report_var = tk.StringVar(value=REPORT_TYPES[0])
        report_cb = ttk.Combobox(ctrl, textvariable=self._report_var,
                                 values=REPORT_TYPES, state="readonly", width=24)
        report_cb.grid(row=0, column=1, padx=(0, 20))
        report_cb.bind("<<ComboboxSelected>>", self._on_type_change)

        tk.Label(ctrl, text="From:", bg=COLORS["panel"],
                 fg=COLORS["muted"], font=("Segoe UI", 9)).grid(
                     row=0, column=2, sticky="w", padx=(0, 4))
        self._from_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        tk.Entry(ctrl, textvariable=self._from_var, width=12,
                 bg=COLORS["bg"], fg=COLORS["white"],
                 insertbackground=COLORS["white"],
                 relief="flat").grid(row=0, column=3, padx=(0, 16))

        tk.Label(ctrl, text="To:", bg=COLORS["panel"],
                 fg=COLORS["muted"], font=("Segoe UI", 9)).grid(
                     row=0, column=4, sticky="w", padx=(0, 4))
        self._to_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        tk.Entry(ctrl, textvariable=self._to_var, width=12,
                 bg=COLORS["bg"], fg=COLORS["white"],
                 insertbackground=COLORS["white"],
                 relief="flat").grid(row=0, column=5, padx=(0, 16))

        # Quick-range buttons
        for idx, (label, delta) in enumerate([("Today", 0), ("Last 7d", 7), ("Last 30d", 30)]):
            tk.Button(ctrl, text=label,
                      bg=COLORS["panel"], fg=COLORS["accent"],
                      activebackground=COLORS["bg"],
                      font=("Segoe UI", 8), relief="flat",
                      cursor="hand2",
                      command=lambda d=delta: self._quick_range(d)).grid(
                          row=0, column=6 + idx, padx=2)

        tk.Button(ctrl, text="Generate",
                  bg=COLORS["accent"], fg=COLORS["white"],
                  activebackground=COLORS["button"],
                  font=("Segoe UI", 9, "bold"), relief="flat",
                  padx=14, cursor="hand2",
                  command=self._generate).grid(row=0, column=9, padx=(20, 4))

        tk.Button(ctrl, text="Export CSV",
                  bg=COLORS["panel"], fg=COLORS["white"],
                  activebackground=COLORS["accent"],
                  font=("Segoe UI", 9), relief="flat",
                  padx=10, cursor="hand2",
                  command=self._export).grid(row=0, column=10, padx=(4, 0))

        # ── Summary cards row ─────────────────────────────────────────────
        self._cards_frame = tk.Frame(self, bg=COLORS["bg"])
        self._cards_frame.pack(fill="x", padx=16, pady=(12, 0))

        # ── Results table area ────────────────────────────────────────────
        self._tree_frame = tk.Frame(self, bg=COLORS["bg"])
        self._tree_frame.pack(fill="both", expand=True, padx=16, pady=12)

        self._placeholder = tk.Label(
            self._tree_frame,
            text="Select a report type and press Generate.",
            bg=COLORS["bg"], fg=COLORS["muted"],
            font=("Segoe UI", 10, "italic")
        )
        self._placeholder.pack(pady=40)

    # ── Controls ──────────────────────────────────────────────────────────────

    def _on_type_change(self, _event=None):
        rt    = self._report_var.get()
        today = datetime.now().strftime("%Y-%m-%d")
        if rt == "Daily Sales":
            self._from_var.set(today)
            self._to_var.set(today)
        elif rt in ("Weekly / Period Sales", "Profit Report"):
            week_ago = (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d")
            self._from_var.set(week_ago)
            self._to_var.set(today)

    def _quick_range(self, days: int):
        today = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        self._from_var.set(start if days else today)
        self._to_var.set(today)

    # ── Generate ──────────────────────────────────────────────────────────────

    def _generate(self):
        rt    = self._report_var.get()
        start = self._from_var.get().strip()
        end   = self._to_var.get().strip()

        date_required = rt in (
            "Daily Sales", "Weekly / Period Sales",
            "Cashier Performance", "Profit Report"
        )
        if date_required:
            try:
                datetime.strptime(start, "%Y-%m-%d")
                datetime.strptime(end,   "%Y-%m-%d")
            except ValueError:
                messagebox.showerror("Invalid Date",
                    "Please enter dates in YYYY-MM-DD format.", parent=self)
                return

        try:
            if rt == "Daily Sales":
                data = daily_sales_report(start)
            elif rt == "Weekly / Period Sales":
                data = weekly_sales_report(start, end)
            elif rt == "Product Performance":
                data = product_performance_report()
            elif rt == "Inventory Status":
                data = inventory_report()
            elif rt == "Cashier Performance":
                data = cashier_performance_report(start, end)
            else:
                data = profit_report(start, end)
        except Exception as e:
            messagebox.showerror("Report Error", str(e), parent=self)
            return

        self._current_data = data
        self._render(data, rt)

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _render(self, data: dict, rt: str):
        self._build_summary_cards(data, rt)
        self._build_table(data, rt)

    def _build_summary_cards(self, data: dict, rt: str):
        for w in self._cards_frame.winfo_children():
            w.destroy()

        _cur = get_setting("currency_symbol") or "₵"
        cards = []
        if rt == "Daily Sales":
            cards = [
                ("Transactions",  str(data["transactions"])),
                ("Revenue",       f"{_cur}{data['revenue']:,.2f}"),
                ("Discounts",     f"{_cur}{data['total_discount']:,.2f}"),
                ("Tax Collected", f"{_cur}{data['total_tax']:,.2f}"),
            ]
        elif rt in ("Weekly / Period Sales", "Profit Report"):
            cards = [
                ("Transactions", str(data["transactions"])),
                ("Revenue",      f"{_cur}{data['revenue']:,.2f}"),
                ("Discounts",    f"{_cur}{data['total_discount']:,.2f}"),
                ("Tax",          f"{_cur}{data['total_tax']:,.2f}"),
            ]
        elif rt == "Product Performance":
            total_rev  = sum(p["revenue"]    for p in data["products"])
            total_sold = sum(p["units_sold"] for p in data["products"])
            cards = [
                ("Products",      str(len(data["products"]))),
                ("Units Sold",    str(total_sold)),
                ("Total Revenue", f"{_cur}{total_rev:,.2f}"),
            ]
        elif rt == "Inventory Status":
            cards = [
                ("Total Products", str(data["total_products"])),
                ("Low Stock",      str(data["low_stock_count"])),
                ("Out of Stock",   str(data["out_of_stock_count"])),
                ("Threshold",      str(data["threshold"])),
            ]
        elif rt == "Cashier Performance":
            total = sum(c["revenue"] for c in data["cashiers"])
            cards = [
                ("Cashiers",      str(len(data["cashiers"]))),
                ("Total Revenue", f"{_cur}{total:,.2f}"),
            ]

        for label, value in cards:
            card = tk.Frame(self._cards_frame, bg=COLORS["panel"], padx=18, pady=10)
            card.pack(side="left", padx=(0, 10), pady=(0, 4))
            tk.Label(card, text=value, bg=COLORS["panel"],
                     fg=COLORS["white"],
                     font=("Segoe UI", 14, "bold")).pack()
            tk.Label(card, text=label, bg=COLORS["panel"],
                     fg=COLORS["muted"],
                     font=("Segoe UI", 8)).pack()

    def _build_table(self, data: dict, rt: str):
        for w in self._tree_frame.winfo_children():
            w.destroy()

        cols, rows = self._get_table_data(data, rt)
        if not cols:
            tk.Label(self._tree_frame,
                     text="No data to display for this report.",
                     bg=COLORS["bg"], fg=COLORS["muted"],
                     font=("Segoe UI", 10, "italic")).pack(pady=40)
            return

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Report.Treeview",
                         background=COLORS["panel"],
                         foreground=COLORS["white"],
                         fieldbackground=COLORS["panel"],
                         rowheight=26, font=("Segoe UI", 9))
        style.configure("Report.Treeview.Heading",
                         background=COLORS["button"],
                         foreground=COLORS["white"],
                         font=("Segoe UI", 9, "bold"))
        style.map("Report.Treeview",
                  background=[("selected", COLORS["accent"])])

        tree = ttk.Treeview(self._tree_frame, columns=cols,
                             show="headings", style="Report.Treeview")

        for col in cols:
            tree.heading(col, text=col)
            tree.column(col, anchor="w", width=self._col_width(col))

        tree.tag_configure("odd",  background=COLORS["panel"])
        tree.tag_configure("even", background=COLORS["bg"])
        tree.tag_configure("low",  foreground="#F59E0B")
        tree.tag_configure("out",  foreground="#EF4444")

        for i, row in enumerate(rows):
            base_tag  = "odd" if i % 2 else "even"
            extra_tag = self._row_extra_tag(rt, row)
            tags      = (base_tag, extra_tag) if extra_tag else (base_tag,)
            tree.insert("", "end", values=row, tags=tags)

        vsb = ttk.Scrollbar(self._tree_frame, orient="vertical",
                             command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)

    def _get_table_data(self, data: dict, rt: str):
        """Return (column_names, list_of_row_tuples) for the Treeview."""
        _cur = get_setting("currency_symbol") or "₵"

        if rt == "Daily Sales":
            if not data.get("top_products"):
                return [], []
            cols = ["Product", "Units Sold", "Revenue"]
            rows = [(p["product_name"], p["units_sold"],
                     f"{_cur}{p['revenue']:,.2f}") for p in data["top_products"]]
            return cols, rows

        if rt == "Weekly / Period Sales":
            if not data.get("daily_breakdown"):
                return [], []
            cols = ["Date", "Transactions", "Revenue"]
            rows = [(d["day"], d["transactions"],
                     f"{_cur}{d['revenue']:,.2f}") for d in data["daily_breakdown"]]
            return cols, rows

        if rt == "Product Performance":
            cols = ["Product", "Category", "Units Sold", "Revenue", "Current Stock"]
            rows = [(p["product_name"], p["category"], p["units_sold"],
                     f"{_cur}{p['revenue']:,.2f}", p["current_stock"])
                    for p in data["products"]]
            return cols, rows

        if rt == "Inventory Status":
            cols = ["Product", "Category", "Stock", "Status", "Price"]
            rows = [(p["product_name"], p["category"], p["quantity"],
                     p["status"].upper(), f"{_cur}{p['price']:,.2f}")
                    for p in data["products"]]
            return cols, rows

        if rt == "Cashier Performance":
            if not data.get("cashiers"):
                return [], []
            cols = ["Cashier", "Transactions", "Revenue", "Avg Sale"]
            rows = [(c["cashier"], c["transactions"],
                     f"{_cur}{c['revenue']:,.2f}", f"{_cur}{c['avg_sale']:,.2f}")
                    for c in data["cashiers"]]
            return cols, rows

        # Profit Report
        if not data.get("daily_breakdown"):
            return [], []
        cols = ["Date", "Transactions", "Revenue", "Subtotal", "Discount", "Tax"]
        rows = [(d["day"], d["transactions"],
                 f"{_cur}{d['revenue']:,.2f}", f"{_cur}{d['subtotal']:,.2f}",
                 f"{_cur}{d['discount']:,.2f}", f"{_cur}{d['tax']:,.2f}")
                for d in data["daily_breakdown"]]
        return cols, rows

    def _row_extra_tag(self, rt: str, row: tuple) -> str:
        if rt == "Inventory Status":
            status = row[3].lower()
            if status == "out":
                return "out"
            if status == "low":
                return "low"
        return ""

    def _col_width(self, col: str) -> int:
        wide = {"Product": 180, "Category": 110, "Revenue": 100,
                "Subtotal": 100, "Date": 100}
        return wide.get(col, 90)

    # ── Export ────────────────────────────────────────────────────────────────

    def _export(self):
        if not self._current_data:
            messagebox.showwarning("No Data",
                "Generate a report first before exporting.", parent=self)
            return
        ok, result = export_report_to_csv(self._current_data)
        if ok:
            messagebox.showinfo("Exported",
                f"Report saved to:\n{result}", parent=self)
        else:
            messagebox.showerror("Export Failed", result, parent=self)
