"""
Inventory Management UI.
Three sections:
  1. Summary cards (total products, low-stock count, out-of-stock, total units)
  2. Stock table (all products colour-coded by status)
  3. Adjustment log (last 200 changes)
"""

import tkinter as tk
from tkinter import ttk, messagebox
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ui.login_screen import COLORS
from modules import inventory as inv_mod
from modules import products as prod_mod
from database.db_setup import get_setting


class InventoryUI:
    def __init__(self, parent: tk.Frame):
        self.parent = parent
        self._build_ui()
        self._load_data()

    # ── Top-level layout ──────────────────────────────────────────────────────

    def _build_ui(self):
        # Page header
        header = tk.Frame(self.parent, bg=COLORS["bg"])
        header.pack(fill="x", padx=32, pady=(24, 0))

        tk.Label(
            header, text="Inventory Management",
            font=("Segoe UI", 18, "bold"),
            bg=COLORS["bg"], fg=COLORS["white"]
        ).pack(side="left")

        tk.Button(
            header, text="Refresh",
            font=("Segoe UI", 9),
            bg=COLORS["panel"], fg=COLORS["white"],
            activebackground=COLORS["accent"],
            relief="flat", bd=0, padx=12, pady=5,
            cursor="hand2", command=self._load_data
        ).pack(side="right")

        # Summary cards row
        self.cards_frame = tk.Frame(self.parent, bg=COLORS["bg"])
        self.cards_frame.pack(fill="x", padx=32, pady=(16, 0))

        # Notebook: Stock Levels / Adjustment Log tabs
        style = ttk.Style()
        style.theme_use("default")
        style.configure("TNotebook",
            background=COLORS["bg"], borderwidth=0)
        style.configure("TNotebook.Tab",
            background=COLORS["panel"],
            foreground=COLORS["text"],
            font=("Segoe UI", 10),
            padding=[14, 6]
        )
        style.map("TNotebook.Tab",
            background=[("selected", COLORS["accent"])],
            foreground=[("selected", COLORS["white"])]
        )

        self.notebook = ttk.Notebook(self.parent)
        self.notebook.pack(fill="both", expand=True, padx=32, pady=12)

        # Tab 1 — Stock Levels
        self.stock_tab = tk.Frame(self.notebook, bg=COLORS["bg"])
        self.notebook.add(self.stock_tab, text="  Stock Levels  ")
        self._build_stock_tab()

        # Tab 2 — Adjustment Log
        self.log_tab = tk.Frame(self.notebook, bg=COLORS["bg"])
        self.notebook.add(self.log_tab, text="  Adjustment Log  ")
        self._build_log_tab()

    # ── Summary cards ─────────────────────────────────────────────────────────

    def _refresh_summary(self):
        for w in self.cards_frame.winfo_children():
            w.destroy()

        s = inv_mod.get_stock_summary()
        cards = [
            ("Total Products",  str(s["total_products"]),  COLORS["accent"]),
            ("Low Stock",       str(s["low_stock_count"]),  "#c0392b"),
            ("Out of Stock",    str(s["out_of_stock"]),     "#7f0000"),
            ("Total Units",     str(s["total_units"]),      "#27ae60"),
            ("Alert Threshold", str(s["threshold"]) + " units", "#8e44ad"),
        ]
        for title, value, color in cards:
            card = tk.Frame(self.cards_frame, bg=color, padx=18, pady=14)
            card.pack(side="left", padx=(0, 10), pady=(0, 8))
            tk.Label(card, text=title, font=("Segoe UI", 8),
                     bg=color, fg=COLORS["white"]).pack(anchor="w")
            tk.Label(card, text=value, font=("Segoe UI", 18, "bold"),
                     bg=color, fg=COLORS["white"]).pack(anchor="w")

    # ── Stock Levels tab ──────────────────────────────────────────────────────

    def _build_stock_tab(self):
        # Toolbar
        bar = tk.Frame(self.stock_tab, bg=COLORS["bg"])
        bar.pack(fill="x", pady=(8, 4))

        tk.Label(bar, text="Filter:",
                 font=("Segoe UI", 9), bg=COLORS["bg"], fg=COLORS["muted"]).pack(side="left")

        self.stock_filter_var = tk.StringVar(value="All")
        for label in ("All", "Low Stock", "Out of Stock"):
            tk.Radiobutton(
                bar, text=label, variable=self.stock_filter_var, value=label,
                font=("Segoe UI", 9),
                bg=COLORS["bg"], fg=COLORS["text"],
                selectcolor=COLORS["accent"],
                activebackground=COLORS["bg"],
                command=self._apply_stock_filter
            ).pack(side="left", padx=(8, 0))

        tk.Button(
            bar, text="Adjust Stock",
            font=("Segoe UI", 10, "bold"),
            bg=COLORS["button"], fg=COLORS["white"],
            activebackground=COLORS["button_hover"],
            relief="flat", bd=0, padx=14, pady=5,
            cursor="hand2", command=self._open_adjust_dialog
        ).pack(side="right", padx=(0, 0))

        tk.Button(
            bar, text="Restock Selected",
            font=("Segoe UI", 10),
            bg=COLORS["accent"], fg=COLORS["white"],
            activebackground=COLORS["button"],
            relief="flat", bd=0, padx=14, pady=5,
            cursor="hand2", command=self._open_restock_dialog
        ).pack(side="right", padx=(0, 8))

        # Treeview
        tf = tk.Frame(self.stock_tab, bg=COLORS["bg"])
        tf.pack(fill="both", expand=True)

        self._style_tree()

        sb = ttk.Scrollbar(tf, orient="vertical")
        sb.pack(side="right", fill="y")

        cols = ("id", "name", "category", "price", "quantity", "status")
        self.stock_tree = ttk.Treeview(
            tf, columns=cols, show="headings",
            yscrollcommand=sb.set, selectmode="browse"
        )
        sb.config(command=self.stock_tree.yview)

        col_cfg = [
            ("id",       "ID",        55,  "center"),
            ("name",     "Product",   240, "w"),
            ("category", "Category",  130, "center"),
            ("price",    "Price",     90,  "e"),
            ("quantity", "Stock",     80,  "center"),
            ("status",   "Status",    110, "center"),
        ]
        for col, heading, width, anchor in col_cfg:
            self.stock_tree.heading(col, text=heading)
            self.stock_tree.column(col, width=width, anchor=anchor)

        self.stock_tree.tag_configure("ok",  foreground=COLORS["success"])
        self.stock_tree.tag_configure("low", foreground="#e74c3c")
        self.stock_tree.tag_configure("out",
            foreground="#ffffff", background="#7f0000")

        self.stock_tree.pack(fill="both", expand=True)
        self.stock_tree.bind("<Double-Button-1>", lambda e: self._open_adjust_dialog())

        self._all_stock: list[dict] = []

    def _style_tree(self):
        s = ttk.Style()
        s.theme_use("default")
        s.configure("Treeview",
            background=COLORS["panel"], foreground=COLORS["text"],
            rowheight=32, fieldbackground=COLORS["panel"],
            font=("Segoe UI", 10))
        s.configure("Treeview.Heading",
            background=COLORS["accent"], foreground=COLORS["white"],
            font=("Segoe UI", 10, "bold"), relief="flat")
        s.map("Treeview", background=[("selected", COLORS["button"])])

    def _render_stock(self, items: list[dict]):
        for r in self.stock_tree.get_children():
            self.stock_tree.delete(r)
        _cur = get_setting("currency_symbol") or "₵"
        for p in items:
            status_text = {"ok": "OK", "low": "Low Stock", "out": "Out of Stock"}.get(p["status"], "")
            self.stock_tree.insert("", "end", values=(
                p["product_id"],
                p["product_name"],
                p["category"],
                f"{_cur}{p['price']:.2f}",
                p["quantity"],
                status_text,
            ), tags=(p["status"],))

    def _apply_stock_filter(self, *_):
        f = self.stock_filter_var.get()
        if f == "Low Stock":
            shown = [p for p in self._all_stock if p["status"] == "low"]
        elif f == "Out of Stock":
            shown = [p for p in self._all_stock if p["status"] == "out"]
        else:
            shown = self._all_stock
        self._render_stock(shown)

    def _get_selected_stock_product(self) -> dict | None:
        sel = self.stock_tree.selection()
        if not sel:
            messagebox.showwarning("No Selection", "Please select a product first.")
            return None
        values = self.stock_tree.item(sel[0])["values"]
        return prod_mod.get_product_by_id(values[0])

    # ── Adjustment Log tab ────────────────────────────────────────────────────

    def _build_log_tab(self):
        bar = tk.Frame(self.log_tab, bg=COLORS["bg"])
        bar.pack(fill="x", pady=(8, 4))

        tk.Label(bar, text="Last 200 stock adjustments (newest first)",
                 font=("Segoe UI", 9), bg=COLORS["bg"], fg=COLORS["muted"]).pack(side="left")
        tk.Button(
            bar, text="Refresh Log",
            font=("Segoe UI", 9),
            bg=COLORS["panel"], fg=COLORS["white"],
            activebackground=COLORS["accent"],
            relief="flat", bd=0, padx=10, pady=4,
            cursor="hand2", command=self._load_log
        ).pack(side="right")

        lf = tk.Frame(self.log_tab, bg=COLORS["bg"])
        lf.pack(fill="both", expand=True)

        sb2 = ttk.Scrollbar(lf, orient="vertical")
        sb2.pack(side="right", fill="y")

        log_cols = ("log_id", "product", "change", "reason", "date")
        self.log_tree = ttk.Treeview(
            lf, columns=log_cols, show="headings",
            yscrollcommand=sb2.set, selectmode="none"
        )
        sb2.config(command=self.log_tree.yview)

        log_col_cfg = [
            ("log_id",  "#",       55,  "center"),
            ("product", "Product", 220, "w"),
            ("change",  "Change",  80,  "center"),
            ("reason",  "Reason",  260, "w"),
            ("date",    "Date",    170, "center"),
        ]
        for col, heading, width, anchor in log_col_cfg:
            self.log_tree.heading(col, text=heading)
            self.log_tree.column(col, width=width, anchor=anchor)

        self.log_tree.tag_configure("pos", foreground=COLORS["success"])
        self.log_tree.tag_configure("neg", foreground="#e74c3c")
        self.log_tree.pack(fill="both", expand=True)

    def _load_log(self):
        for r in self.log_tree.get_children():
            self.log_tree.delete(r)
        entries = inv_mod.get_inventory_log()
        for e in entries:
            change = e["adjustment"]
            tag = "pos" if change > 0 else "neg"
            sign = f"+{change}" if change > 0 else str(change)
            self.log_tree.insert("", "end", values=(
                e["inventory_id"],
                e["product_name"],
                sign,
                e["reason"],
                e["date"],
            ), tags=(tag,))

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load_data(self):
        self._refresh_summary()
        self._all_stock = inv_mod.get_all_stock()
        self._apply_stock_filter()
        self._load_log()

    # ── Dialogs ───────────────────────────────────────────────────────────────

    def _open_adjust_dialog(self):
        product = self._get_selected_stock_product()
        if not product:
            return
        AdjustStockDialog(self.parent, product, on_success=self._load_data)

    def _open_restock_dialog(self):
        product = self._get_selected_stock_product()
        if not product:
            return
        RestockDialog(self.parent, product, on_success=self._load_data)


