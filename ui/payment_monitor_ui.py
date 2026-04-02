"""
Payment Monitor UI.
Admin/Manager dashboard panel for live payment operations visibility.

Sections:
  1) Payment summary cards
  2) Recent payments table
  3) Recent MoMo transaction table
  4) Recent webhook/provider events table
"""

import tkinter as tk
from tkinter import ttk

from ui.login_screen import COLORS
from modules import payments as payments_mod
from database.db_setup import get_setting


class PaymentMonitorUI:
    def __init__(self, parent: tk.Frame):
        self.parent = parent
        self._auto_refresh_job = None
        self._build_ui()
        self._refresh_all()

    def _build_ui(self):
        header = tk.Frame(self.parent, bg=COLORS["bg"])
        header.pack(fill="x", padx=24, pady=(20, 8))

        tk.Label(
            header,
            text="Payment Monitor",
            font=("Segoe UI", 16, "bold"),
            bg=COLORS["bg"],
            fg=COLORS["white"],
        ).pack(side="left")

        self._auto_refresh_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            header,
            text="Auto refresh (5s)",
            variable=self._auto_refresh_var,
            bg=COLORS["bg"],
            fg=COLORS["muted"],
            selectcolor=COLORS["panel"],
            activebackground=COLORS["bg"],
            command=self._schedule_auto_refresh,
            font=("Segoe UI", 9),
        ).pack(side="right", padx=(8, 0))

        tk.Button(
            header,
            text="Refresh Now",
            font=("Segoe UI", 9, "bold"),
            bg=COLORS["button"],
            fg=COLORS["white"],
            activebackground=COLORS["button_hover"],
            relief="flat",
            bd=0,
            padx=12,
            pady=6,
            cursor="hand2",
            command=self._refresh_all,
        ).pack(side="right")

        self._cards_frame = tk.Frame(self.parent, bg=COLORS["bg"])
        self._cards_frame.pack(fill="x", padx=24, pady=(0, 8))

        self._notebook = ttk.Notebook(self.parent)
        self._notebook.pack(fill="both", expand=True, padx=24, pady=(0, 16))

        self._payments_tab = tk.Frame(self._notebook, bg=COLORS["bg"])
        self._momo_tab = tk.Frame(self._notebook, bg=COLORS["bg"])
        self._events_tab = tk.Frame(self._notebook, bg=COLORS["bg"])

        self._notebook.add(self._payments_tab, text="Recent Payments")
        self._notebook.add(self._momo_tab, text="MoMo Transactions")
        self._notebook.add(self._events_tab, text="Webhook Events")

        self._payments_tree = self._build_tree(
            self._payments_tab,
            columns=("sale", "amount", "type", "status", "provider", "reference", "when"),
            headings={
                "sale": "Sale ID",
                "amount": "Amount",
                "type": "Payment Type",
                "status": "Status",
                "provider": "Provider",
                "reference": "Reference",
                "when": "When",
            },
            widths={
                "sale": 120,
                "amount": 90,
                "type": 220,
                "status": 90,
                "provider": 120,
                "reference": 180,
                "when": 145,
            },
        )

        self._momo_tree = self._build_tree(
            self._momo_tab,
            columns=("txn", "provider", "phone", "amount", "status", "ref", "updated", "reason"),
            headings={
                "txn": "Txn ID",
                "provider": "Provider",
                "phone": "Phone",
                "amount": "Amount",
                "status": "Status",
                "ref": "Reference",
                "updated": "Updated",
                "reason": "Failure Reason",
            },
            widths={
                "txn": 110,
                "provider": 130,
                "phone": 120,
                "amount": 90,
                "status": 90,
                "ref": 170,
                "updated": 145,
                "reason": 260,
            },
        )

        self._events_tree = self._build_tree(
            self._events_tab,
            columns=("time", "source", "event", "status", "ref", "payload"),
            headings={
                "time": "Received",
                "source": "Source",
                "event": "Event Type",
                "status": "Process Status",
                "ref": "Reference",
                "payload": "Payload Preview",
            },
            widths={
                "time": 145,
                "source": 90,
                "event": 170,
                "status": 120,
                "ref": 140,
                "payload": 520,
            },
        )

        self.parent.bind("<Destroy>", self._on_destroy, add="+")
        self._schedule_auto_refresh()

    def _build_tree(self, parent: tk.Frame, *, columns, headings, widths):
        container = tk.Frame(parent, bg=COLORS["bg"])
        container.pack(fill="both", expand=True, padx=4, pady=4)

        tree = ttk.Treeview(container, columns=columns, show="headings", selectmode="browse")
        vsb = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(container, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        for col in columns:
            tree.heading(col, text=headings[col])
            tree.column(col, width=widths[col], anchor="w")

        tree.tag_configure("success", foreground=COLORS["success"])
        tree.tag_configure("failed", foreground=COLORS["error"])
        tree.tag_configure("pending", foreground="#F59E0B")

        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        tree.pack(fill="both", expand=True)
        return tree

    def _refresh_all(self):
        self._render_cards()
        self._render_recent_payments()
        self._render_recent_momo()
        self._render_recent_events()

    def _render_cards(self):
        for w in self._cards_frame.winfo_children():
            w.destroy()

        payments = payments_mod.get_recent_payments(250)
        momo = payments_mod.get_recent_momo_transactions(250)
        events = payments_mod.get_recent_payment_events(250)

        cur = get_setting("currency_symbol") or "₵"
        total_value = sum((p.get("amount_paid") or 0.0) for p in payments)
        completed = sum(1 for p in payments if (p.get("payment_status") or "").upper() == "COMPLETED")
        failed = sum(1 for p in payments if (p.get("payment_status") or "").upper() == "FAILED")
        pending_momo = sum(1 for m in momo if (m.get("status") or "").upper() == "PENDING")

        cards = [
            ("Payments (sample)", str(len(payments)), COLORS["accent"]),
            ("Completed", str(completed), COLORS["success"]),
            ("Failed", str(failed), COLORS["error"]),
            ("MoMo Pending", str(pending_momo), "#F59E0B"),
            ("Events Logged", str(len(events)), COLORS["button"]),
            ("Collected (sample)", f"{cur}{total_value:,.2f}", "#8e44ad"),
        ]

        for title, value, color in cards:
            card = tk.Frame(self._cards_frame, bg=color, padx=14, pady=10)
            card.pack(side="left", padx=(0, 10), pady=(0, 4))
            tk.Label(card, text=title, bg=color, fg=COLORS["white"], font=("Segoe UI", 8)).pack(anchor="w")
            tk.Label(card, text=value, bg=color, fg=COLORS["white"], font=("Segoe UI", 14, "bold")).pack(anchor="w")

    def _render_recent_payments(self):
        for row in self._payments_tree.get_children():
            self._payments_tree.delete(row)

        cur = get_setting("currency_symbol") or "₵"
        for p in payments_mod.get_recent_payments(120):
            status = (p.get("payment_status") or "").upper()
            tag = "success" if status == "COMPLETED" else ("failed" if status == "FAILED" else "pending")
            when = p.get("paid_at") or p.get("sale_date") or ""
            self._payments_tree.insert(
                "",
                "end",
                values=(
                    p.get("sale_id") or "",
                    f"{cur}{(p.get('amount_paid') or 0.0):.2f}",
                    p.get("payment_type") or "",
                    status,
                    p.get("provider") or "",
                    p.get("external_reference") or "",
                    when,
                ),
                tags=(tag,),
            )

    def _render_recent_momo(self):
        for row in self._momo_tree.get_children():
            self._momo_tree.delete(row)

        cur = get_setting("currency_symbol") or "₵"
        for m in payments_mod.get_recent_momo_transactions(120):
            status = (m.get("status") or "").upper()
            tag = "success" if status == "SUCCESS" else ("failed" if status in ("FAILED", "EXPIRED") else "pending")
            self._momo_tree.insert(
                "",
                "end",
                values=(
                    m.get("txn_id") or "",
                    m.get("provider") or "",
                    m.get("phone") or "",
                    f"{cur}{(m.get('amount') or 0.0):.2f}",
                    status,
                    m.get("reference") or "",
                    m.get("updated_at") or m.get("created_at") or "",
                    m.get("failure_reason") or "",
                ),
                tags=(tag,),
            )

    def _render_recent_events(self):
        for row in self._events_tree.get_children():
            self._events_tree.delete(row)

        for e in payments_mod.get_recent_payment_events(180):
            status = (e.get("event_status") or "").lower()
            tag = "success" if status == "processed" else ("failed" if status == "ignored" else "pending")
            self._events_tree.insert(
                "",
                "end",
                values=(
                    e.get("received_at") or "",
                    e.get("source") or "",
                    e.get("event_type") or "",
                    e.get("event_status") or "",
                    e.get("payment_ref") or "",
                    (e.get("payload_json") or "")[:240],
                ),
                tags=(tag,),
            )

    def _schedule_auto_refresh(self):
        if self._auto_refresh_job:
            try:
                self.parent.after_cancel(self._auto_refresh_job)
            except Exception:
                pass
            self._auto_refresh_job = None

        if self._auto_refresh_var.get():
            self._auto_refresh_job = self.parent.after(5000, self._auto_refresh_tick)

    def _auto_refresh_tick(self):
        try:
            self._refresh_all()
        finally:
            if self._auto_refresh_var.get():
                self._auto_refresh_job = self.parent.after(5000, self._auto_refresh_tick)

    def _on_destroy(self, _event=None):
        if self._auto_refresh_job:
            try:
                self.parent.after_cancel(self._auto_refresh_job)
            except Exception:
                pass
            self._auto_refresh_job = None
