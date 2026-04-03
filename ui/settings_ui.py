"""
Settings UI — Admin only.

Displays and saves all configurable store/system settings from the Settings table.
Sections (grouped per UI Pro Max field-grouping rule):
  1. Store Information  — name, address, phone
  2. Financial          — currency symbol, tax rate
  3. Inventory          — low-stock threshold
"""

import tkinter as tk
from tkinter import messagebox
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ui.login_screen import COLORS
from database.db_setup import get_setting, update_setting


# ── Colour tokens for this screen ─────────────────────────────────────────────
_LABEL_FG    = COLORS["muted"]       # section header muted label
_INPUT_BG    = "#0d1b35"             # slightly darker than panel for input depth
_INPUT_FG    = COLORS["white"]
_BORDER      = "#1e3a5f"             # subtle separator between groups
_SUCCESS_FG  = COLORS["success"]
_ERROR_FG    = COLORS["error"]


class SettingsUI(tk.Frame):
    """Settings panel — admin dashboard content area."""

    def __init__(self, parent):
        super().__init__(parent, bg=COLORS["bg"])
        self.pack(fill="both", expand=True)
        self._entries: dict[str, tk.StringVar] = {}
        self._build()
        self._load_values()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        # ── Page header ───────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=COLORS["bg"])
        hdr.pack(fill="x", padx=32, pady=(24, 0))

        tk.Label(hdr, text="System Settings",
                 font=("Segoe UI", 18, "bold"),
                 bg=COLORS["bg"], fg=COLORS["white"]).pack(side="left")

        tk.Label(hdr,
                 text="Changes are saved immediately to the database.",
                 font=("Segoe UI", 9),
                 bg=COLORS["bg"], fg=_LABEL_FG).pack(side="left", padx=16, pady=4)

        # ── Scrollable body ───────────────────────────────────────────────
        canvas_frame = tk.Frame(self, bg=COLORS["bg"])
        canvas_frame.pack(fill="both", expand=True, padx=32, pady=16)

        canvas = tk.Canvas(canvas_frame, bg=COLORS["bg"],
                           highlightthickness=0, bd=0)
        vsb = tk.Scrollbar(canvas_frame, orient="vertical",
                            command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self._body = tk.Frame(canvas, bg=COLORS["bg"])
        window_id = canvas.create_window((0, 0), window=self._body, anchor="nw")

        def _on_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(window_id, width=canvas.winfo_width())

        self._body.bind("<Configure>", _on_configure)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(
            window_id, width=e.width))

        # ── Section groups ────────────────────────────────────────────────
        self._build_section("Store Information", [
            ("Store Name",    "store_name",
             "The name shown on receipts and the login screen."),
            ("Address",       "store_address",
             "Street address printed on every receipt."),
            ("Phone Number",  "store_phone",
             "Contact number shown on receipts."),
        ])

        self._build_divider()

        self._build_section("Financial Settings", [
            ("Currency Symbol", "currency_symbol",
           "Symbol prepended to all prices (e.g. ₵, £, KES, €)."),
            ("Tax Rate (%)",    "tax_rate",
             "Percentage applied to every sale total (e.g. 16 for 16%)."),
        ])

        self._build_divider()

        self._build_section("Inventory Thresholds", [
            ("Low Stock Threshold", "low_stock_threshold",
             "Products with stock at or below this level show a low-stock alert."),
        ])

        # ── Save button + feedback ────────────────────────────────────────
        footer = tk.Frame(self._body, bg=COLORS["bg"])
        footer.pack(fill="x", pady=(24, 8))

        self._status_var = tk.StringVar()
        self._status_lbl = tk.Label(footer, textvariable=self._status_var,
                                     font=("Segoe UI", 10),
                                     bg=COLORS["bg"], fg=_SUCCESS_FG)
        self._status_lbl.pack(side="left")

        tk.Button(footer, text="Save All Settings",
                  font=("Segoe UI", 11, "bold"),
                  bg=COLORS["accent"], fg=COLORS["white"],
                  activebackground=COLORS["button"],
                  relief="flat", padx=24, pady=10,
                  cursor="hand2",
                  command=self._save_all).pack(side="right")

    def _build_section(self, title: str, fields: list[tuple]):
        """
        Render a labelled group of settings fields.
        Each field: (display_label, settings_key, helper_text)
        UX rule: visible label ABOVE each input, helper text below.
        """
        # Section header
        sec = tk.Frame(self._body, bg=COLORS["bg"])
        sec.pack(fill="x", pady=(20, 0))

        tk.Label(sec, text=title.upper(),
                 font=("Segoe UI", 8, "bold"),
                 bg=COLORS["bg"], fg=_LABEL_FG).pack(anchor="w")

        # Card container — subtle panel background for grouping
        card = tk.Frame(self._body, bg=COLORS["panel"],
                        padx=20, pady=16)
        card.pack(fill="x", pady=(6, 0))

        for i, (label, key, helper) in enumerate(fields):
            if i:
                # Thin divider between fields inside a group
                tk.Frame(card, bg=_BORDER, height=1).pack(
                    fill="x", pady=(8, 0))

            field_row = tk.Frame(card, bg=COLORS["panel"])
            field_row.pack(fill="x", pady=(8, 0))

            # Visible label above the input (UX rule: never placeholder-only)
            tk.Label(field_row, text=label,
                     font=("Segoe UI", 9, "bold"),
                     bg=COLORS["panel"], fg=COLORS["white"]).pack(anchor="w")

            var = tk.StringVar()
            self._entries[key] = var

            entry = tk.Entry(field_row, textvariable=var,
                             font=("Segoe UI", 10),
                             bg=_INPUT_BG, fg=_INPUT_FG,
                             insertbackground=_INPUT_FG,
                             relief="flat", bd=6,
                             highlightthickness=1,
                             highlightcolor=COLORS["accent"],
                             highlightbackground=_BORDER)
            entry.pack(fill="x", pady=(4, 0))

            # Helper text below input (UX rule: persistent helper text)
            tk.Label(field_row, text=helper,
                     font=("Segoe UI", 8),
                     bg=COLORS["panel"], fg=_LABEL_FG,
                     wraplength=580, justify="left").pack(anchor="w", pady=(2, 0))

    def _build_divider(self):
        """Visible separator between section groups."""
        tk.Frame(self._body, bg=_BORDER, height=1).pack(
            fill="x", padx=4, pady=(16, 0))

    # ── Data ──────────────────────────────────────────────────────────────────

    def _load_values(self):
        """Populate all fields from the Settings table."""
        for key, var in self._entries.items():
            val = get_setting(key) or ""
            # tax_rate is stored as a decimal (0.16) — display as percentage (16)
            if key == "tax_rate":
                try:
                    val = str(round(float(val) * 100, 4)).rstrip("0").rstrip(".")
                except ValueError:
                    pass
            var.set(val)

    def _save_all(self):
        """Validate and persist every setting, then show clear feedback."""
        errors = self._validate()
        if errors:
            self._show_status("  ".join(errors), error=True)
            return

        for key, var in self._entries.items():
            value = var.get().strip()
            # Convert percentage input back to decimal for storage
            if key == "tax_rate":
                value = str(round(float(value) / 100, 6))
            update_setting(key, value)

        self._show_status("Settings saved successfully.", error=False)

    def _validate(self) -> list[str]:
        """Return a list of validation error strings (empty = valid)."""
        errors = []

        name = self._entries.get("store_name", tk.StringVar()).get().strip()
        if not name:
            errors.append("Store Name is required.")

        try:
            rate = float(self._entries.get("tax_rate",
                                           tk.StringVar()).get().strip() or "0")
            if not (0 <= rate <= 100):
                raise ValueError
        except ValueError:
            errors.append("Tax Rate must be a number between 0 and 100.")

        try:
            thresh = int(self._entries.get("low_stock_threshold",
                                           tk.StringVar()).get().strip() or "0")
            if thresh < 0:
                raise ValueError
        except ValueError:
            errors.append("Low Stock Threshold must be a positive integer.")

        return errors

    def _show_status(self, msg: str, error: bool = False):
        """Display a status message; auto-clear after 4 seconds."""
        self._status_lbl.config(fg=_ERROR_FG if error else _SUCCESS_FG)
        self._status_var.set(msg)
        self.after(4000, lambda: self._status_var.set(""))
