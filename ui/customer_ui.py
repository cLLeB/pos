"""
Customer Management UI  —  Admin / Manager panel.
Table with search, Add / Edit / Delete, purchase history popup,
loyalty points display and redemption.

Also exports CustomerSelectDialog used by the Cashier Screen
to link a customer to a sale.
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ui.login_screen import COLORS
from modules import customers as cust_mod
from database.db_setup import get_setting


# ══════════════════════════════════════════════════════════════════════════════
#  Main Customer Management Panel (Admin / Manager sidebar)
# ══════════════════════════════════════════════════════════════════════════════

class CustomerUI:
    def __init__(self, parent: tk.Frame):
        self.parent = parent
        self._build_ui()
        self._load_customers()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Header
        header = tk.Frame(self.parent, bg=COLORS["bg"])
        header.pack(fill="x", padx=32, pady=(24, 0))

        tk.Label(header, text="Customer Management",
                 font=("Segoe UI", 18, "bold"),
                 bg=COLORS["bg"], fg=COLORS["white"]).pack(side="left")

        tk.Button(header, text="+ Add Customer",
                  font=("Segoe UI", 10, "bold"),
                  bg=COLORS["button"], fg=COLORS["white"],
                  activebackground=COLORS["button_hover"],
                  relief="flat", bd=0, padx=14, pady=6,
                  cursor="hand2", command=self._open_add).pack(side="right")

        # Search bar
        srow = tk.Frame(self.parent, bg=COLORS["bg"])
        srow.pack(fill="x", padx=32, pady=(12, 8))

        tk.Label(srow, text="Search:",
                 font=("Segoe UI", 10),
                 bg=COLORS["bg"], fg=COLORS["muted"]).pack(side="left")

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._on_search)
        tk.Entry(srow, textvariable=self.search_var,
                 font=("Segoe UI", 11), width=32,
                 bg=COLORS["accent"], fg=COLORS["white"],
                 insertbackground=COLORS["white"],
                 relief="flat", bd=6).pack(side="left", padx=(8, 10))

        tk.Button(srow, text="Clear",
                  font=("Segoe UI", 9),
                  bg=COLORS["panel"], fg=COLORS["muted"],
                  activebackground=COLORS["accent"],
                  relief="flat", bd=0, padx=10, pady=4,
                  cursor="hand2",
                  command=lambda: self.search_var.set("")).pack(side="left")

        self.count_label = tk.Label(srow, text="",
                 font=("Segoe UI", 9),
                 bg=COLORS["bg"], fg=COLORS["muted"])
        self.count_label.pack(side="right")

        # Table
        tf = tk.Frame(self.parent, bg=COLORS["bg"])
        tf.pack(fill="both", expand=True, padx=32, pady=(0, 4))

        self._style_tree()
        sb = ttk.Scrollbar(tf, orient="vertical")
        sb.pack(side="right", fill="y")

        cols = ("id", "name", "phone", "email", "points", "address")
        self.tree = ttk.Treeview(tf, columns=cols, show="headings",
                                 yscrollcommand=sb.set, selectmode="browse")
        sb.config(command=self.tree.yview)

        col_cfg = [
            ("id",      "ID",      55,  "center"),
            ("name",    "Name",    200, "w"),
            ("phone",   "Phone",   130, "center"),
            ("email",   "Email",   190, "w"),
            ("points",  "Points",  70,  "center"),
            ("address", "Address", 180, "w"),
        ]
        for col, heading, width, anchor in col_cfg:
            self.tree.heading(col, text=heading)
            self.tree.column(col, width=width, anchor=anchor)

        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-Button-1>", lambda e: self._open_history())

        # Action buttons
        actions = tk.Frame(self.parent, bg=COLORS["bg"])
        actions.pack(fill="x", padx=32, pady=(4, 16))

        btn = dict(font=("Segoe UI", 10),
                   bg=COLORS["accent"], fg=COLORS["white"],
                   activebackground=COLORS["button"],
                   relief="flat", bd=0, padx=14, pady=6, cursor="hand2")

        tk.Button(actions, text="Edit",
                  command=self._open_edit, **btn).pack(side="left", padx=(0, 8))
        tk.Button(actions, text="Purchase History",
                  command=self._open_history, **btn).pack(side="left", padx=(0, 8))
        tk.Button(actions, text="Redeem Points",
                  command=self._redeem_points, **btn).pack(side="left", padx=(0, 8))
        tk.Button(actions, text="Delete",
                  command=self._delete_customer,
                  bg="#c0392b", activebackground="#922b21",
                  fg=COLORS["white"], font=("Segoe UI", 10),
                  relief="flat", bd=0, padx=14, pady=6,
                  cursor="hand2").pack(side="left")
        tk.Button(actions, text="Refresh",
                  command=self._load_customers, **btn).pack(side="right")

        self._all_customers: list[dict] = []

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

    # ── Data ──────────────────────────────────────────────────────────────────

    def _load_customers(self, *_):
        self._all_customers = cust_mod.get_all_customers()
        self._apply_filter(self.search_var.get() if hasattr(self, "search_var") else "")

    def _on_search(self, *_):
        self._apply_filter(self.search_var.get())

    def _apply_filter(self, text: str):
        text = text.strip().lower()
        visible = (
            [c for c in self._all_customers
             if text in c["name"].lower()
             or text in (c["phone"] or "").lower()
             or text in (c["email"] or "").lower()]
            if text else self._all_customers
        )
        for row in self.tree.get_children():
            self.tree.delete(row)
        for c in visible:
            self.tree.insert("", "end", values=(
                c["customer_id"], c["name"],
                c["phone"] or "—", c["email"] or "—",
                c["loyalty_points"], c["address"] or "—",
            ))
        total  = len(self._all_customers)
        shown  = len(visible)
        self.count_label.config(
            text=f"{shown} of {total}" if text else f"{total} customers"
        )

    def _get_selected(self) -> dict | None:
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("No Selection", "Please select a customer first.")
            return None
        return cust_mod.get_customer_by_id(self.tree.item(sel[0])["values"][0])

    # ── Actions ───────────────────────────────────────────────────────────────

    def _open_add(self):
        AddEditCustomerDialog(self.parent, customer=None,
                              on_success=self._load_customers)

    def _open_edit(self):
        c = self._get_selected()
        if c:
            AddEditCustomerDialog(self.parent, customer=c,
                                  on_success=self._load_customers)

    def _open_history(self):
        c = self._get_selected()
        if c:
            PurchaseHistoryDialog(self.parent, c)

    def _redeem_points(self):
        c = self._get_selected()
        if not c:
            return
        if c["loyalty_points"] == 0:
            messagebox.showinfo("No Points",
                f"{c['name']} has no loyalty points to redeem.")
            return
        _cur = get_setting("currency_symbol") or "₵"
        pts = simpledialog.askinteger(
            "Redeem Points",
            f"{c['name']} has {c['loyalty_points']} point(s).\n"
            f"1 point = {_cur}0.10 discount.\n\nPoints to redeem:",
            minvalue=1, maxvalue=c["loyalty_points"]
        )
        if not pts:
            return
        ok, msg, discount = cust_mod.redeem_loyalty_points(c["customer_id"], pts)
        if ok:
            messagebox.showinfo("Redeemed", msg)
            self._load_customers()
        else:
            messagebox.showerror("Error", msg)

    def _delete_customer(self):
        c = self._get_selected()
        if not c:
            return
        if not messagebox.askyesno("Delete Customer",
                f"Delete '{c['name']}'?\nThis cannot be undone."):
            return
        ok, msg = cust_mod.delete_customer(c["customer_id"])
        if ok:
            messagebox.showinfo("Deleted", msg)
            self._load_customers()
        else:
            messagebox.showerror("Cannot Delete", msg)


# ══════════════════════════════════════════════════════════════════════════════
#  Add / Edit Dialog
# ══════════════════════════════════════════════════════════════════════════════

class AddEditCustomerDialog(tk.Toplevel):
    def __init__(self, parent, customer: dict | None, on_success):
        super().__init__(parent)
        self.customer   = customer
        self.on_success = on_success
        self.is_edit    = customer is not None

        self.title("Edit Customer" if self.is_edit else "Add Customer")
        self.geometry("380x380")
        self.configure(bg=COLORS["bg"])
        self.resizable(False, False)
        self.grab_set()
        self._build()
        if self.is_edit:
            self._populate()

    def _build(self):
        tk.Label(self, text=self.title(),
                 font=("Segoe UI", 14, "bold"),
                 bg=COLORS["bg"], fg=COLORS["white"]).pack(pady=(20, 4))

        f = tk.Frame(self, bg=COLORS["bg"], padx=28)
        f.pack(fill="x")

        self.name_var    = tk.StringVar()
        self.phone_var   = tk.StringVar()
        self.email_var   = tk.StringVar()
        self.address_var = tk.StringVar()

        for label, var, required in [
            ("Full Name *",    self.name_var,    True),
            ("Phone *",        self.phone_var,   True),
            ("Email",          self.email_var,   False),
            ("Address",        self.address_var, False),
        ]:
            tk.Label(f, text=label, font=("Segoe UI", 9),
                     bg=COLORS["bg"], fg=COLORS["muted"]).pack(anchor="w", pady=(10, 2))
            tk.Entry(f, textvariable=var,
                     font=("Segoe UI", 11),
                     bg=COLORS["accent"], fg=COLORS["white"],
                     insertbackground=COLORS["white"],
                     relief="flat", bd=6).pack(fill="x")

        self.error_var = tk.StringVar()
        tk.Label(f, textvariable=self.error_var,
                 font=("Segoe UI", 9),
                 bg=COLORS["bg"], fg=COLORS["error"]).pack(pady=(8, 0))

        label = "Save Changes" if self.is_edit else "Register Customer"
        tk.Button(f, text=label,
                  font=("Segoe UI", 11, "bold"),
                  bg=COLORS["button"], fg=COLORS["white"],
                  activebackground=COLORS["button_hover"],
                  relief="flat", bd=0, pady=10,
                  cursor="hand2", command=self._submit).pack(fill="x", pady=(12, 0))

    def _populate(self):
        self.name_var.set(self.customer["name"])
        self.phone_var.set(self.customer["phone"] or "")
        self.email_var.set(self.customer["email"] or "")
        self.address_var.set(self.customer["address"] or "")

    def _submit(self):
        if self.is_edit:
            ok, msg = cust_mod.update_customer(
                self.customer["customer_id"],
                self.name_var.get(), self.phone_var.get(),
                self.email_var.get(), self.address_var.get()
            )
        else:
            ok, msg, _ = cust_mod.register_customer(
                self.name_var.get(), self.phone_var.get(),
                self.email_var.get(), self.address_var.get()
            )

        if ok:
            self.on_success()
            self.destroy()
            messagebox.showinfo("Success", msg)
        else:
            self.error_var.set(msg)


# ══════════════════════════════════════════════════════════════════════════════
#  Purchase History Dialog
# ══════════════════════════════════════════════════════════════════════════════

class PurchaseHistoryDialog(tk.Toplevel):
    def __init__(self, parent, customer: dict):
        super().__init__(parent)
        self.customer = customer
        self.title(f"Purchase History — {customer['name']}")
        self.geometry("700x500")
        self.configure(bg=COLORS["bg"])
        self.resizable(True, True)
        self.grab_set()
        self._build()

    def _build(self):
        # Header with stats
        stats = cust_mod.get_customer_stats(self.customer["customer_id"])
        _cur = get_setting("currency_symbol") or "₵"
        header = tk.Frame(self, bg=COLORS["panel"], pady=12)
        header.pack(fill="x", padx=20, pady=(16, 0))

        cards = [
            ("Total Visits",  str(stats["visits"]),                        COLORS["accent"]),
            ("Total Spend",   f"{_cur}{stats['total_spend']:.2f}",         "#27ae60"),
            ("Avg Basket",    f"{_cur}{stats['avg_basket']:.2f}",          "#8e44ad"),
            ("Loyalty Points", str(self.customer["loyalty_points"]), "#c0392b"),
        ]
        for title, value, color in cards:
            card = tk.Frame(header, bg=color, padx=14, pady=10)
            card.pack(side="left", padx=(8, 0))
            tk.Label(card, text=title, font=("Segoe UI", 8),
                     bg=color, fg=COLORS["white"]).pack(anchor="w")
            tk.Label(card, text=value, font=("Segoe UI", 16, "bold"),
                     bg=color, fg=COLORS["white"]).pack(anchor="w")

        # Sales table
        tk.Label(self, text="Transaction History",
                 font=("Segoe UI", 11, "bold"),
                 bg=COLORS["bg"], fg=COLORS["white"]).pack(anchor="w", padx=20, pady=(14, 4))

        tf = tk.Frame(self, bg=COLORS["bg"])
        tf.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        sb = ttk.Scrollbar(tf, orient="vertical")
        sb.pack(side="right", fill="y")

        cols = ("date", "items", "total", "method", "cashier")
        tree = ttk.Treeview(tf, columns=cols, show="headings",
                            yscrollcommand=sb.set, selectmode="browse")
        sb.config(command=tree.yview)

        tree.heading("date",    text="Date")
        tree.heading("items",   text="Items")
        tree.heading("total",   text="Total")
        tree.heading("method",  text="Payment")
        tree.heading("cashier", text="Cashier")

        tree.column("date",    width=160, anchor="center")
        tree.column("items",   width=220, anchor="w")
        tree.column("total",   width=90,  anchor="e")
        tree.column("method",  width=120, anchor="center")
        tree.column("cashier", width=100, anchor="center")
        tree.pack(fill="both", expand=True)

        history = cust_mod.get_purchase_history(self.customer["customer_id"])
        if not history:
            tree.insert("", "end", values=("No purchases yet.", "", "", "", ""))
        else:
            for sale in history:
                item_summary = ", ".join(
                    f"{i['product_name']} x{i['quantity']}"
                    for i in sale["items"][:2]
                )
                if len(sale["items"]) > 2:
                    item_summary += f" +{len(sale['items'])-2} more"

                tree.insert("", "end", values=(
                    sale["date"],
                    item_summary,
                    f"{_cur}{sale['total_amount']:.2f}",
                    sale["payment_method"],
                    sale["cashier"] or "—",
                ))


# ══════════════════════════════════════════════════════════════════════════════
#  Customer Select Dialog  —  used by CashierScreen
# ══════════════════════════════════════════════════════════════════════════════

class CustomerSelectDialog(tk.Toplevel):
    """
    Lightweight lookup dialog for the cashier to link a customer to a sale.
    Supports search by name or phone, inline registration of new customers,
    and loyalty point redemption before checkout.
    """

    def __init__(self, parent, on_select):
        super().__init__(parent)
        self.on_select = on_select

        self.title("Select Customer")
        self.geometry("500x460")
        self.configure(bg=COLORS["bg"])
        self.resizable(False, True)
        self.grab_set()
        self._build()
        self._load_all()

    def _build(self):
        tk.Label(self, text="Customer Lookup",
                 font=("Segoe UI", 14, "bold"),
                 bg=COLORS["bg"], fg=COLORS["white"]).pack(pady=(18, 4))

        # Search row
        srow = tk.Frame(self, bg=COLORS["bg"])
        srow.pack(fill="x", padx=20, pady=(0, 8))

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._on_search)
        search_entry = tk.Entry(srow, textvariable=self.search_var,
                 font=("Segoe UI", 11),
                 bg=COLORS["accent"], fg=COLORS["white"],
                 insertbackground=COLORS["white"],
                 relief="flat", bd=6)
        search_entry.pack(side="left", fill="x", expand=True)
        search_entry.focus_set()

        tk.Button(srow, text="New",
                  font=("Segoe UI", 9, "bold"),
                  bg=COLORS["button"], fg=COLORS["white"],
                  activebackground=COLORS["button_hover"],
                  relief="flat", bd=0, padx=10, pady=5,
                  cursor="hand2", command=self._register_new).pack(side="left", padx=(6, 0))

        # Customer listbox
        lf = tk.Frame(self, bg=COLORS["bg"])
        lf.pack(fill="both", expand=True, padx=20)

        sb = ttk.Scrollbar(lf, orient="vertical")
        sb.pack(side="right", fill="y")

        self.listbox = tk.Listbox(
            lf, font=("Segoe UI", 11),
            bg=COLORS["accent"], fg=COLORS["white"],
            selectbackground=COLORS["button"],
            relief="flat", bd=0, activestyle="none",
            yscrollcommand=sb.set
        )
        self.listbox.pack(fill="both", expand=True)
        sb.config(command=self.listbox.yview)
        self.listbox.bind("<Double-Button-1>", lambda e: self._select())
        self.listbox.bind("<Return>",          lambda e: self._select())

        # Customer detail bar
        self.detail_var = tk.StringVar(value="Select a customer to see details")
        tk.Label(self, textvariable=self.detail_var,
                 font=("Segoe UI", 9),
                 bg=COLORS["bg"], fg=COLORS["muted"],
                 wraplength=460).pack(pady=(6, 4))

        self.listbox.bind("<<ListboxSelect>>", self._on_listbox_select)

        # Buttons
        brow = tk.Frame(self, bg=COLORS["bg"])
        brow.pack(fill="x", padx=20, pady=(0, 16))

        tk.Button(brow, text="Select Customer",
                  font=("Segoe UI", 11, "bold"),
                  bg=COLORS["button"], fg=COLORS["white"],
                  activebackground=COLORS["button_hover"],
                  relief="flat", bd=0, pady=8,
                  cursor="hand2", command=self._select).pack(fill="x")

        tk.Button(brow, text="Walk-in (no customer)",
                  font=("Segoe UI", 9),
                  bg=COLORS["panel"], fg=COLORS["muted"],
                  activebackground=COLORS["accent"],
                  relief="flat", bd=0, pady=6,
                  cursor="hand2", command=self.destroy).pack(fill="x", pady=(6, 0))

        self._customers: list[dict] = []

    def _load_all(self):
        self._customers = cust_mod.get_all_customers()
        self._render(self._customers)

    def _on_search(self, *_):
        q = self.search_var.get().strip()
        filtered = cust_mod.search_customers(q) if q else cust_mod.get_all_customers()
        self._customers = filtered
        self._render(filtered)

    def _render(self, customers: list[dict]):
        self.listbox.delete(0, "end")
        for c in customers:
            pts_tag = f"  [{c['loyalty_points']} pts]" if c["loyalty_points"] > 0 else ""
            self.listbox.insert(
                "end",
                f"  {c['name']}  |  {c['phone'] or '—'}{pts_tag}"
            )

    def _on_listbox_select(self, *_):
        sel = self.listbox.curselection()
        if not sel or sel[0] >= len(self._customers):
            return
        c = self._customers[sel[0]]
        stats = cust_mod.get_customer_stats(c["customer_id"])
        _cur = get_setting("currency_symbol") or "₵"
        self.detail_var.set(
            f"{c['name']}  |  Phone: {c['phone'] or '—'}  |  "
            f"Email: {c['email'] or '—'}  |  "
            f"Visits: {stats['visits']}  |  "
            f"Total spent: {_cur}{stats['total_spend']:.2f}  |  "
            f"Points: {c['loyalty_points']}"
        )

    def _select(self):
        sel = self.listbox.curselection()
        if not sel or sel[0] >= len(self._customers):
            messagebox.showwarning("No Selection", "Please select a customer.")
            return
        customer = self._customers[sel[0]]
        self.destroy()
        self.on_select(customer)

    def _register_new(self):
        """Quick-register a new customer without leaving the cashier flow."""
        QuickRegisterDialog(self, on_success=self._on_quick_register)

    def _on_quick_register(self, customer: dict):
        self._load_all()
        # Auto-select the newly registered customer
        self.destroy()
        self.on_select(customer)


# ══════════════════════════════════════════════════════════════════════════════
#  Quick Register Dialog  (used from CustomerSelectDialog in cashier flow)
# ══════════════════════════════════════════════════════════════════════════════

class QuickRegisterDialog(tk.Toplevel):
    """Minimal registration dialog for new walk-in customers at the till."""

    def __init__(self, parent, on_success):
        super().__init__(parent)
        self.on_success = on_success
        self.title("Quick Register")
        self.geometry("340x280")
        self.configure(bg=COLORS["bg"])
        self.resizable(False, False)
        self.grab_set()
        self._build()

    def _build(self):
        tk.Label(self, text="New Customer",
                 font=("Segoe UI", 13, "bold"),
                 bg=COLORS["bg"], fg=COLORS["white"]).pack(pady=(18, 4))

        f = tk.Frame(self, bg=COLORS["bg"], padx=24)
        f.pack(fill="x")

        self.name_var  = tk.StringVar()
        self.phone_var = tk.StringVar()

        for label, var in [("Full Name *", self.name_var), ("Phone *", self.phone_var)]:
            tk.Label(f, text=label, font=("Segoe UI", 9),
                     bg=COLORS["bg"], fg=COLORS["muted"]).pack(anchor="w", pady=(10, 2))
            e = tk.Entry(f, textvariable=var,
                     font=("Segoe UI", 11),
                     bg=COLORS["accent"], fg=COLORS["white"],
                     insertbackground=COLORS["white"],
                     relief="flat", bd=6)
            e.pack(fill="x")

        self.error_var = tk.StringVar()
        tk.Label(f, textvariable=self.error_var,
                 font=("Segoe UI", 9),
                 bg=COLORS["bg"], fg=COLORS["error"]).pack(pady=(6, 0))

        tk.Button(f, text="Register & Select",
                  font=("Segoe UI", 11, "bold"),
                  bg=COLORS["button"], fg=COLORS["white"],
                  activebackground=COLORS["button_hover"],
                  relief="flat", bd=0, pady=10,
                  cursor="hand2", command=self._submit).pack(fill="x", pady=(12, 0))

    def _submit(self):
        ok, msg, cid = cust_mod.register_customer(
            self.name_var.get(), self.phone_var.get()
        )
        if ok:
            customer = cust_mod.get_customer_by_id(cid)
            self.destroy()
            self.on_success(customer)
        else:
            self.error_var.set(msg)
