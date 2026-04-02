"""
Receipt Window.
Displays a formatted receipt in a scrollable text widget after every sale.
Buttons: Print, Save to File, Close.
"""

import tkinter as tk
from tkinter import messagebox
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ui.login_screen import COLORS
from modules.receipts import (
    generate_receipt, format_receipt_text,
    save_receipt_to_file
)
from modules.receipt_printer import print_sale_receipt


class ReceiptWindow(tk.Toplevel):
    """
    Standalone receipt viewer.

    Parameters
    ----------
    parent   : parent widget (may be None when opened from payment dialog)
    receipt  : pre-built receipt dict from generate_receipt()
               OR a sale_id string — the window will call generate_receipt() itself
    """

    def __init__(self, parent, receipt):
        super().__init__(parent)

        # Accept either a dict or a sale_id string
        if isinstance(receipt, str):
            self._data = generate_receipt(receipt)
        else:
            self._data = receipt

        if not self._data:
            messagebox.showerror("Error", "Receipt data not found.")
            self.destroy()
            return

        self.title(f"Receipt — {self._data['sale_id']}")
        self.geometry("440x600")
        self.configure(bg=COLORS["bg"])
        self.resizable(False, True)
        if parent:
            self.grab_set()

        self._build()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        # ── Top bar ───────────────────────────────────────────────────────
        topbar = tk.Frame(self, bg=COLORS["accent"], height=44)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)

        tk.Label(topbar, text="Receipt",
                 font=("Segoe UI", 12, "bold"),
                 bg=COLORS["accent"], fg=COLORS["white"]).pack(side="left", padx=14)

        tk.Label(topbar, text=self._data["sale_id"],
                 font=("Segoe UI", 10),
                 bg=COLORS["accent"], fg=COLORS["white"]).pack(side="left")

        # ── Receipt text area ─────────────────────────────────────────────
        text_frame = tk.Frame(self, bg=COLORS["bg"])
        text_frame.pack(fill="both", expand=True, padx=16, pady=12)

        scrollbar = tk.Scrollbar(text_frame)
        scrollbar.pack(side="right", fill="y")

        self.text_widget = tk.Text(
            text_frame,
            font=("Courier New", 10),
            bg=COLORS["panel"],
            fg=COLORS["white"],
            relief="flat",
            bd=8,
            wrap="none",
            yscrollcommand=scrollbar.set,
            state="disabled",
            cursor="arrow",
        )
        self.text_widget.pack(fill="both", expand=True)
        scrollbar.config(command=self.text_widget.yview)

        # Horizontal scrollbar for wide receipts
        h_scroll = tk.Scrollbar(self, orient="horizontal",
                                command=self.text_widget.xview)
        h_scroll.pack(fill="x", padx=16)
        self.text_widget.config(xscrollcommand=h_scroll.set)

        self._render_receipt()

        # ── Action buttons ────────────────────────────────────────────────
        btn_frame = tk.Frame(self, bg=COLORS["bg"])
        btn_frame.pack(fill="x", padx=16, pady=(4, 16))

        btn_cfg = dict(
            font=("Segoe UI", 10, "bold"),
            relief="flat", bd=0, pady=9, cursor="hand2"
        )

        tk.Button(btn_frame, text="Print Receipt",
                  bg=COLORS["accent"], fg=COLORS["white"],
                  activebackground=COLORS["button"],
                  command=self._print, **btn_cfg).pack(
                      side="left", fill="x", expand=True, padx=(0, 6))

        tk.Button(btn_frame, text="Save to File",
                  bg=COLORS["panel"], fg=COLORS["white"],
                  activebackground=COLORS["accent"],
                  command=self._save, **btn_cfg).pack(
                      side="left", fill="x", expand=True, padx=(0, 6))

        tk.Button(btn_frame, text="Close",
                  bg=COLORS["button"], fg=COLORS["white"],
                  activebackground=COLORS["button_hover"],
                  command=self.destroy, **btn_cfg).pack(
                      side="left", fill="x", expand=True)

    # ── Receipt rendering ─────────────────────────────────────────────────────

    def _render_receipt(self):
        """Format and insert receipt text; apply basic colour highlights."""
        text = format_receipt_text(self._data)

        self.text_widget.config(state="normal")
        self.text_widget.delete("1.0", "end")

        # Configure colour tags
        self.text_widget.tag_configure("header",
            foreground=COLORS["button"], font=("Courier New", 10, "bold"))
        self.text_widget.tag_configure("total_line",
            foreground=COLORS["success"], font=("Courier New", 11, "bold"))
        self.text_widget.tag_configure("divider",
            foreground=COLORS["muted"])
        self.text_widget.tag_configure("footer",
            foreground=COLORS["muted"], font=("Courier New", 9, "italic"))

        store_name = self._data["store_name"]

        for line in text.split("\n"):
            stripped = line.strip()

            if stripped == store_name:
                self.text_widget.insert("end", line + "\n", "header")
            elif stripped.startswith("TOTAL:"):
                self.text_widget.insert("end", line + "\n", "total_line")
            elif set(stripped) <= {"=", "-"} and stripped:
                self.text_widget.insert("end", line + "\n", "divider")
            elif "Thank you" in line or "come again" in line:
                self.text_widget.insert("end", line + "\n", "footer")
            else:
                self.text_widget.insert("end", line + "\n")

        self.text_widget.config(state="disabled")
        # Scroll to top
        self.text_widget.yview_moveto(0)

    # ── Button actions ────────────────────────────────────────────────────────

    def _print(self):
        ok, msg = print_sale_receipt(self._data)
        if ok:
            messagebox.showinfo("Print", msg)
        else:
            # Fallback: save as text file so cashier can print manually
            ok2, path = save_receipt_to_file(self._data["sale_id"])
            messagebox.showwarning(
                "Print",
                f"{msg}\n\nReceipt saved to:\n{path}" if ok2
                else msg
            )

    def _save(self):
        ok, result = save_receipt_to_file(self._data["sale_id"])
        if ok:
            messagebox.showinfo("Saved", f"Receipt saved to:\n{result}")
        else:
            messagebox.showerror("Error", result)
