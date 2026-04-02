"""
Payment Dialog — full tabbed UI.
Four tabs: Cash | Mobile Money | Card | Split
Persists the sale and payment records, then triggers the receipt.

Ghana-localised: MTN MoMo, Telecel Cash, AT Money (AirtelTigo).
Currency and tax rate are read from the Settings table at runtime.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ui.login_screen import COLORS
from modules import auth, sales as sales_mod, payments as payments_mod
from database.db_setup import get_setting


class PaymentDialog(tk.Toplevel):
    """
    Modal payment dialog.

    Parameters
    ----------
    parent     : parent widget
    totals     : {subtotal, discount, tax, total}
    cart       : list of cart item dicts
    customer   : customer dict or None (walk-in)
    tax_rate   : float — passed from cashier screen (read from Settings there)
    on_success : callback(sale_id) called after successful payment
    """

    QUICK_AMOUNTS  = [5, 10, 20, 50, 100, 200]
    MOBILE_PROVIDERS = [
        "MTN MoMo",
        "Telecel Cash",
        "AT Money (AirtelTigo)",
        "Other",
    ]
    CARD_TYPES = ["Visa", "Mastercard", "Verve", "Other"]

    def __init__(self, parent, totals: dict, cart: list,
                 customer, on_success, tax_rate: float = 0.16):
        super().__init__(parent)
        self.totals     = dict(totals)   # mutable local copy
        self.cart       = cart
        self.customer   = customer
        self.on_success = on_success
        self._tax_rate  = tax_rate
        self._sale_id   = None

        # Runtime currency symbol
        try:
            self._cur = get_setting("currency_symbol") or "₵"
        except Exception:
            self._cur = "₵"

        # Loyalty-redemption state (zero until cashier clicks Redeem)
        self._pts_discount = 0.0
        self._pts_redeemed = 0

        self.title("Checkout \u2014 Collect Payment")
        self.geometry("480x640")
        self.configure(bg=COLORS["bg"])
        self.resizable(False, False)
        self.grab_set()
        self.bind("<Escape>", lambda e: self._cancel())
        self._build()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        self._build_summary()
        self._build_tabs()

        bottom = tk.Frame(self, bg=COLORS["bg"], padx=28)
        bottom.pack(fill="x", side="bottom", pady=(0, 20))

        self.error_var = tk.StringVar()
        tk.Label(bottom, textvariable=self.error_var,
                 font=("Segoe UI", 9),
                 bg=COLORS["bg"], fg=COLORS["error"],
                 wraplength=420).pack(pady=(0, 8))

        tk.Button(bottom, text="CONFIRM PAYMENT",
                  font=("Segoe UI", 13, "bold"),
                  bg=COLORS["button"], fg=COLORS["white"],
                  activebackground=COLORS["button_hover"],
                  relief="flat", bd=0, pady=14,
                  cursor="hand2", command=self._confirm).pack(fill="x")

        tk.Button(bottom, text="Cancel",
                  font=("Segoe UI", 9),
                  bg=COLORS["panel"], fg=COLORS["muted"],
                  activebackground=COLORS["accent"],
                  relief="flat", bd=0, pady=6,
                  cursor="hand2", command=self._cancel).pack(fill="x", pady=(6, 0))

    def _build_summary(self):
        """Compact order summary with loyalty-redemption button."""
        strip = tk.Frame(self, bg=COLORS["panel"])
        strip.pack(fill="x", padx=28, pady=(20, 12))

        inner = tk.Frame(strip, bg=COLORS["panel"], padx=16, pady=10)
        inner.pack(fill="x")

        left = tk.Frame(inner, bg=COLORS["panel"])
        left.pack(side="left", fill="x", expand=True)

        cur = self._cur
        for label, value in [
            ("Subtotal", f"{cur}{self.totals['subtotal']:.2f}"),
            ("Discount", f"-{cur}{self.totals['discount']:.2f}"),
            ("Tax",      f"{cur}{self.totals['tax']:.2f}"),
        ]:
            row = tk.Frame(left, bg=COLORS["panel"])
            row.pack(fill="x", pady=1)
            tk.Label(row, text=label, font=("Segoe UI", 9),
                     bg=COLORS["panel"], fg=COLORS["muted"]).pack(side="left")
            tk.Label(row, text=value, font=("Segoe UI", 9),
                     bg=COLORS["panel"], fg=COLORS["text"]).pack(side="right")

        right = tk.Frame(inner, bg=COLORS["panel"], padx=16)
        right.pack(side="right")
        tk.Label(right, text="TOTAL",
                 font=("Segoe UI", 9, "bold"),
                 bg=COLORS["panel"], fg=COLORS["muted"]).pack()
        self._total_lbl = tk.Label(
            right, text=f"{cur}{self.totals['total']:.2f}",
            font=("Segoe UI", 20, "bold"),
            bg=COLORS["panel"], fg=COLORS["button"]
        )
        self._total_lbl.pack()

        # Customer row + optional Redeem Points button
        if self.customer:
            pts = self.customer.get("loyalty_points", 0)
            cust_row = tk.Frame(strip, bg=COLORS["panel"])
            cust_row.pack(fill="x", padx=16, pady=(0, 4))
            tk.Label(cust_row,
                     text=f"Customer: {self.customer['name']}  |  Points: {pts}",
                     font=("Segoe UI", 8),
                     bg=COLORS["panel"], fg=COLORS["success"]).pack(side="left")
            if pts > 0:
                tk.Button(cust_row, text="Redeem Points",
                          font=("Segoe UI", 8),
                          bg=COLORS["accent"], fg=COLORS["white"],
                          relief="flat", bd=0, padx=8, pady=2,
                          cursor="hand2",
                          command=self._redeem_points).pack(side="right")

        # Redemption confirmation label (hidden until points redeemed)
        self._pts_lbl = tk.Label(strip, text="",
                                  font=("Segoe UI", 8, "italic"),
                                  bg=COLORS["panel"], fg=COLORS["success"])
        self._pts_lbl.pack(padx=16, anchor="w", pady=(0, 4))

    def _build_tabs(self):
        """Four-tab payment method selector."""
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Pay.TNotebook",
                         background=COLORS["bg"], borderwidth=0)
        style.configure("Pay.TNotebook.Tab",
                         background=COLORS["panel"],
                         foreground=COLORS["text"],
                         font=("Segoe UI", 9, "bold"),
                         padding=[10, 8])
        style.map("Pay.TNotebook.Tab",
                  background=[("selected", COLORS["accent"])],
                  foreground=[("selected", COLORS["white"])])

        self.notebook = ttk.Notebook(self, style="Pay.TNotebook")
        self.notebook.pack(fill="both", expand=True, padx=28, pady=(0, 8))

        self.cash_tab   = tk.Frame(self.notebook, bg=COLORS["bg"])
        self.mobile_tab = tk.Frame(self.notebook, bg=COLORS["bg"])
        self.card_tab   = tk.Frame(self.notebook, bg=COLORS["bg"])
        self.split_tab  = tk.Frame(self.notebook, bg=COLORS["bg"])

        self.notebook.add(self.cash_tab,   text="  Cash  ")
        self.notebook.add(self.mobile_tab, text="  Mobile Money  ")
        self.notebook.add(self.card_tab,   text="  Card  ")
        self.notebook.add(self.split_tab,  text="  Split  ")

        self._build_cash_tab()
        self._build_mobile_tab()
        self._build_card_tab()
        self._build_split_tab()

        self.after(50, self.tendered_entry.focus_set)

    # ── Cash tab ──────────────────────────────────────────────────────────────

    def _build_cash_tab(self):
        f = tk.Frame(self.cash_tab, bg=COLORS["bg"], padx=16, pady=12)
        f.pack(fill="both", expand=True)

        cur = self._cur
        tk.Label(f, text=f"Amount Tendered ({cur})",
                 font=("Segoe UI", 9),
                 bg=COLORS["bg"], fg=COLORS["muted"]).pack(anchor="w", pady=(0, 2))

        self.tendered_var = tk.StringVar()
        self.tendered_entry = tk.Entry(
            f, textvariable=self.tendered_var,
            font=("Segoe UI", 16),
            bg=COLORS["accent"], fg=COLORS["white"],
            insertbackground=COLORS["white"],
            relief="flat", bd=8, justify="right"
        )
        self.tendered_entry.pack(fill="x")
        self.tendered_entry.bind("<KeyRelease>", lambda e: self._update_change())
        self.tendered_entry.bind("<Return>",     lambda e: self._confirm())

        tk.Label(f, text="Quick amounts",
                 font=("Segoe UI", 8),
                 bg=COLORS["bg"], fg=COLORS["muted"]).pack(anchor="w", pady=(10, 4))

        row1 = tk.Frame(f, bg=COLORS["bg"])
        row1.pack(fill="x")
        row2 = tk.Frame(f, bg=COLORS["bg"])
        row2.pack(fill="x", pady=(4, 0))

        for i, amt in enumerate(self.QUICK_AMOUNTS):
            parent_row = row1 if i < 3 else row2
            tk.Button(
                parent_row, text=f"{cur}{amt}",
                font=("Segoe UI", 10, "bold"),
                bg=COLORS["accent"], fg=COLORS["white"],
                activebackground=COLORS["button"],
                relief="flat", bd=0, pady=7, padx=10,
                cursor="hand2",
                command=lambda a=amt: self._set_tendered(a)
            ).pack(side="left", padx=(0, 6), fill="x", expand=True)

        exact_row = tk.Frame(f, bg=COLORS["bg"])
        exact_row.pack(fill="x", pady=(6, 0))
        tk.Button(exact_row,
                  text=f"Exact  ({cur}{self.totals['total']:.2f})",
                  font=("Segoe UI", 9),
                  bg=COLORS["panel"], fg=COLORS["white"],
                  activebackground=COLORS["accent"],
                  relief="flat", bd=0, pady=6,
                  cursor="hand2",
                  command=lambda: self._set_tendered(self.totals["total"])
                  ).pack(fill="x")

        change_row = tk.Frame(f, bg=COLORS["bg"])
        change_row.pack(fill="x", pady=(14, 0))
        tk.Label(change_row, text="Change Due:",
                 font=("Segoe UI", 12),
                 bg=COLORS["bg"], fg=COLORS["text"]).pack(side="left")

        self.change_var   = tk.StringVar(value=f"{cur}0.00")
        self.change_label = tk.Label(
            change_row, textvariable=self.change_var,
            font=("Segoe UI", 16, "bold"),
            bg=COLORS["bg"], fg=COLORS["muted"]
        )
        self.change_label.pack(side="right")

    def _set_tendered(self, amount: float):
        self.tendered_var.set(f"{amount:.2f}")
        self._update_change()
        self.tendered_entry.focus_set()

    def _update_change(self):
        cur = self._cur
        try:
            tendered = float(self.tendered_var.get() or 0)
            change   = tendered - self.totals["total"]
            if change >= 0:
                self.change_var.set(f"{cur}{change:.2f}")
                self.change_label.config(fg=COLORS["success"])
            else:
                self.change_var.set(f"-{cur}{abs(change):.2f}")
                self.change_label.config(fg=COLORS["error"])
        except ValueError:
            self.change_var.set(f"{cur}0.00")
            self.change_label.config(fg=COLORS["muted"])

    # ── Mobile Money tab ──────────────────────────────────────────────────────

    def _build_mobile_tab(self):
        f = tk.Frame(self.mobile_tab, bg=COLORS["bg"], padx=16, pady=16)
        f.pack(fill="both", expand=True)

        tk.Label(f, text="Mobile Money Provider",
                 font=("Segoe UI", 9),
                 bg=COLORS["bg"], fg=COLORS["muted"]).pack(anchor="w", pady=(0, 4))

        self.provider_var = tk.StringVar(value=self.MOBILE_PROVIDERS[0])
        for provider in self.MOBILE_PROVIDERS:
            tk.Radiobutton(
                f, text=provider, variable=self.provider_var, value=provider,
                font=("Segoe UI", 10),
                bg=COLORS["bg"], fg=COLORS["text"],
                selectcolor=COLORS["accent"],
                activebackground=COLORS["bg"],
                command=self._on_mobile_provider_changed,
            ).pack(anchor="w", pady=2)

        tk.Frame(f, bg=COLORS["accent"], height=1).pack(fill="x", pady=12)

        tk.Label(f, text="Customer Phone Number",
                 font=("Segoe UI", 9),
                 bg=COLORS["bg"], fg=COLORS["muted"]).pack(anchor="w", pady=(0, 2))
        self.mobile_phone_var = tk.StringVar()
        if self.customer and self.customer.get("phone"):
            self.mobile_phone_var.set(self.customer["phone"])
        tk.Entry(f, textvariable=self.mobile_phone_var,
                 font=("Segoe UI", 12),
                 bg=COLORS["accent"], fg=COLORS["white"],
                 insertbackground=COLORS["white"],
                 relief="flat", bd=6).pack(fill="x")

        tk.Label(f,
                 text=f"Amount to pay:  {self._cur}{self.totals['total']:.2f}",
                 font=("Segoe UI", 11, "bold"),
                 bg=COLORS["bg"], fg=COLORS["white"]).pack(anchor="w", pady=(14, 0))

        # Status area shown while waiting for customer approval
        self._momo_status_var = tk.StringVar(value="")
        self._momo_status_lbl = tk.Label(
            f, textvariable=self._momo_status_var,
            font=("Segoe UI", 9, "italic"),
            bg=COLORS["bg"], fg=COLORS["muted"],
            wraplength=380
        )
        self._momo_status_lbl.pack(anchor="w", pady=(8, 0))

        action_row = tk.Frame(f, bg=COLORS["bg"])
        action_row.pack(fill="x", pady=(8, 0))
        self._retry_verify_btn = tk.Button(
            action_row,
            text="Retry Verification",
            font=("Segoe UI", 9, "bold"),
            bg=COLORS["panel"],
            fg=COLORS["white"],
            activebackground=COLORS["accent"],
            relief="flat",
            bd=0,
            padx=10,
            pady=6,
            cursor="hand2",
            state="disabled",
            command=self._retry_momo_verification,
        )
        self._retry_verify_btn.pack(anchor="w")

        self._momo_code_row = tk.Frame(f, bg=COLORS["bg"])
        self._momo_code_row.pack(fill="x", pady=(10, 0))
        self._momo_code_label_var = tk.StringVar(value="Telecel Voucher / OTP Code")
        tk.Label(
            self._momo_code_row,
            textvariable=self._momo_code_label_var,
            font=("Segoe UI", 9),
            bg=COLORS["bg"],
            fg=COLORS["muted"],
        ).pack(anchor="w", pady=(0, 2))

        code_input_row = tk.Frame(self._momo_code_row, bg=COLORS["bg"])
        code_input_row.pack(fill="x")
        self._momo_code_var = tk.StringVar()
        tk.Entry(
            code_input_row,
            textvariable=self._momo_code_var,
            font=("Segoe UI", 11),
            bg=COLORS["accent"],
            fg=COLORS["white"],
            insertbackground=COLORS["white"],
            relief="flat",
            bd=6,
        ).pack(side="left", fill="x", expand=True)
        self._momo_submit_code_btn = tk.Button(
            code_input_row,
            text="Submit Code",
            font=("Segoe UI", 9, "bold"),
            bg=COLORS["button"],
            fg=COLORS["white"],
            activebackground=COLORS["button_hover"],
            relief="flat",
            bd=0,
            padx=10,
            pady=6,
            cursor="hand2",
            state="disabled",
            command=self._submit_momo_code,
        )
        self._momo_submit_code_btn.pack(side="left", padx=(8, 0))
        self._momo_code_row.pack_forget()

        # Pending txn tracking (used during CONFIRM flow)
        self._momo_txn_id = None
        self._momo_provider_name = ""
        self._momo_phone = ""
        self._momo_code_modal = None

        # Initial visibility follows selected provider.
        self._on_mobile_provider_changed()

    def _on_mobile_provider_changed(self):
        provider_name = (self.provider_var.get() or "").strip()
        if provider_name == "Telecel Cash":
            self._show_momo_code_entry(enable_submit=False)
        else:
            self._hide_momo_code_entry()

    def _message_requires_momo_code(self, message: str) -> bool:
        text = (message or "").strip().lower()
        if not text:
            return False
        return any(marker in text for marker in ("otp", "voucher", "verification code", "enter code", "submit code"))

    def _show_momo_code_entry(self, *, challenge_type: str = "otp", message: str = "", enable_submit: bool = True,
                              auto_popup: bool = False):
        label = "Telecel Voucher / OTP Code" if challenge_type == "otp" else "Challenge Value"
        self._momo_code_label_var.set(label)
        self._momo_code_var.set("")
        self._momo_code_row.pack(fill="x", pady=(10, 0))
        self._momo_submit_code_btn.config(state="normal" if enable_submit else "disabled")
        if message:
            self._momo_status_var.set(
                f"{self._momo_status_var.get()}\n"
                f"Enter the code in POS and click Submit Code."
            )
        if enable_submit and auto_popup:
            self._open_momo_code_modal(message)

    def _hide_momo_code_entry(self):
        self._momo_code_var.set("")
        self._momo_submit_code_btn.config(state="disabled")
        self._momo_code_row.pack_forget()
        self._close_momo_code_modal()

    def _open_momo_code_modal(self, prompt_message: str = ""):
        """Open/focus a small modal to capture OTP/voucher code quickly."""
        if self._momo_code_modal and self._momo_code_modal.winfo_exists():
            self._momo_code_modal.deiconify()
            self._momo_code_modal.lift()
            self._momo_code_modal.focus_force()
            return

        dlg = tk.Toplevel(self)
        self._momo_code_modal = dlg
        dlg.title("Enter MoMo Code")
        dlg.configure(bg=COLORS["panel"])
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()

        tk.Label(
            dlg,
            text="Customer received OTP/Voucher code",
            font=("Segoe UI", 10, "bold"),
            bg=COLORS["panel"],
            fg=COLORS["white"],
            pady=10,
            padx=16,
        ).pack(anchor="w")

        if prompt_message:
            tk.Label(
                dlg,
                text=prompt_message,
                font=("Segoe UI", 9),
                bg=COLORS["panel"],
                fg=COLORS["muted"],
                wraplength=340,
                justify="left",
                padx=16,
            ).pack(anchor="w")

        tk.Label(
            dlg,
            text="Enter code",
            font=("Segoe UI", 9),
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            padx=16,
            pady=0,
        ).pack(anchor="w", pady=(10, 2))

        code_entry = tk.Entry(
            dlg,
            textvariable=self._momo_code_var,
            font=("Segoe UI", 12),
            bg=COLORS["bg"],
            fg=COLORS["white"],
            insertbackground=COLORS["white"],
            relief="flat",
            bd=6,
            width=26,
        )
        code_entry.pack(fill="x", padx=16)
        code_entry.focus_set()
        code_entry.bind("<Return>", lambda e: self._submit_momo_code())

        btn_row = tk.Frame(dlg, bg=COLORS["panel"], padx=16, pady=12)
        btn_row.pack(fill="x")
        tk.Button(
            btn_row,
            text="Submit Code",
            command=self._submit_momo_code,
            bg=COLORS["button"],
            fg=COLORS["white"],
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=12,
            pady=6,
            cursor="hand2",
        ).pack(side="left", padx=(0, 8))
        tk.Button(
            btn_row,
            text="Close",
            command=dlg.destroy,
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=("Segoe UI", 10),
            relief="flat",
            padx=10,
            pady=6,
            cursor="hand2",
        ).pack(side="left")

        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        dlg.bind("<Destroy>", lambda e: setattr(self, "_momo_code_modal", None))

    def _close_momo_code_modal(self):
        if self._momo_code_modal and self._momo_code_modal.winfo_exists():
            self._momo_code_modal.destroy()
        self._momo_code_modal = None

    # ── Card tab ──────────────────────────────────────────────────────────────

    def _build_card_tab(self):
        f = tk.Frame(self.card_tab, bg=COLORS["bg"], padx=16, pady=16)
        f.pack(fill="both", expand=True)

        tk.Label(f, text="Card Type",
                 font=("Segoe UI", 9),
                 bg=COLORS["bg"], fg=COLORS["muted"]).pack(anchor="w", pady=(0, 6))

        self.card_type_var = tk.StringVar(value=self.CARD_TYPES[0])
        card_row = tk.Frame(f, bg=COLORS["bg"])
        card_row.pack(fill="x")
        for ct in self.CARD_TYPES:
            tk.Radiobutton(
                card_row, text=ct, variable=self.card_type_var, value=ct,
                font=("Segoe UI", 10),
                bg=COLORS["bg"], fg=COLORS["text"],
                selectcolor=COLORS["accent"],
                activebackground=COLORS["bg"]
            ).pack(side="left", padx=(0, 12))

        tk.Frame(f, bg=COLORS["accent"], height=1).pack(fill="x", pady=16)

        amount_frame = tk.Frame(f, bg=COLORS["panel"], pady=16)
        amount_frame.pack(fill="x")
        tk.Label(amount_frame, text="Charge to Card",
                 font=("Segoe UI", 11),
                 bg=COLORS["panel"], fg=COLORS["muted"]).pack()
        tk.Label(amount_frame,
                 text=f"{self._cur}{self.totals['total']:.2f}",
                 font=("Segoe UI", 24, "bold"),
                 bg=COLORS["panel"], fg=COLORS["button"]).pack()

        tk.Label(f,
                 text="Insert / tap card on reader, then\nclick CONFIRM PAYMENT.",
                 font=("Segoe UI", 10),
                 bg=COLORS["bg"], fg=COLORS["muted"],
                 justify="center").pack(pady=(20, 0))

        tk.Label(f, text="Last 4 digits (optional)",
                 font=("Segoe UI", 9),
                 bg=COLORS["bg"], fg=COLORS["muted"]).pack(anchor="w", pady=(16, 2))
        self.card_ref_var = tk.StringVar()
        tk.Entry(f, textvariable=self.card_ref_var, width=8,
                 font=("Segoe UI", 12),
                 bg=COLORS["accent"], fg=COLORS["white"],
                 insertbackground=COLORS["white"],
                 relief="flat", bd=6).pack(anchor="w")

    # ── Split Payment tab ─────────────────────────────────────────────────────

    def _build_split_tab(self):
        cur   = self._cur
        total = self.totals["total"]

        f = tk.Frame(self.split_tab, bg=COLORS["bg"], padx=16, pady=10)
        f.pack(fill="both", expand=True)

        tk.Label(f, text="Split Payment",
                 font=("Segoe UI", 11, "bold"),
                 bg=COLORS["bg"], fg=COLORS["white"]).pack(anchor="w", pady=(0, 2))
        tk.Label(f, text=f"Total due: {cur}{total:.2f}",
                 font=("Segoe UI", 9),
                 bg=COLORS["bg"], fg=COLORS["muted"]).pack(anchor="w", pady=(0, 10))

        # First payment method
        tk.Label(f, text="1st Payment Method",
                 font=("Segoe UI", 9),
                 bg=COLORS["bg"], fg=COLORS["muted"]).pack(anchor="w")

        self._split1_method = tk.StringVar(value="Cash")
        m1_row = tk.Frame(f, bg=COLORS["bg"])
        m1_row.pack(fill="x", pady=(2, 6))
        for m in ["Cash", "Mobile Money", "Card"]:
            tk.Radiobutton(m1_row, text=m, variable=self._split1_method, value=m,
                           font=("Segoe UI", 9),
                           bg=COLORS["bg"], fg=COLORS["text"],
                           selectcolor=COLORS["accent"],
                           activebackground=COLORS["bg"],
                           command=self._update_split_remaining
                           ).pack(side="left", padx=(0, 10))

        amt_row = tk.Frame(f, bg=COLORS["bg"])
        amt_row.pack(fill="x")
        tk.Label(amt_row, text=f"Amount ({cur})",
                 font=("Segoe UI", 9),
                 bg=COLORS["bg"], fg=COLORS["muted"]).pack(side="left")
        self._split1_amt = tk.StringVar()
        split1_entry = tk.Entry(amt_row, textvariable=self._split1_amt,
                                font=("Segoe UI", 12), width=12,
                                bg=COLORS["accent"], fg=COLORS["white"],
                                insertbackground=COLORS["white"],
                                relief="flat", bd=6)
        split1_entry.pack(side="right", padx=(8, 0))
        split1_entry.bind("<KeyRelease>", lambda e: self._update_split_remaining())

        # Divider
        tk.Frame(f, bg=COLORS["accent"], height=1).pack(fill="x", pady=10)

        # Second payment method
        tk.Label(f, text="2nd Payment Method (Remainder)",
                 font=("Segoe UI", 9),
                 bg=COLORS["bg"], fg=COLORS["muted"]).pack(anchor="w")

        self._split2_method = tk.StringVar(value="Mobile Money")
        m2_row = tk.Frame(f, bg=COLORS["bg"])
        m2_row.pack(fill="x", pady=(2, 6))
        for m in ["Cash", "Mobile Money", "Card"]:
            tk.Radiobutton(m2_row, text=m, variable=self._split2_method, value=m,
                           font=("Segoe UI", 9),
                           bg=COLORS["bg"], fg=COLORS["text"],
                           selectcolor=COLORS["accent"],
                           activebackground=COLORS["bg"]
                           ).pack(side="left", padx=(0, 10))

        rem_row = tk.Frame(f, bg=COLORS["bg"])
        rem_row.pack(fill="x")
        tk.Label(rem_row, text="Remaining:",
                 font=("Segoe UI", 9),
                 bg=COLORS["bg"], fg=COLORS["muted"]).pack(side="left")
        self._split_remaining_var = tk.StringVar(value=f"{cur}{total:.2f}")
        tk.Label(rem_row, textvariable=self._split_remaining_var,
                 font=("Segoe UI", 12, "bold"),
                 bg=COLORS["bg"], fg=COLORS["button"]).pack(side="right")

        # Reference for 2nd payment if Mobile/Card
        tk.Label(f, text="2nd Payment Reference (Mobile/Card)",
                 font=("Segoe UI", 9),
                 bg=COLORS["bg"], fg=COLORS["muted"]).pack(anchor="w", pady=(10, 2))
        self._split2_ref = tk.StringVar()
        tk.Entry(f, textvariable=self._split2_ref,
                 font=("Segoe UI", 11),
                 bg=COLORS["accent"], fg=COLORS["white"],
                 insertbackground=COLORS["white"],
                 relief="flat", bd=6).pack(fill="x")

    def _update_split_remaining(self):
        cur   = self._cur
        total = self.totals["total"]
        try:
            first = float(self._split1_amt.get() or 0)
            remaining = max(0.0, round(total - first, 2))
            self._split_remaining_var.set(f"{cur}{remaining:.2f}")
        except ValueError:
            self._split_remaining_var.set(f"{cur}{total:.2f}")

    # ── Loyalty Points Redemption ─────────────────────────────────────────────

    def _redeem_points(self):
        """Open a mini-dialog to redeem loyalty points as a discount."""
        if not self.customer:
            return
        pts_available = self.customer.get("loyalty_points", 0)
        if pts_available <= 0:
            messagebox.showinfo("No Points", "Customer has no loyalty points.")
            return

        cur = self._cur
        dlg = tk.Toplevel(self)
        dlg.title("Redeem Loyalty Points")
        dlg.configure(bg=COLORS["panel"])
        dlg.resizable(False, False)
        dlg.grab_set()

        tk.Label(dlg,
                 text=f"Available: {pts_available} pts  (1 pt = {cur}0.10 discount)",
                 font=("Segoe UI", 10),
                 bg=COLORS["panel"], fg=COLORS["text"],
                 pady=10, padx=20).pack()

        tk.Label(dlg, text="Points to redeem:",
                 font=("Segoe UI", 9),
                 bg=COLORS["panel"], fg=COLORS["muted"],
                 padx=20).pack(anchor="w")

        # Default: max that covers the total, capped at available
        max_useful = int(self.totals["total"] / 0.10)
        default_pts = min(pts_available, max_useful)
        pts_var = tk.IntVar(value=default_pts)
        tk.Spinbox(dlg, from_=0, to=pts_available,
                   textvariable=pts_var,
                   font=("Segoe UI", 13), width=8,
                   bg=COLORS["bg"], fg=COLORS["white"],
                   buttonbackground=COLORS["button"]).pack(padx=20, pady=6)

        disc_lbl = tk.Label(dlg, text="",
                             font=("Segoe UI", 10, "bold"),
                             bg=COLORS["panel"], fg=COLORS["success"])
        disc_lbl.pack()

        def _preview(*_):
            try:
                pts = int(pts_var.get())
                disc_lbl.config(text=f"Discount: {cur}{pts * 0.10:.2f}")
            except (ValueError, tk.TclError):
                disc_lbl.config(text="")

        pts_var.trace_add("write", _preview)
        _preview()

        def _apply():
            pts  = int(pts_var.get())
            if pts <= 0:
                dlg.destroy()
                return
            disc = round(pts * 0.10, 2)
            # Cap at current total (can't go negative)
            if disc > self.totals["total"]:
                disc = self.totals["total"]
                pts  = int(disc / 0.10)

            self._pts_discount = disc
            self._pts_redeemed = pts

            # Recalculate totals with the additional points discount
            new_discount = round(self.totals["discount"] + disc, 2)
            subtotal     = self.totals["subtotal"]
            taxable      = max(0.0, subtotal - new_discount)
            tax          = round(taxable * self._tax_rate, 2)
            new_total    = round(taxable + tax, 2)

            self.totals["discount"] = new_discount
            self.totals["tax"]      = tax
            self.totals["total"]    = new_total

            self._total_lbl.config(text=f"{cur}{new_total:.2f}")
            self._pts_lbl.config(
                text=f"\u2714 {pts} pts redeemed  \u2014  {cur}{disc:.2f} off"
            )
            dlg.destroy()
            messagebox.showinfo(
                "Points Applied",
                f"{pts} pts redeemed.\nNew total: {cur}{new_total:.2f}"
            )

        btn_row = tk.Frame(dlg, bg=COLORS["panel"])
        btn_row.pack(pady=(6, 14), padx=20, fill="x")
        tk.Button(btn_row, text="Apply", command=_apply,
                  bg=COLORS["button"], fg=COLORS["white"],
                  font=("Segoe UI", 11, "bold"),
                  relief="flat", padx=14, pady=6).pack(side="left", padx=(0, 8))
        tk.Button(btn_row, text="Cancel", command=dlg.destroy,
                  bg=COLORS["panel"], fg=COLORS["muted"],
                  font=("Segoe UI", 10),
                  relief="flat", padx=10, pady=6).pack(side="left")

    # ── Confirm routing ───────────────────────────────────────────────────────

    def _confirm(self):
        self.error_var.set("")
        tab = self.notebook.index(self.notebook.select())
        if tab == 0:
            self._confirm_cash()
        elif tab == 1:
            self._confirm_mobile()
        elif tab == 2:
            self._confirm_card()
        else:
            self._confirm_split()

    def _confirm_cash(self):
        total = self.totals["total"]
        try:
            tendered = float(self.tendered_var.get() or 0)
        except ValueError:
            self.error_var.set("Enter a valid amount tendered.")
            return
        if tendered < total:
            self.error_var.set(
                f"Insufficient. Need {self._cur}{total:.2f}, "
                f"received {self._cur}{tendered:.2f}."
            )
            return
        change = round(tendered - total, 2)
        self._process_sale("Cash", tendered, change, "")

    def _confirm_mobile(self):
        """
        Send a payment request to the customer's phone via the MoMo module,
        then wait for the provider callback (mock: ~3 s, real MTN: up to 2 min).
        """
        phone = self.mobile_phone_var.get().strip()
        if not phone:
            self.error_var.set("Customer phone number is required.")
            return

        provider_name = self.provider_var.get()

        # Create a placeholder sale_id for the MoMo transaction record.
        # The actual sale is created only after payment is confirmed.
        placeholder_sale_id = ""

        self._momo_status_var.set(
            f"\U0001f4f2 Sending payment request to {phone} via {provider_name}..."
        )
        self.error_var.set("")
        self.update_idletasks()

        from modules.momo import initiate_momo_payment, get_pending_momo_challenge

        def _on_momo_result(txn_id: str, status: str, reason: str):
            # This fires from a background thread — schedule UI update on main thread
            self.after(0, lambda: self._handle_momo_result(
                txn_id, status, reason, provider_name, phone
            ))

        ok, provider_msg, txn_id = initiate_momo_payment(
            sale_id       = placeholder_sale_id,
            phone         = phone,
            amount        = self.totals["total"],
            provider_name = provider_name,
            on_result     = _on_momo_result,
            currency      = "GHS",
        )

        if not ok:
            self._momo_status_var.set("")
            self.error_var.set(f"Failed to send request: {provider_msg}")
            return

        self._momo_txn_id = txn_id
        self._momo_provider_name = provider_name
        self._momo_phone = phone
        self._retry_verify_btn.config(state="normal")
        instruction = (provider_msg or "").strip()

        if provider_name in ("MTN MoMo", "AT Money (AirtelTigo)"):
            status_lines = [
                "\u23f3 Waiting for customer to approve on their phone...",
                "Customer must enter MoMo PIN on their own phone prompt.",
                "(Transaction will auto-complete once approved)",
            ]
        else:
            status_lines = [
                "\u23f3 Waiting for customer confirmation...",
                "For Telecel, customer may need voucher/OTP from *110#.",
                "Use the code field below if prompted.",
            ]

        if instruction:
            status_lines.insert(1, f"Provider message: {instruction}")
        self._momo_status_var.set("\n".join(status_lines))

        challenge = get_pending_momo_challenge(txn_id)
        if challenge and challenge.get("challenge_required"):
            self._show_momo_code_entry(
                challenge_type=(challenge.get("challenge_type") or "otp"),
                message=(challenge.get("message") or ""),
                enable_submit=True,
                auto_popup=True,
            )
        elif self._message_requires_momo_code(instruction):
            self._show_momo_code_entry(
                challenge_type="otp",
                message=instruction,
                enable_submit=True,
                auto_popup=True,
            )
        else:
            self._on_mobile_provider_changed()

    def _handle_momo_result(self, txn_id: str, status: str, reason: str,
                             provider_name: str, phone: str):
        """Called on the main thread when the MoMo callback fires."""
        if status == "SUCCESS":
            self._retry_verify_btn.config(state="disabled")
            self._hide_momo_code_entry()
            self._momo_status_var.set("\u2705 Payment approved!")
            self.update_idletasks()
            sale_id = self._process_sale(
                f"Mobile Money ({provider_name})",
                self.totals["total"], 0.0,
                f"MoMo-{txn_id}"
            )
            if sale_id:
                try:
                    from modules.momo import link_momo_sale
                    link_momo_sale(txn_id, sale_id)
                except Exception:
                    pass
        elif status == "FAILED":
            if self._message_requires_momo_code(reason):
                self._retry_verify_btn.config(state="normal")
                self._momo_status_var.set(
                    "\u23f3 Provider is requesting OTP/code confirmation.\n"
                    "Enter code and submit to continue."
                )
                self.error_var.set("")
                self._show_momo_code_entry(
                    challenge_type="otp",
                    message=reason,
                    enable_submit=True,
                    auto_popup=True,
                )
                return

            self._retry_verify_btn.config(state="disabled")
            self._hide_momo_code_entry()
            self._momo_status_var.set("")
            self.error_var.set(
                f"\u274c Payment failed. {reason}\n"
                "If customer got an OTP/code prompt, ensure they complete it on their phone, then try again."
            )
        else:  # EXPIRED
            self._retry_verify_btn.config(state="disabled")
            self._hide_momo_code_entry()
            self._momo_status_var.set("")
            self.error_var.set(
                "\u23f0 Payment timed out — customer did not respond. "
                "Please try again or use another payment method."
            )

    def _submit_momo_code(self):
        """Submit Telecel voucher/OTP code for the active MoMo transaction."""
        if not self._momo_txn_id:
            self.error_var.set("No active Mobile Money transaction.")
            return False

        code = "".join((self._momo_code_var.get() or "").split())
        if not code:
            self.error_var.set("Enter voucher/OTP code before submitting.")
            return False

        self.error_var.set("")
        self._momo_status_var.set("\U0001f504 Submitting voucher/OTP code...")
        self._momo_submit_code_btn.config(state="disabled")
        self.update_idletasks()

        try:
            from modules.momo import submit_momo_challenge_code

            ok, status, message = submit_momo_challenge_code(self._momo_txn_id, code)
        except Exception as e:
            self.error_var.set(f"Code submission failed: {e}")
            self._momo_submit_code_btn.config(state="normal")
            return False

        if not ok:
            self.error_var.set(message or "Code submission failed.")
            self._momo_submit_code_btn.config(state="normal")
            return False

        if status in ("SUCCESS", "FAILED", "EXPIRED"):
            self._momo_status_var.set("\u23f3 Code accepted. Finalizing transaction...")
            self._close_momo_code_modal()
            return True

        self._momo_status_var.set(
            "\u23f3 Code submitted successfully.\n"
            f"{message}\n"
            "Waiting for provider confirmation (auto-checking in background)..."
        )
        self._close_momo_code_modal()
        return True

    def _retry_momo_verification(self):
        """Manually retry verification for the current pending MoMo transaction."""
        if not self._momo_txn_id:
            self.error_var.set("No active Mobile Money transaction to verify.")
            return

        self.error_var.set("")
        self._momo_status_var.set("\U0001f504 Checking payment status with provider...")
        self.update_idletasks()

        try:
            from modules.momo import retry_verify_momo_transaction

            ok, status, message = retry_verify_momo_transaction(self._momo_txn_id)
        except Exception as e:
            self.error_var.set(f"Verification retry failed: {e}")
            return

        if not ok:
            self.error_var.set(message or "Verification retry failed.")
            return

        if status in ("SUCCESS", "FAILED", "EXPIRED"):
            # Finalization callback will run shortly via handle_payment_callback.
            self._momo_status_var.set("\u23f3 Verification received. Finalizing transaction...")
            return

        self._momo_status_var.set(
            "\u23f3 Payment still pending.\n"
            f"{message}\n"
            + (
                "For Telecel: enter voucher/OTP in POS and submit."
                if self._momo_provider_name == "Telecel Cash"
                else "Customer should complete the prompt on their phone."
            )
        )

        if self._message_requires_momo_code(message):
            self._show_momo_code_entry(
                challenge_type="otp",
                message=message,
                enable_submit=True,
                auto_popup=True,
            )

    def _confirm_card(self):
        card_type = self.card_type_var.get()
        last4     = self.card_ref_var.get().strip()
        ref       = f"****{last4}" if last4 else ""
        # Store card metadata for post-sale recording
        self._pending_card_type = card_type
        self._pending_card_last4 = last4
        self._process_sale(card_type, self.totals["total"], 0.0, ref)

    def _confirm_split(self):
        cur   = self._cur
        total = self.totals["total"]
        try:
            first_amt = float(self._split1_amt.get() or 0)
        except ValueError:
            self.error_var.set("Enter a valid first payment amount.")
            return
        if first_amt <= 0:
            self.error_var.set("First payment amount must be greater than zero.")
            return
        if first_amt >= total:
            self.error_var.set(
                f"First amount ({cur}{first_amt:.2f}) covers full total. "
                "Use the Cash/Mobile/Card tab instead."
            )
            return
        m2   = self._split2_method.get()
        ref2 = self._split2_ref.get().strip()
        if m2 in ("Mobile Money", "Card") and not ref2:
            self.error_var.set("Enter a reference for the 2nd payment.")
            return
        remaining = round(total - first_amt, 2)
        self._process_split_sale(first_amt, remaining, ref2)

    # ── Persist sale + payment(s) ─────────────────────────────────────────────

    def _process_sale(self, method: str, amount_paid: float,
                      change: float, reference: str):
        """Single-method payment: save sale, payment record, debit points."""
        user = auth.get_current_user()
        if not user:
            self.error_var.set("Session expired. Please log in again.")
            return None

        customer_id = self.customer["customer_id"] if self.customer else None

        ok, msg, sale_id = sales_mod.create_sale(
            user_id        = user["user_id"],
            cart_items     = self.cart,
            payment_method = method,
            discount       = self.totals["discount"],
            tax_rate       = self._tax_rate,
            customer_id    = customer_id,
        )
        if not ok:
            self.error_var.set(msg)
            return None

        ok_pay, pay_msg = payments_mod.record_payment(
            sale_id=sale_id,
            amount_paid=amount_paid,
            change_given=change,
            payment_type=method,
            reference=reference,
            provider=method,
            status="COMPLETED",
        )
        if not ok_pay:
            self.error_var.set(pay_msg)
            return None

        self._post_sale_actions(sale_id, customer_id, method)
        self.destroy()
        self.on_success(sale_id)
        self._show_completion(sale_id, method, amount_paid, change)
        return sale_id

    def _process_split_sale(self, first_amt: float, second_amt: float, ref2: str):
        """Two-method split payment: save sale with two payment records."""
        user = auth.get_current_user()
        if not user:
            self.error_var.set("Session expired. Please log in again.")
            return

        customer_id = self.customer["customer_id"] if self.customer else None
        m1 = self._split1_method.get()
        m2 = self._split2_method.get()
        combined_method = f"Split: {m1} + {m2}"

        ok, msg, sale_id = sales_mod.create_sale(
            user_id        = user["user_id"],
            cart_items     = self.cart,
            payment_method = combined_method,
            discount       = self.totals["discount"],
            tax_rate       = self._tax_rate,
            customer_id    = customer_id,
        )
        if not ok:
            self.error_var.set(msg)
            return

        ok_1, msg_1 = payments_mod.record_payment(
            sale_id=sale_id,
            amount_paid=first_amt,
            payment_type=m1,
            status="COMPLETED",
            provider=m1,
        )
        ok_2, msg_2 = payments_mod.record_payment(
            sale_id=sale_id,
            amount_paid=second_amt,
            payment_type=m2,
            reference=ref2,
            status="COMPLETED",
            provider=m2,
        )
        if not ok_1:
            self.error_var.set(msg_1)
            return
        if not ok_2:
            self.error_var.set(msg_2)
            return

        self._post_sale_actions(sale_id, customer_id, combined_method)
        self.destroy()
        self.on_success(sale_id)
        self._show_completion(
            sale_id, combined_method,
            first_amt + second_amt, 0.0
        )

    def _post_sale_actions(self, sale_id: str, customer_id, method: str):
        """Debit redeemed loyalty points, record card txn, kick cash drawer."""
        if self._pts_redeemed > 0 and customer_id:
            try:
                from modules.customers import redeem_loyalty_points
                redeem_loyalty_points(customer_id, self._pts_redeemed)
            except Exception:
                pass

        # Record card transaction for audit trail
        if hasattr(self, "_pending_card_type") and self._pending_card_type:
            try:
                from modules.card import process_card_payment
                process_card_payment(
                    sale_id,
                    self._pending_card_type,
                    self.totals["total"],
                    getattr(self, "_pending_card_last4", ""),
                )
            except Exception:
                pass
            self._pending_card_type = ""

        if "Cash" in method:
            self._kick_cash_drawer()

    def _kick_cash_drawer(self):
        """
        Send ESC/p cash drawer kick via the default Windows printer.
        Compatible with Epson TM-series and Star TSP thermal printers
        that have a cash drawer port (DK-2 cable).
        Silently ignored if no compatible printer is detected.
        """
        try:
            import platform
            if platform.system() != "Windows":
                return
            import win32print  # type: ignore  (requires pywin32)
            printer_name = win32print.GetDefaultPrinter()
            handle = win32print.OpenPrinter(printer_name)
            try:
                win32print.StartDocPrinter(handle, 1, ("Cash Drawer Kick", None, "RAW"))
                win32print.StartPagePrinter(handle)
                win32print.WritePrinter(handle, b"\x1b\x70\x00\x19\xfa")
                win32print.EndPagePrinter(handle)
                win32print.EndDocPrinter(handle)
            finally:
                win32print.ClosePrinter(handle)
        except Exception:
            pass   # No printer / driver not installed — fail silently

    def _show_completion(self, sale_id: str, method: str,
                         amount_paid: float, change: float):
        """Sale-complete summary then offer to view the receipt."""
        cur = self._cur
        lines = [
            f"Sale ID: {sale_id}",
            f"Method:  {method}",
            f"Paid:    {cur}{amount_paid:.2f}",
        ]
        if change > 0:
            lines.append(f"Change:  {cur}{change:.2f}")
        if self._pts_redeemed > 0:
            lines.append(f"Points:  {self._pts_redeemed} pts redeemed")
        lines.append("\nView receipt?")

        show = messagebox.askyesno("Payment Complete", "\n".join(lines))
        if show:
            try:
                from modules.receipts import generate_receipt
                from ui.receipt_window import ReceiptWindow
                receipt = generate_receipt(sale_id)
                ReceiptWindow(None, receipt)
            except Exception:
                messagebox.showinfo(
                    "Receipt",
                    f"Receipt for {sale_id} saved to /receipts/ folder."
                )

    def _cancel(self):
        """Close without processing — cart is preserved."""
        self.destroy()