# ── Adjust Stock Dialog ───────────────────────────────────────────────────────

class AdjustStockDialog(tk.Toplevel):
    """
    Manually add or remove stock for a product.
    Used for corrections, damage write-offs, audits, etc.
    """

    REASONS = [
        "Stock audit correction",
        "Damaged / expired goods",
        "Theft / shrinkage",
        "Returned to supplier",
        "Opening stock entry",
        "Manual adjustment",
        "Other",
    ]

    def __init__(self, parent, product: dict, on_success):
        super().__init__(parent)
        self.product = product
        self.on_success = on_success

        self.title("Adjust Stock")
        self.geometry("380x400")
        self.configure(bg=COLORS["bg"])
        self.resizable(False, False)
        self.grab_set()
        self._build()

    def _build(self):
        tk.Label(self, text="Adjust Stock",
                 font=("Segoe UI", 14, "bold"),
                 bg=COLORS["bg"], fg=COLORS["white"]).pack(pady=(18, 2))

        tk.Label(self,
                 text=f"{self.product['product_name']}  —  Current stock: {self.product['quantity']}",
                 font=("Segoe UI", 10),
                 bg=COLORS["bg"], fg=COLORS["muted"]).pack()

        form = tk.Frame(self, bg=COLORS["bg"], padx=28)
        form.pack(fill="x", pady=12)

        # Direction
        tk.Label(form, text="Adjustment Type",
                 font=("Segoe UI", 9), bg=COLORS["bg"], fg=COLORS["muted"]).pack(anchor="w", pady=(8, 4))

        self.direction_var = tk.StringVar(value="add")
        dir_row = tk.Frame(form, bg=COLORS["bg"])
        dir_row.pack(fill="x")
        for label, val in (("Add stock  (+)", "add"), ("Remove stock  (-)", "remove")):
            tk.Radiobutton(
                dir_row, text=label, variable=self.direction_var, value=val,
                font=("Segoe UI", 10),
                bg=COLORS["bg"], fg=COLORS["text"],
                selectcolor=COLORS["accent"],
                activebackground=COLORS["bg"]
            ).pack(side="left", padx=(0, 18))

        # Quantity
        tk.Label(form, text="Quantity",
                 font=("Segoe UI", 9), bg=COLORS["bg"], fg=COLORS["muted"]).pack(anchor="w", pady=(12, 2))
        self.qty_var = tk.StringVar(value="1")
        tk.Entry(form, textvariable=self.qty_var,
                 font=("Segoe UI", 12), bg=COLORS["accent"],
                 fg=COLORS["white"], insertbackground=COLORS["white"],
                 relief="flat", bd=6).pack(fill="x")

        # Reason
        tk.Label(form, text="Reason",
                 font=("Segoe UI", 9), bg=COLORS["bg"], fg=COLORS["muted"]).pack(anchor="w", pady=(12, 2))
        self.reason_var = tk.StringVar(value=self.REASONS[0])
        reason_combo = ttk.Combobox(form, textvariable=self.reason_var,
                                    values=self.REASONS, font=("Segoe UI", 10),
                                    state="normal")
        reason_combo.pack(fill="x")

        # Error label
        self.error_var = tk.StringVar()
        tk.Label(form, textvariable=self.error_var,
                 font=("Segoe UI", 9), bg=COLORS["bg"], fg=COLORS["error"]).pack(pady=(8, 0))

        tk.Button(form, text="Apply Adjustment",
                  font=("Segoe UI", 11, "bold"),
                  bg=COLORS["button"], fg=COLORS["white"],
                  activebackground=COLORS["button_hover"],
                  relief="flat", bd=0, pady=9,
                  cursor="hand2", command=self._submit).pack(fill="x", pady=(10, 0))

    def _submit(self):
        try:
            qty = int(self.qty_var.get())
            if qty <= 0:
                raise ValueError
        except ValueError:
            self.error_var.set("Enter a valid positive integer.")
            return

        change = qty if self.direction_var.get() == "add" else -qty
        reason = self.reason_var.get().strip()
        if not reason:
            self.error_var.set("Please select or enter a reason.")
            return

        ok, msg = inv_mod.update_stock(self.product["product_id"], change, reason)
        if ok:
            self.on_success()
            self.destroy()
            messagebox.showinfo("Stock Updated", msg)
        else:
            self.error_var.set(msg)


