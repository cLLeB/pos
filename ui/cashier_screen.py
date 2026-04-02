"""
Cashier Screen — Main POS interface.
Three-panel layout: Product search | Cart | Order summary.

Keyboard shortcuts:
  F1          — Focus the search / barcode field
  F5          — Clear cart
  Delete      — Remove selected cart item
  Enter       — In search field: barcode auto-add or search
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ui.login_screen import COLORS
from modules import auth
from database.db_setup import get_setting


class CashierScreen:
    def __init__(self, root):
        self.root = root
        user = auth.get_current_user()
        self._username = user["username"] if user else "Cashier"

        # Read runtime settings (tax rate and currency) from the database
        try:
            self._tax_rate = float(get_setting("tax_rate") or "0.16")
        except (ValueError, TypeError):
            self._tax_rate = 0.16
        try:
            self._cur = get_setting("currency_symbol") or "₵"
        except Exception:
            self._cur = "₵"

        self.root.title(f"POS System — Cashier: {self._username}")
        self.root.geometry("1150x700")
        self.root.configure(bg=COLORS["bg"])
        self.root.resizable(True, True)
        self._center_window()

        # In-memory cart: list of dicts
        # {product_id, name, price, quantity, subtotal}
        self.cart: list[dict] = []

        # Currently selected customer (None = walk-in)
        self.selected_customer: dict | None = None

        # Transactions completed this session
        self._session_tx_count = 0

        self._build_ui()
        self._bind_shortcuts()
        self._start_clock()
        self._start_session_timeout()

    def _center_window(self):
        x = (self.root.winfo_screenwidth()  // 2) - (1150 // 2)
        y = (self.root.winfo_screenheight() // 2) - (700  // 2)
        self.root.geometry(f"1150x700+{x}+{y}")

    # ── Full layout ──────────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_topbar()
        body = tk.Frame(self.root, bg=COLORS["bg"])
        body.pack(fill="both", expand=True)
        self._build_left_panel(body)
        self._build_center_panel(body)
        self._build_right_panel(body)
        self._build_statusbar()

    # ── Top bar ──────────────────────────────────────────────────────────────

    def _build_topbar(self):
        bar = tk.Frame(self.root, bg=COLORS["accent"], height=48)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        tk.Label(bar, text="POS — Cashier",
                 font=("Segoe UI", 13, "bold"),
                 bg=COLORS["accent"], fg=COLORS["white"]).pack(side="left", padx=16)

        self.customer_label = tk.Label(
            bar, text="Customer: Walk-in",
            font=("Segoe UI", 10),
            bg=COLORS["accent"], fg=COLORS["white"]
        )
        self.customer_label.pack(side="left", padx=20)

        tk.Label(bar, text=f"User: {self._username}",
                 font=("Segoe UI", 10),
                 bg=COLORS["accent"], fg=COLORS["white"]).pack(side="right", padx=16)

        tk.Button(bar, text="Logout",
                  font=("Segoe UI", 9),
                  bg=COLORS["button"], fg=COLORS["white"],
                  activebackground=COLORS["button_hover"],
                  relief="flat", bd=0, padx=12, pady=4,
                  cursor="hand2", command=self._logout).pack(side="right", padx=4)

        tk.Button(bar, text="Select Customer",
                  font=("Segoe UI", 9),
                  bg=COLORS["panel"], fg=COLORS["white"],
                  activebackground=COLORS["accent"],
                  relief="flat", bd=0, padx=12, pady=4,
                  cursor="hand2", command=self._select_customer).pack(side="right", padx=4)

    # ── Left panel: barcode / search ─────────────────────────────────────────

    def _build_left_panel(self, body: tk.Frame):
        left = tk.Frame(body, bg=COLORS["panel"], width=270)
        left.pack(side="left", fill="y", padx=(8, 4), pady=8)
        left.pack_propagate(False)

        tk.Label(left, text="Product Search",
                 font=("Segoe UI", 11, "bold"),
                 bg=COLORS["panel"], fg=COLORS["white"]).pack(anchor="w", padx=14, pady=(14, 2))

        tk.Label(left,
                 text="Type barcode (Enter = instant add)\nor product name to search",
                 font=("Segoe UI", 8),
                 bg=COLORS["panel"], fg=COLORS["muted"],
                 justify="left").pack(anchor="w", padx=14)

        # ── Search / barcode input ────────────────────────────────────────
        search_row = tk.Frame(left, bg=COLORS["panel"])
        search_row.pack(fill="x", padx=12, pady=(6, 0))

        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(
            search_row, textvariable=self.search_var,
            font=("Segoe UI", 12),
            bg=COLORS["accent"], fg=COLORS["white"],
            insertbackground=COLORS["white"],
            relief="flat", bd=6
        )
        self.search_entry.pack(side="left", fill="x", expand=True)
        # Enter: try barcode first, fall back to search
        self.search_entry.bind("<Return>", lambda e: self._on_search_enter())

        tk.Button(search_row, text="Search",
                  font=("Segoe UI", 9),
                  bg=COLORS["button"], fg=COLORS["white"],
                  relief="flat", bd=0, padx=8, pady=3,
                  cursor="hand2", command=self._search_product).pack(side="left", padx=(4, 0))

        self.search_entry.focus_set()

        # ── Results listbox ───────────────────────────────────────────────
        tk.Label(left, text="Results  (double-click to add)",
                 font=("Segoe UI", 8),
                 bg=COLORS["panel"], fg=COLORS["muted"]).pack(anchor="w", padx=14, pady=(8, 2))

        results_frame = tk.Frame(left, bg=COLORS["panel"])
        results_frame.pack(fill="both", expand=True, padx=12, pady=(0, 6))

        sb = ttk.Scrollbar(results_frame, orient="vertical")
        sb.pack(side="right", fill="y")

        self.results_list = tk.Listbox(
            results_frame,
            font=("Segoe UI", 10),
            bg=COLORS["accent"], fg=COLORS["white"],
            selectbackground=COLORS["button"],
            relief="flat", bd=0,
            yscrollcommand=sb.set,
            activestyle="none"
        )
        self.results_list.pack(fill="both", expand=True)
        sb.config(command=self.results_list.yview)
        self.results_list.bind("<Double-Button-1>", lambda e: self._add_from_search())
        self.results_list.bind("<Return>",          lambda e: self._add_from_search())

        # ── Qty + Add row ─────────────────────────────────────────────────
        qty_row = tk.Frame(left, bg=COLORS["panel"])
        qty_row.pack(fill="x", padx=12, pady=(0, 12))

        tk.Label(qty_row, text="Qty:",
                 font=("Segoe UI", 10),
                 bg=COLORS["panel"], fg=COLORS["text"]).pack(side="left")

        self.qty_var = tk.IntVar(value=1)
        tk.Spinbox(qty_row, from_=1, to=999, textvariable=self.qty_var,
                   width=5, font=("Segoe UI", 10),
                   bg=COLORS["accent"], fg=COLORS["white"],
                   relief="flat", bd=4).pack(side="left", padx=6)

        tk.Button(qty_row, text="Add to Cart",
                  font=("Segoe UI", 9, "bold"),
                  bg=COLORS["button"], fg=COLORS["white"],
                  activebackground=COLORS["button_hover"],
                  relief="flat", bd=0, padx=10, pady=4,
                  cursor="hand2", command=self._add_from_search).pack(side="right")

        # Cache of last search results
        self._search_results: list[dict] = []

    # ── Center panel: cart ───────────────────────────────────────────────────

    def _build_center_panel(self, body: tk.Frame):
        center = tk.Frame(body, bg=COLORS["bg"])
        center.pack(side="left", fill="both", expand=True, padx=4, pady=8)

        header_row = tk.Frame(center, bg=COLORS["bg"])
        header_row.pack(fill="x", padx=4, pady=(6, 4))

        tk.Label(header_row, text="Shopping Cart",
                 font=("Segoe UI", 13, "bold"),
                 bg=COLORS["bg"], fg=COLORS["white"]).pack(side="left")

        tk.Label(header_row, text="Double-click item to edit quantity",
                 font=("Segoe UI", 8),
                 bg=COLORS["bg"], fg=COLORS["muted"]).pack(side="right")

        # ── Cart Treeview ─────────────────────────────────────────────────
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Cart.Treeview",
            background=COLORS["panel"], foreground=COLORS["text"],
            rowheight=34, fieldbackground=COLORS["panel"],
            font=("Segoe UI", 10))
        style.configure("Cart.Treeview.Heading",
            background=COLORS["accent"], foreground=COLORS["white"],
            font=("Segoe UI", 10, "bold"), relief="flat")
        style.map("Cart.Treeview", background=[("selected", COLORS["button"])])

        cols = ("name", "qty", "unit_price", "subtotal")
        self.cart_tree = ttk.Treeview(
            center, columns=cols, show="headings",
            style="Cart.Treeview", selectmode="browse"
        )
        self.cart_tree.heading("name",       text="Product")
        self.cart_tree.heading("qty",        text="Qty")
        self.cart_tree.heading("unit_price", text="Unit Price")
        self.cart_tree.heading("subtotal",   text="Subtotal")

        self.cart_tree.column("name",       width=280, anchor="w")
        self.cart_tree.column("qty",        width=60,  anchor="center")
        self.cart_tree.column("unit_price", width=100, anchor="e")
        self.cart_tree.column("subtotal",   width=110, anchor="e")
        self.cart_tree.pack(fill="both", expand=True, padx=4)

        # Double-click to edit quantity
        self.cart_tree.bind("<Double-Button-1>", lambda e: self._edit_cart_item_qty())

        # ── Cart actions ──────────────────────────────────────────────────
        cart_actions = tk.Frame(center, bg=COLORS["bg"])
        cart_actions.pack(fill="x", padx=4, pady=(6, 0))

        btn_cfg = dict(font=("Segoe UI", 9),
                       relief="flat", bd=0, padx=12, pady=6, cursor="hand2")

        tk.Button(cart_actions, text="Remove Item  [Del]",
                  bg=COLORS["panel"], fg=COLORS["white"],
                  activebackground=COLORS["accent"],
                  command=self._remove_cart_item, **btn_cfg).pack(side="left", padx=(0, 6))

        tk.Button(cart_actions, text="Clear Cart  [F5]",
                  bg=COLORS["button"], fg=COLORS["white"],
                  activebackground=COLORS["button_hover"],
                  command=self._clear_cart, **btn_cfg).pack(side="left")

    # ── Right panel: totals + checkout ───────────────────────────────────────

    def _build_right_panel(self, body: tk.Frame):
        right = tk.Frame(body, bg=COLORS["panel"], width=250)
        right.pack(side="left", fill="y", padx=(4, 8), pady=8)
        right.pack_propagate(False)

        tk.Label(right, text="Order Summary",
                 font=("Segoe UI", 12, "bold"),
                 bg=COLORS["panel"], fg=COLORS["white"]).pack(pady=(18, 4))

        tk.Frame(right, bg=COLORS["accent"], height=1).pack(fill="x", padx=16, pady=(0, 10))

        # Summary rows
        sf = tk.Frame(right, bg=COLORS["panel"])
        sf.pack(fill="x", padx=16)

        _z = f"{self._cur}0.00"
        self.subtotal_var = tk.StringVar(value=_z)
        self.discount_var = tk.StringVar(value=f"-{_z}")
        self.tax_var      = tk.StringVar(value=_z)
        self.total_var    = tk.StringVar(value=_z)

        self._summary_row(sf, "Subtotal:",  self.subtotal_var)
        self._summary_row(sf, "Discount:",  self.discount_var, color=COLORS["success"])
        self._summary_row(sf, "Tax (16%):", self.tax_var)

        tk.Frame(right, bg=COLORS["accent"], height=1).pack(fill="x", padx=16, pady=8)

        total_row = tk.Frame(right, bg=COLORS["panel"])
        total_row.pack(fill="x", padx=16)
        tk.Label(total_row, text="TOTAL",
                 font=("Segoe UI", 13, "bold"),
                 bg=COLORS["panel"], fg=COLORS["white"]).pack(side="left")
        tk.Label(total_row, textvariable=self.total_var,
                 font=("Segoe UI", 17, "bold"),
                 bg=COLORS["panel"], fg=COLORS["button"]).pack(side="right")

        tk.Frame(right, bg=COLORS["accent"], height=1).pack(fill="x", padx=16, pady=10)

        # Discount input
        tk.Label(right, text="Discount ($)",
                 font=("Segoe UI", 8),
                 bg=COLORS["panel"], fg=COLORS["muted"]).pack(anchor="w", padx=16)

        self.discount_input = tk.Entry(
            right, font=("Segoe UI", 11),
            bg=COLORS["accent"], fg=COLORS["white"],
            insertbackground=COLORS["white"],
            relief="flat", bd=6
        )
        self.discount_input.insert(0, "0")
        self.discount_input.pack(fill="x", padx=16, pady=(2, 14))
        self.discount_input.bind("<KeyRelease>", lambda e: self._refresh_totals())

        # Checkout
        tk.Button(right, text="CHECKOUT",
                  font=("Segoe UI", 14, "bold"),
                  bg=COLORS["button"], fg=COLORS["white"],
                  activebackground=COLORS["button_hover"],
                  relief="flat", bd=0, pady=16,
                  cursor="hand2", command=self._checkout).pack(fill="x", padx=16)

        tk.Label(right, bg=COLORS["panel"]).pack(expand=True)

        self.items_count_var = tk.StringVar(value="0 items in cart")
        tk.Label(right, textvariable=self.items_count_var,
                 font=("Segoe UI", 8),
                 bg=COLORS["panel"], fg=COLORS["muted"]).pack(pady=(0, 12))

    def _summary_row(self, parent, label: str, var: tk.StringVar, color: str = None):
        row = tk.Frame(parent, bg=COLORS["panel"])
        row.pack(fill="x", pady=3)
        tk.Label(row, text=label, font=("Segoe UI", 10),
                 bg=COLORS["panel"], fg=COLORS["text"]).pack(side="left")
        tk.Label(row, textvariable=var, font=("Segoe UI", 10, "bold"),
                 bg=COLORS["panel"], fg=color or COLORS["white"]).pack(side="right")

    # ── Status bar ────────────────────────────────────────────────────────────

    def _build_statusbar(self):
        bar = tk.Frame(self.root, bg=COLORS["panel"], height=26)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        self.clock_var = tk.StringVar()
        tk.Label(bar, textvariable=self.clock_var,
                 font=("Segoe UI", 8),
                 bg=COLORS["panel"], fg=COLORS["muted"]).pack(side="left", padx=12)

        tk.Label(bar, text=f"Cashier: {self._username}",
                 font=("Segoe UI", 8),
                 bg=COLORS["panel"], fg=COLORS["muted"]).pack(side="left", padx=12)

        self.session_var = tk.StringVar(value="Session sales: 0")
        tk.Label(bar, textvariable=self.session_var,
                 font=("Segoe UI", 8),
                 bg=COLORS["panel"], fg=COLORS["muted"]).pack(side="right", padx=12)

        tk.Label(bar, text="F1=Search  F5=Clear  Del=Remove",
                 font=("Segoe UI", 8),
                 bg=COLORS["panel"], fg=COLORS["muted"]).pack(side="right", padx=12)

    def _start_clock(self):
        """Update the clock label every second."""
        self.clock_var.set(time.strftime("  %Y-%m-%d   %H:%M:%S"))
        self.root.after(1000, self._start_clock)

    # ── Keyboard shortcuts ────────────────────────────────────────────────────

    def _bind_shortcuts(self):
        self.root.bind("<F1>",     lambda e: self.search_entry.focus_set())
        self.root.bind("<F5>",     lambda e: self._clear_cart())
        self.root.bind("<Delete>", lambda e: self._remove_cart_item())

    # ── Search & barcode logic ────────────────────────────────────────────────

    def _on_search_enter(self):
        """
        On Enter in the search field:
          1. Try to find an exact barcode match → add directly to cart.
          2. Otherwise run a name/partial search.
        """
        query = self.search_var.get().strip()
        if not query:
            return

        from modules.products import get_product_by_barcode
        product = get_product_by_barcode(query)

        if product:
            # Exact barcode hit — auto-add and clear field
            qty = self.qty_var.get()
            self._add_to_cart(product, qty)
            self.search_var.set("")
            self.results_list.delete(0, "end")
            self._search_results = []
        else:
            self._search_product()

    def _search_product(self):
        """Search by name or partial barcode and populate the results listbox."""
        query = self.search_var.get().strip()
        if not query:
            return

        from modules.products import search_product
        results = search_product(query)
        self._search_results = results

        self.results_list.delete(0, "end")
        if not results:
            self.results_list.insert("end", "  No products found")
            return

        for p in results:
            stock = p["quantity"]
            stock_tag = " [LOW]" if 0 < stock <= 5 else (" [OUT]" if stock == 0 else "")
            self.results_list.insert(
                "end",
                f"  {p['product_name']}  —  ${p['price']:.2f}  (stock: {stock}{stock_tag})"
            )

    def _add_from_search(self):
        """Add the highlighted search result to the cart."""
        selection = self.results_list.curselection()
        if not selection or not self._search_results:
            return
        idx = selection[0]
        if idx >= len(self._search_results):
            return
        product = self._search_results[idx]
        qty = self.qty_var.get()
        self._add_to_cart(product, qty)

    # ── Cart operations ───────────────────────────────────────────────────────

    def _add_to_cart(self, product: dict, qty: int):
        """Add a product to the in-memory cart and refresh the display."""
        if product["quantity"] == 0:
            messagebox.showwarning("Out of Stock",
                f"'{product['product_name']}' is out of stock.")
            return

        if product["quantity"] < qty:
            messagebox.showwarning("Low Stock",
                f"Only {product['quantity']} unit(s) available for "
                f"'{product['product_name']}'.")
            return

        # If already in cart, increase quantity
        for item in self.cart:
            if item["product_id"] == product["product_id"]:
                new_qty = item["quantity"] + qty
                if product["quantity"] < new_qty:
                    messagebox.showwarning("Low Stock",
                        f"Cannot add {qty} more — only "
                        f"{product['quantity']} in stock.")
                    return
                item["quantity"] = new_qty
                item["subtotal"] = round(item["price"] * new_qty, 2)
                self._refresh_cart_display()
                return

        self.cart.append({
            "product_id": product["product_id"],
            "name":       product["product_name"],
            "price":      product["price"],
            "quantity":   qty,
            "subtotal":   round(product["price"] * qty, 2),
        })
        self._refresh_cart_display()

    def _edit_cart_item_qty(self):
        """Double-click on a cart row to change its quantity."""
        selected = self.cart_tree.selection()
        if not selected:
            return
        idx = self.cart_tree.index(selected[0])
        item = self.cart[idx]

        new_qty = simpledialog.askinteger(
            "Edit Quantity",
            f"New quantity for '{item['name']}':\n(Current: {item['quantity']})",
            minvalue=1, maxvalue=9999
        )
        if new_qty is None:
            return

        from modules.products import get_product_by_id
        product = get_product_by_id(item["product_id"])
        if product and product["quantity"] < new_qty:
            messagebox.showwarning("Low Stock",
                f"Only {product['quantity']} unit(s) in stock.")
            return

        item["quantity"] = new_qty
        item["subtotal"] = round(item["price"] * new_qty, 2)
        self._refresh_cart_display()

    def _remove_cart_item(self):
        selected = self.cart_tree.selection()
        if not selected:
            return
        idx = self.cart_tree.index(selected[0])
        del self.cart[idx]
        self._refresh_cart_display()

    def _clear_cart(self):
        if not self.cart:
            return
        if messagebox.askyesno("Clear Cart", "Remove all items from the cart?"):
            self.cart.clear()
            self.selected_customer = None
            self.customer_label.config(text="Customer: Walk-in")
            self._refresh_cart_display()

    def _refresh_cart_display(self):
        """Redraw the cart Treeview and update totals."""
        for row in self.cart_tree.get_children():
            self.cart_tree.delete(row)

        cur = self._cur
        for item in self.cart:
            self.cart_tree.insert("", "end", values=(
                item["name"],
                item["quantity"],
                f"{cur}{item['price']:.2f}",
                f"{cur}{item['subtotal']:.2f}",
            ))

        self._refresh_totals()
        count = len(self.cart)
        self.items_count_var.set(f"{count} item{'s' if count != 1 else ''} in cart")

    def _refresh_totals(self) -> dict:
        """Recalculate subtotal / discount / tax / total and update labels."""
        from utils.helpers import calculate_total
        subtotal = sum(i["subtotal"] for i in self.cart)
        try:
            discount = float(self.discount_input.get() or 0)
        except ValueError:
            discount = 0.0
        discount = max(0.0, min(discount, subtotal))

        totals = calculate_total(subtotal, discount, tax_rate=self._tax_rate)
        cur = self._cur
        self.subtotal_var.set(f"{cur}{totals['subtotal']:.2f}")
        self.discount_var.set(f"-{cur}{totals['discount']:.2f}")
        self.tax_var.set(f"{cur}{totals['tax']:.2f}")
        self.total_var.set(f"{cur}{totals['total']:.2f}")
        return totals

    # ── Customer selection (wired fully in Day 8) ─────────────────────────────

    def _select_customer(self):
        """
        Look up or register a customer.
        Placeholder until Day 8 wires in the customer module.
        """
        try:
            from ui.customer_ui import CustomerSelectDialog
            CustomerSelectDialog(self.root, on_select=self._on_customer_selected)
        except (ImportError, AttributeError):
            messagebox.showinfo(
                "Coming Day 8",
                "Customer selection will be fully available after Day 8."
            )

    def _on_customer_selected(self, customer: dict):
        """Callback when a customer is chosen from the lookup dialog."""
        self.selected_customer = customer
        self.customer_label.config(
            text=f"Customer: {customer['name']} (pts: {customer['loyalty_points']})"
        )

    # ── Checkout (wired fully in Day 7) ──────────────────────────────────────

    def _checkout(self):
        """Open the payment dialog after optional low-stock warning."""
        if not self.cart:
            messagebox.showwarning("Empty Cart",
                "Please add items to the cart before checking out.")
            return

        # Low-stock warning: list any items near or at threshold
        try:
            from database.db_setup import get_connection as _gc
            _conn = _gc()
            _threshold = int(_conn.execute(
                "SELECT value FROM Settings WHERE key='low_stock_threshold'"
            ).fetchone()[0])
            _conn.close()
        except Exception:
            _threshold = 5

        low_items = []
        for item in self.cart:
            from modules.products import get_product_by_id
            p = get_product_by_id(item["product_id"])
            if p:
                remaining = p["quantity"] - item["quantity"]
                if remaining <= _threshold:
                    low_items.append(
                        f"  \u2022 {item['name']}: {remaining} left after sale"
                    )

        if low_items:
            warn = (
                "The following items will be low or out of stock after this sale:\n\n"
                + "\n".join(low_items)
                + "\n\nProceed to checkout?"
            )
            if not messagebox.askyesno("Low Stock Warning", warn):
                return

        totals = self._refresh_totals()

        try:
            from ui.payment_dialog import PaymentDialog
            PaymentDialog(
                self.root,
                totals=totals,
                cart=self.cart,
                customer=self.selected_customer,
                tax_rate=self._tax_rate,
                on_success=self._on_sale_complete
            )
        except (ImportError, AttributeError):
            messagebox.showinfo(
                "Error",
                f"Total: {self._cur}{totals['total']:.2f}\n\n"
                "Could not open payment dialog."
            )

    def _on_sale_complete(self, sale_id: str):
        """Called by PaymentDialog after a successful sale."""
        self._session_tx_count += 1
        self.session_var.set(f"Session sales: {self._session_tx_count}")
        self.cart.clear()
        self.selected_customer = None
        self.customer_label.config(text="Customer: Walk-in")
        self.discount_input.delete(0, "end")
        self.discount_input.insert(0, "0")
        self._refresh_cart_display()
        self.search_entry.focus_set()

    # ── Session timeout ────────────────────────────────────────────────────────

    _TIMEOUT_MS = 30 * 60 * 1000

    def _start_session_timeout(self):
        for event in ("<Motion>", "<KeyPress>", "<ButtonPress>"):
            self.root.bind_all(event, self._reset_timeout, add="+")
        self._reset_timeout()

    def _reset_timeout(self, _event=None):
        if hasattr(self, "_timeout_id"):
            self.root.after_cancel(self._timeout_id)
        self._timeout_id = self.root.after(self._TIMEOUT_MS, self._session_expired)

    def _session_expired(self):
        messagebox.showwarning(
            "Session Expired",
            "You have been logged out due to 30 minutes of inactivity.",
            parent=self.root
        )
        auth.logout()
        self.root.destroy()
        import main
        main.launch()

    # ── Logout ────────────────────────────────────────────────────────────────

    def _logout(self):
        if self.cart:
            if not messagebox.askyesno("Logout",
                    "You have items in the cart. Logout anyway?"):
                return
        auth.logout()
        self.root.destroy()
        import main
        main.launch()
