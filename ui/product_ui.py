"""
Product Management UI.
Full CRUD table: view all products, add, edit, delete, live search filter.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ui.login_screen import COLORS
from modules import products as product_mod
from database.db_setup import get_setting


class ProductUI:
    def __init__(self, parent: tk.Frame):
        self.parent = parent
        self._build_ui()
        self._load_products()

    # ── Layout ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Header row ────────────────────────────────────────────────────
        header = tk.Frame(self.parent, bg=COLORS["bg"])
        header.pack(fill="x", padx=32, pady=(24, 0))

        tk.Label(
            header, text="Product Management",
            font=("Segoe UI", 18, "bold"),
            bg=COLORS["bg"], fg=COLORS["white"]
        ).pack(side="left")

        tk.Button(
            header, text="+ Add Product",
            font=("Segoe UI", 10, "bold"),
            bg=COLORS["button"], fg=COLORS["white"],
            activebackground=COLORS["button_hover"],
            relief="flat", bd=0, padx=14, pady=6,
            cursor="hand2", command=self._open_add_dialog
        ).pack(side="right")

        # ── Search bar ────────────────────────────────────────────────────
        search_row = tk.Frame(self.parent, bg=COLORS["bg"])
        search_row.pack(fill="x", padx=32, pady=(12, 8))

        tk.Label(
            search_row, text="Search:",
            font=("Segoe UI", 10),
            bg=COLORS["bg"], fg=COLORS["muted"]
        ).pack(side="left")

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._on_search_change)

        tk.Entry(
            search_row, textvariable=self.search_var,
            font=("Segoe UI", 11), width=34,
            bg=COLORS["accent"], fg=COLORS["white"],
            insertbackground=COLORS["white"],
            relief="flat", bd=6
        ).pack(side="left", padx=(8, 12))

        tk.Button(
            search_row, text="Clear",
            font=("Segoe UI", 9),
            bg=COLORS["panel"], fg=COLORS["muted"],
            activebackground=COLORS["accent"],
            relief="flat", bd=0, padx=10, pady=4,
            cursor="hand2",
            command=lambda: self.search_var.set("")
        ).pack(side="left")

        self.count_label = tk.Label(
            search_row, text="",
            font=("Segoe UI", 9),
            bg=COLORS["bg"], fg=COLORS["muted"]
        )
        self.count_label.pack(side="right")

        # ── Product table ─────────────────────────────────────────────────
        table_frame = tk.Frame(self.parent, bg=COLORS["bg"])
        table_frame.pack(fill="both", expand=True, padx=32, pady=(0, 4))

        self._style_treeview()

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")

        columns = ("id", "name", "category", "price", "quantity", "barcode")
        self.tree = ttk.Treeview(
            table_frame, columns=columns, show="headings",
            yscrollcommand=scrollbar.set, selectmode="browse"
        )
        scrollbar.config(command=self.tree.yview)

        # Column headings and widths
        col_cfg = [
            ("id",       "ID",        55,  "center"),
            ("name",     "Product Name", 240, "w"),
            ("category", "Category",  130, "center"),
            ("price",    "Price",     90,  "e"),
            ("quantity", "Stock",     80,  "center"),
            ("barcode",  "Barcode",   160, "center"),
        ]
        for col, heading, width, anchor in col_cfg:
            self.tree.heading(col, text=heading,
                              command=lambda c=col: self._sort_by(c))
            self.tree.column(col, width=width, anchor=anchor)

        # Row colour tags
        self.tree.tag_configure("low_stock", foreground="#e74c3c")
        self.tree.tag_configure("out_stock",
                                foreground="#ffffff",
                                background="#7f0000")

        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-Button-1>", lambda e: self._open_edit_dialog())

        # ── Action buttons ────────────────────────────────────────────────
        actions = tk.Frame(self.parent, bg=COLORS["bg"])
        actions.pack(fill="x", padx=32, pady=(4, 16))

        btn = dict(
            font=("Segoe UI", 10),
            bg=COLORS["accent"], fg=COLORS["white"],
            activebackground=COLORS["button"],
            activeforeground=COLORS["white"],
            relief="flat", bd=0, padx=14, pady=6,
            cursor="hand2"
        )
        tk.Button(actions, text="Edit Selected",  command=self._open_edit_dialog,   **btn).pack(side="left", padx=(0, 8))
        tk.Button(actions, text="Delete Selected",command=self._delete_selected,
                  bg="#c0392b", activebackground="#922b21",
                  fg=COLORS["white"], font=("Segoe UI", 10),
                  relief="flat", bd=0, padx=14, pady=6,
                  cursor="hand2").pack(side="left", padx=(0, 8))
        tk.Button(actions, text="Refresh",        command=self._load_products,       **btn).pack(side="right")

        # Legend
        legend = tk.Frame(self.parent, bg=COLORS["bg"])
        legend.pack(fill="x", padx=32, pady=(0, 8))
        tk.Label(legend, text="  Low stock (<=5)  ",
                 font=("Segoe UI", 8), bg=COLORS["bg"], fg="#e74c3c").pack(side="left")
        tk.Label(legend, text="  Out of stock  ",
                 font=("Segoe UI", 8), bg="#7f0000", fg="white").pack(side="left")

        # Track sort state
        self._sort_col = "name"
        self._sort_asc = True
        # Full product list (unfiltered)
        self._all_products: list[dict] = []

    def _style_treeview(self):
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview",
            background=COLORS["panel"],
            foreground=COLORS["text"],
            rowheight=32,
            fieldbackground=COLORS["panel"],
            font=("Segoe UI", 10)
        )
        style.configure("Treeview.Heading",
            background=COLORS["accent"],
            foreground=COLORS["white"],
            font=("Segoe UI", 10, "bold"),
            relief="flat"
        )
        style.map("Treeview", background=[("selected", COLORS["button"])])

    # ── Data loading & filtering ──────────────────────────────────────────────

    def _load_products(self, filter_text: str = ""):
        """Fetch products from DB, apply optional text filter, populate table."""
        self._all_products = product_mod.get_all_products()
        self._apply_filter(filter_text or self.search_var.get())

    def _apply_filter(self, text: str):
        """Filter the cached product list and redisplay."""
        text = text.strip().lower()
        if text:
            visible = [
                p for p in self._all_products
                if text in p["product_name"].lower()
                or text in (p["category"] or "").lower()
                or text in (p["barcode"] or "").lower()
            ]
        else:
            visible = self._all_products

        self._render_rows(visible)
        total = len(self._all_products)
        shown = len(visible)
        self.count_label.config(
            text=f"{shown} of {total} products" if text else f"{total} products"
        )

    def _render_rows(self, product_list: list[dict]):
        """Clear and repopulate the Treeview with the given product list."""
        for row in self.tree.get_children():
            self.tree.delete(row)

        _cur = get_setting("currency_symbol") or "₵"
        for p in product_list:
            qty = p["quantity"]
            if qty == 0:
                tag = "out_stock"
            elif qty <= 5:
                tag = "low_stock"
            else:
                tag = ""

            self.tree.insert("", "end", values=(
                p["product_id"],
                p["product_name"],
                p["category"],
                f"{_cur}{p['price']:.2f}",
                qty,
                p["barcode"] or "—",
            ), tags=(tag,))

    def _on_search_change(self, *_):
        """Called every time the search box changes."""
        self._apply_filter(self.search_var.get())

    # ── Sorting ───────────────────────────────────────────────────────────────

    def _sort_by(self, col: str):
        """Sort the table by the clicked column header."""
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True

        key_map = {
            "id":       lambda p: p["product_id"],
            "name":     lambda p: p["product_name"].lower(),
            "category": lambda p: (p["category"] or "").lower(),
            "price":    lambda p: p["price"],
            "quantity": lambda p: p["quantity"],
            "barcode":  lambda p: (p["barcode"] or "").lower(),
        }
        self._all_products.sort(key=key_map.get(col, lambda p: p["product_name"]),
                                reverse=not self._sort_asc)
        self._apply_filter(self.search_var.get())

    # ── Selection helper ──────────────────────────────────────────────────────

    def _get_selected_product(self) -> dict | None:
        """Return the product dict for the selected row, or None."""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select a product first.")
            return None
        values = self.tree.item(selected[0])["values"]
        return product_mod.get_product_by_id(values[0])

    # ── CRUD actions ──────────────────────────────────────────────────────────

    def _open_add_dialog(self):
        AddEditProductDialog(
            self.parent, title="Add New Product",
            product=None, on_success=self._load_products
        )

    def _open_edit_dialog(self):
        product = self._get_selected_product()
        if not product:
            return
        AddEditProductDialog(
            self.parent, title="Edit Product",
            product=product, on_success=self._load_products
        )

    def _delete_selected(self):
        product = self._get_selected_product()
        if not product:
            return

        confirm = messagebox.askyesno(
            "Delete Product",
            f"Delete '{product['product_name']}'?\n\nThis cannot be undone."
        )
        if not confirm:
            return

        ok, msg = product_mod.delete_product(product["product_id"])
        if ok:
            messagebox.showinfo("Deleted", msg)
            self._load_products()
        else:
            messagebox.showerror("Error", msg)


# ── Add / Edit Dialog ─────────────────────────────────────────────────────────

class AddEditProductDialog(tk.Toplevel):
    """
    Reusable dialog for both adding and editing a product.
    Pass product=None for add mode, or a product dict for edit mode.
    """

    def __init__(self, parent, title: str, product: dict | None, on_success):
        super().__init__(parent)
        self.product = product          # None → add mode
        self.on_success = on_success
        self.is_edit = product is not None

        self.title(title)
        self.geometry("420x460")
        self.configure(bg=COLORS["bg"])
        self.resizable(False, False)
        self.grab_set()                 # modal
        self._build()
        if self.is_edit:
            self._populate(product)

    def _build(self):
        tk.Label(
            self, text=self.title(),
            font=("Segoe UI", 14, "bold"),
            bg=COLORS["bg"], fg=COLORS["white"]
        ).pack(pady=(20, 4))

        form = tk.Frame(self, bg=COLORS["bg"], padx=30)
        form.pack(fill="x")

        self.name_var     = tk.StringVar()
        self.category_var = tk.StringVar()
        self.price_var    = tk.StringVar()
        self.qty_var      = tk.StringVar()
        self.barcode_var  = tk.StringVar()

        # Product Name
        self._field(form, "Product Name *", self.name_var)

        # Category (combobox with known categories)
        tk.Label(form, text="Category *", font=("Segoe UI", 9),
                 bg=COLORS["bg"], fg=COLORS["muted"]).pack(anchor="w", pady=(10, 2))
        categories = product_mod.get_categories()
        self.cat_combo = ttk.Combobox(
            form, textvariable=self.category_var,
            values=categories, font=("Segoe UI", 11),
            state="normal"
        )
        self._style_combo()
        self.cat_combo.pack(fill="x")

        # Price and Quantity side by side
        row2 = tk.Frame(form, bg=COLORS["bg"])
        row2.pack(fill="x", pady=(10, 0))

        left2 = tk.Frame(row2, bg=COLORS["bg"])
        left2.pack(side="left", fill="x", expand=True, padx=(0, 8))
        _cur = get_setting("currency_symbol") or "₵"
        tk.Label(left2, text=f"Price ({_cur}) *", font=("Segoe UI", 9),
                 bg=COLORS["bg"], fg=COLORS["muted"]).pack(anchor="w", pady=(0, 2))
        tk.Entry(left2, textvariable=self.price_var,
                 font=("Segoe UI", 11), bg=COLORS["accent"],
                 fg=COLORS["white"], insertbackground=COLORS["white"],
                 relief="flat", bd=6).pack(fill="x")

        right2 = tk.Frame(row2, bg=COLORS["bg"])
        right2.pack(side="left", fill="x", expand=True)
        tk.Label(right2, text="Stock Quantity *", font=("Segoe UI", 9),
                 bg=COLORS["bg"], fg=COLORS["muted"]).pack(anchor="w", pady=(0, 2))
        tk.Entry(right2, textvariable=self.qty_var,
                 font=("Segoe UI", 11), bg=COLORS["accent"],
                 fg=COLORS["white"], insertbackground=COLORS["white"],
                 relief="flat", bd=6).pack(fill="x")

        # Barcode
        self._field(form, "Barcode (optional)", self.barcode_var)

        # Error label
        self.error_var = tk.StringVar()
        tk.Label(form, textvariable=self.error_var,
                 font=("Segoe UI", 9), bg=COLORS["bg"], fg=COLORS["error"],
                 wraplength=340).pack(pady=(8, 0))

        # Save button
        label = "Save Changes" if self.is_edit else "Add Product"
        tk.Button(
            form, text=label,
            font=("Segoe UI", 11, "bold"),
            bg=COLORS["button"], fg=COLORS["white"],
            activebackground=COLORS["button_hover"],
            relief="flat", bd=0, pady=10,
            cursor="hand2", command=self._submit
        ).pack(fill="x", pady=(14, 0))

    def _field(self, parent, label: str, var: tk.StringVar):
        tk.Label(parent, text=label, font=("Segoe UI", 9),
                 bg=COLORS["bg"], fg=COLORS["muted"]).pack(anchor="w", pady=(10, 2))
        tk.Entry(parent, textvariable=var,
                 font=("Segoe UI", 11), bg=COLORS["accent"],
                 fg=COLORS["white"], insertbackground=COLORS["white"],
                 relief="flat", bd=6).pack(fill="x")

    def _style_combo(self):
        style = ttk.Style()
        style.theme_use("default")
        style.configure("TCombobox",
            fieldbackground=COLORS["accent"],
            background=COLORS["accent"],
            foreground=COLORS["white"],
            selectbackground=COLORS["button"],
            selectforeground=COLORS["white"],
            font=("Segoe UI", 11)
        )

    def _populate(self, product: dict):
        """Pre-fill form fields when editing."""
        self.name_var.set(product["product_name"])
        self.category_var.set(product["category"])
        self.price_var.set(str(product["price"]))
        self.qty_var.set(str(product["quantity"]))
        self.barcode_var.set(product["barcode"] or "")

    def _submit(self):
        name     = self.name_var.get()
        category = self.category_var.get()
        price    = self.price_var.get()
        qty      = self.qty_var.get()
        barcode  = self.barcode_var.get()

        if self.is_edit:
            ok, msg = product_mod.update_product(
                self.product["product_id"], name, category, price, qty, barcode
            )
        else:
            ok, msg = product_mod.add_product(name, category, price, qty, barcode)

        if ok:
            self.on_success()
            self.destroy()
            messagebox.showinfo("Success", msg)
        else:
            self.error_var.set(msg)