# ── Restock Dialog ────────────────────────────────────────────────────────────

class RestockDialog(tk.Toplevel):
    """Quick restock dialog — pre-set to 'Add' with supplier field."""

    def __init__(self, parent, product: dict, on_success):
        super().__init__(parent)
        self.product = product
        self.on_success = on_success

        self.title("Restock Product")
        self.geometry("360x300")
        self.configure(bg=COLORS["bg"])
        self.resizable(False, False)
        self.grab_set()
        self._build()

    def _build(self):
        tk.Label(self, text="Restock Product",
                 font=("Segoe UI", 14, "bold"),
                 bg=COLORS["bg"], fg=COLORS["white"]).pack(pady=(18, 2))
        tk.Label(self,
                 text=f"{self.product['product_name']}  —  Current: {self.product['quantity']} units",
                 font=("Segoe UI", 10),
                 bg=COLORS["bg"], fg=COLORS["muted"]).pack()

        form = tk.Frame(self, bg=COLORS["bg"], padx=28)
        form.pack(fill="x", pady=14)

        tk.Label(form, text="Quantity to Add",
                 font=("Segoe UI", 9), bg=COLORS["bg"], fg=COLORS["muted"]).pack(anchor="w", pady=(0, 2))
        self.qty_var = tk.StringVar(value="10")
        tk.Entry(form, textvariable=self.qty_var,
                 font=("Segoe UI", 12), bg=COLORS["accent"],
                 fg=COLORS["white"], insertbackground=COLORS["white"],
                 relief="flat", bd=6).pack(fill="x")

        tk.Label(form, text="Supplier (optional)",
                 font=("Segoe UI", 9), bg=COLORS["bg"], fg=COLORS["muted"]).pack(anchor="w", pady=(12, 2))
        self.supplier_var = tk.StringVar()
        tk.Entry(form, textvariable=self.supplier_var,
                 font=("Segoe UI", 11), bg=COLORS["accent"],
                 fg=COLORS["white"], insertbackground=COLORS["white"],
                 relief="flat", bd=6).pack(fill="x")

        self.error_var = tk.StringVar()
        tk.Label(form, textvariable=self.error_var,
                 font=("Segoe UI", 9), bg=COLORS["bg"], fg=COLORS["error"]).pack(pady=(6, 0))

        tk.Button(form, text="Confirm Restock",
                  font=("Segoe UI", 11, "bold"),
                  bg=COLORS["success"], fg=COLORS["white"],
                  activebackground="#388e3c",
                  relief="flat", bd=0, pady=9,
                  cursor="hand2", command=self._submit).pack(fill="x", pady=(10, 0))

    def _submit(self):
        try:
            qty = int(self.qty_var.get())
            if qty <= 0:
                raise ValueError
        except ValueError:
            self.error_var.set("Enter a valid positive integer.")
            return

        ok, msg = inv_mod.restock_product(
            self.product["product_id"], qty, self.supplier_var.get().strip()
        )
        if ok:
            self.on_success()
            self.destroy()
            messagebox.showinfo("Restocked", msg)
        else:
            self.error_var.set(msg)
