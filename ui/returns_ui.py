"""
Returns UI Panel
================
Three-phase workflow (all in one screen):
  1. Search  — enter a Sale ID to load the original sale
  2. Select  — double-click a row to set the return quantity
  3. Confirm — enter a reason and click Process Return

Accessible from the sidebar for manager and admin roles.
"""

import tkinter as tk
from tkinter import ttk, messagebox

from ui.login_screen import COLORS
from database.db_setup import get_setting
import modules.auth as auth
import modules.returns as returns
import modules.sales as sales
from modules.receipts import format_return_receipt, save_return_receipt_to_file
from modules.receipt_printer import print_return_receipt
from modules.returns import get_return_by_id


class ReturnsUI:
    def __init__(self, parent: tk.Frame):
        self.parent = parent
        self.parent.configure(bg=COLORS["bg"])

        self._sale       = None   # currently loaded sale dict
        self._returnable = []     # list of returnable item dicts
        self._qty_vars   = {}     # {sale_item_id: int}

        self._build_ui()

    # -----------------------------------------------------------------------
    # Layout
    # -----------------------------------------------------------------------

    def _build_ui(self):
        # -- Title --
        hdr = tk.Frame(self.parent, bg=COLORS["panel"], pady=10)
        hdr.pack(fill="x", padx=20, pady=(20, 0))
        tk.Label(
            hdr, text="Returns & Refunds",
            font=("Helvetica", 18, "bold"),
            bg=COLORS["panel"], fg=COLORS["white"]
        ).pack(side="left", padx=15)

        # -- Search bar --
        sf = tk.Frame(self.parent, bg=COLORS["bg"], pady=10)
        sf.pack(fill="x", padx=20, pady=10)

        tk.Label(sf, text="Sale ID:",
                 bg=COLORS["bg"], fg=COLORS["text"],
                 font=("Helvetica", 11)).pack(side="left")

        self._sid_var = tk.StringVar()
        entry = tk.Entry(
            sf, textvariable=self._sid_var,
            font=("Helvetica", 12), width=28,
            bg=COLORS["panel"], fg=COLORS["white"],
            insertbackground=COLORS["white"]
        )
        entry.pack(side="left", padx=8)
        entry.bind("<Return>", lambda _e: self._load_sale())

        tk.Button(
            sf, text="Load Sale",
            bg=COLORS["accent"], fg=COLORS["white"],
            font=("Helvetica", 10, "bold"),
            relief="flat", padx=12, pady=4, cursor="hand2",
            command=self._load_sale
        ).pack(side="left", padx=4)

        tk.Button(
            sf, text="Clear",
            bg=COLORS["button"], fg=COLORS["text"],
            font=("Helvetica", 10),
            relief="flat", padx=10, pady=4, cursor="hand2",
            command=self._clear
        ).pack(side="left")

        # -- Sale info bar --
        self._info_bar = tk.Frame(self.parent, bg=COLORS["panel"], pady=8)
        self._info_bar.pack(fill="x", padx=20)
        self._info_lbl = tk.Label(
            self._info_bar,
            text="Enter a Sale ID above to begin. Double-click a row to set return quantity.",
            bg=COLORS["panel"], fg=COLORS["muted"],
            font=("Helvetica", 10)
        )
        self._info_lbl.pack(padx=15, anchor="w")

        # -- Items table --
        tf = tk.Frame(self.parent, bg=COLORS["bg"])
        tf.pack(fill="both", expand=True, padx=20, pady=8)

        cols = ("product", "original_qty", "returned_qty",
                "returnable_qty", "unit_price", "return_qty")
        self._tree = ttk.Treeview(tf, columns=cols, show="headings", height=10)

        col_cfg = [
            ("product",        "Product",       200, "w"),
            ("original_qty",   "Bought",         70, "center"),
            ("returned_qty",   "Returned",        80, "center"),
            ("returnable_qty", "Available",       85, "center"),
            ("unit_price",     "Unit Price",      90, "center"),
            ("return_qty",     "Return Qty ✎",   110, "center"),
        ]
        for cid, label, width, anchor in col_cfg:
            self._tree.heading(cid, text=label)
            self._tree.column(cid, width=width, anchor=anchor)

        vsb = ttk.Scrollbar(tf, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self._tree.bind("<Double-1>", self._edit_return_qty)

        # -- Action bar --
        af = tk.Frame(self.parent, bg=COLORS["panel"], pady=10)
        af.pack(fill="x", padx=20, pady=(0, 20))

        tk.Label(af, text="Reason:",
                 bg=COLORS["panel"], fg=COLORS["text"],
                 font=("Helvetica", 11)).pack(side="left", padx=(15, 5))

        self._reason_var = tk.StringVar()
        tk.Entry(
            af, textvariable=self._reason_var,
            font=("Helvetica", 11), width=32,
            bg=COLORS["bg"], fg=COLORS["white"],
            insertbackground=COLORS["white"]
        ).pack(side="left", padx=5)

        self._restock_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            af, text="Restock items",
            variable=self._restock_var,
            bg=COLORS["panel"], fg=COLORS["text"],
            selectcolor=COLORS["bg"],
            activebackground=COLORS["panel"],
            font=("Helvetica", 10)
        ).pack(side="left", padx=10)

        tk.Button(
            af, text="Process Return",
            bg="#e74c3c", fg=COLORS["white"],
            font=("Helvetica", 11, "bold"),
            relief="flat", padx=16, pady=6, cursor="hand2",
            command=self._confirm_return
        ).pack(side="right", padx=15)

        self._total_lbl = tk.Label(
            af, text="Refund: $0.00",
            bg=COLORS["panel"], fg=COLORS["accent"],
            font=("Helvetica", 12, "bold")
        )
        self._total_lbl.pack(side="right", padx=10)

    # -----------------------------------------------------------------------
    # Actions
    # -----------------------------------------------------------------------

    def _load_sale(self):
        sale_id = self._sid_var.get().strip().upper()
        if not sale_id:
            messagebox.showwarning("Input Required", "Please enter a Sale ID.")
            return

        sale = sales.get_sale_by_id(sale_id)
        if not sale:
            messagebox.showerror("Not Found",
                                 f"No sale found with ID: {sale_id}")
            return

        self._sale       = sale
        self._returnable = returns.get_returnable_items(sale_id)
        self._qty_vars   = {item["sale_item_id"]: 0 for item in self._returnable}

        currency = get_setting("currency_symbol") or "₵"
        info = (
            f"  Sale: {sale['sale_id']}   |   "
            f"Date: {sale['date'][:16]}   |   "
            f"Total: {currency}{sale['total_amount']:.2f}   |   "
            f"Cashier: {sale.get('cashier_name', '—')}"
        )
        self._info_lbl.config(
            text=info, fg=COLORS["text"],
            font=("Helvetica", 10, "bold")
        )
        self._populate_table()

    def _populate_table(self):
        for row in self._tree.get_children():
            self._tree.delete(row)

        currency = get_setting("currency_symbol") or "₵"
        for item in self._returnable:
            tag = "disabled" if item["returnable_qty"] == 0 else ""
            self._tree.insert(
                "", "end",
                iid=str(item["sale_item_id"]),
                tags=(tag,),
                values=(
                    item["product_name"],
                    item["original_qty"],
                    item["returned_qty"],
                    item["returnable_qty"],
                    f"{currency}{item['price']:.2f}",
                    self._qty_vars.get(item["sale_item_id"], 0),
                )
            )
        self._tree.tag_configure("disabled", foreground="#555")
        self._update_total()

    def _edit_return_qty(self, _event):
        sel = self._tree.selection()
        if not sel:
            return
        siid = int(sel[0])
        item = next(
            (i for i in self._returnable if i["sale_item_id"] == siid), None
        )
        if not item or item["returnable_qty"] == 0:
            return

        dlg = tk.Toplevel(self.parent)
        dlg.title("Set Return Quantity")
        dlg.resizable(False, False)
        dlg.configure(bg=COLORS["panel"])
        dlg.grab_set()

        tk.Label(
            dlg,
            text=(f"Return qty for:\n{item['product_name']}\n"
                  f"(max {item['returnable_qty']})"),
            bg=COLORS["panel"], fg=COLORS["text"],
            font=("Helvetica", 11), pady=10, padx=20
        ).pack()

        qty_var = tk.IntVar(value=self._qty_vars.get(siid, 0))
        tk.Spinbox(
            dlg, from_=0, to=item["returnable_qty"],
            textvariable=qty_var,
            font=("Helvetica", 14), width=6,
            bg=COLORS["bg"], fg=COLORS["white"],
            buttonbackground=COLORS["button"]
        ).pack(pady=8)

        def _apply():
            self._qty_vars[siid] = qty_var.get()
            self._tree.set(str(siid), "return_qty", self._qty_vars[siid])
            self._update_total()
            dlg.destroy()

        tk.Button(
            dlg, text="Set", command=_apply,
            bg=COLORS["accent"], fg=COLORS["white"],
            font=("Helvetica", 11, "bold"),
            relief="flat", padx=14, pady=6
        ).pack(pady=(0, 12))

    def _update_total(self):
        currency = get_setting("currency_symbol") or "₵"
        total = sum(
            self._qty_vars.get(i["sale_item_id"], 0) * i["price"]
            for i in self._returnable
        )
        self._total_lbl.config(text=f"Refund: {currency}{total:.2f}")

    def _confirm_return(self):
        if not self._sale:
            messagebox.showwarning("No Sale Loaded",
                                   "Please load a sale first.")
            return

        reason = self._reason_var.get().strip()
        if not reason:
            messagebox.showwarning("Reason Required",
                                   "Please enter a reason for the return.")
            return

        items_to_return = [
            {
                "sale_item_id": item["sale_item_id"],
                "product_id":   item["product_id"],
                "quantity":     self._qty_vars.get(item["sale_item_id"], 0),
                "price":        item["price"],
            }
            for item in self._returnable
            if self._qty_vars.get(item["sale_item_id"], 0) > 0
        ]

        if not items_to_return:
            messagebox.showwarning(
                "No Items Selected",
                "Double-click a row to set the return quantity first."
            )
            return

        currency = get_setting("currency_symbol") or "₵"
        total    = sum(i["quantity"] * i["price"] for i in items_to_return)

        if not messagebox.askyesno(
            "Confirm Return",
            f"Process return of {len(items_to_return)} item(s) for a "
            f"refund of {currency}{total:.2f}?\n\nReason: {reason}"
        ):
            return

        user = auth.get_current_user()
        success, msg, return_id = returns.process_return(
            self._sale["sale_id"],
            items_to_return,
            reason,
            user["user_id"],
            restock=self._restock_var.get()
        )

        if not success:
            messagebox.showerror("Return Failed", msg)
            return

        receipt_text = format_return_receipt(return_id)
        if receipt_text:
            self._show_receipt_window(receipt_text, return_id)

        self._clear()
        messagebox.showinfo("Return Complete",
                            f"Return {return_id} processed successfully.")

    def _show_receipt_window(self, receipt_text: str, return_id: str):
        win = tk.Toplevel(self.parent)
        win.title(f"Return Receipt — {return_id}")
        win.configure(bg=COLORS["bg"])
        win.resizable(False, False)

        tk.Label(
            win, text="Return Receipt",
            font=("Helvetica", 14, "bold"),
            bg=COLORS["bg"], fg=COLORS["white"]
        ).pack(pady=(12, 4))

        txt = tk.Text(
            win, font=("Courier", 10),
            bg=COLORS["panel"], fg=COLORS["white"],
            width=46, height=28,
            relief="flat", padx=8, pady=8
        )
        txt.insert("1.0", receipt_text)
        txt.config(state="disabled")
        txt.pack(padx=16, pady=8)

        bf = tk.Frame(win, bg=COLORS["bg"])
        bf.pack(pady=(0, 12))

        def _print_thermal():
            ret = get_return_by_id(return_id)
            if not ret:
                messagebox.showerror("Error", "Return record not found.")
                return
            store_name  = get_setting("store_name")  or "POS Store"
            store_phone = get_setting("store_phone") or ""
            currency    = get_setting("currency_symbol") or "GH₵"
            ok, msg = print_return_receipt(ret, store_name, store_phone, currency)
            if ok:
                messagebox.showinfo("Print", msg)
            else:
                messagebox.showwarning("Print", msg)

        def _save():
            ok, path = save_return_receipt_to_file(return_id)
            if ok:
                messagebox.showinfo("Saved", f"Receipt saved:\n{path}")
            else:
                messagebox.showerror("Error", path)

        tk.Button(
            bf, text="Print Receipt", command=_print_thermal,
            bg=COLORS["accent"], fg=COLORS["white"],
            font=("Helvetica", 10, "bold"), relief="flat", padx=12, pady=5
        ).pack(side="left", padx=6)

        tk.Button(
            bf, text="Save to File", command=_save,
            bg=COLORS["button"], fg=COLORS["text"],
            font=("Helvetica", 10), relief="flat", padx=12, pady=5
        ).pack(side="left", padx=6)

        tk.Button(
            bf, text="Close", command=win.destroy,
            bg=COLORS["accent"], fg=COLORS["white"],
            font=("Helvetica", 10, "bold"), relief="flat", padx=12, pady=5
        ).pack(side="left", padx=6)

    def _clear(self):
        self._sale       = None
        self._returnable = []
        self._qty_vars   = {}
        self._sid_var.set("")
        self._reason_var.set("")
        self._restock_var.set(True)
        for row in self._tree.get_children():
            self._tree.delete(row)
        self._info_lbl.config(
            text="Enter a Sale ID above to begin. Double-click a row to set return quantity.",
            fg=COLORS["muted"], font=("Helvetica", 10)
        )
        self._total_lbl.config(text="Refund: $0.00")
