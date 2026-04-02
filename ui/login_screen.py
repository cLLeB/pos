"""
Login screen: the first window the user sees.
Authenticates the user and routes to the correct dashboard based on role.
"""

import tkinter as tk
from tkinter import font as tkfont
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules import auth


# ── Colour palette (used across all screens) ─────────────────────────────────
COLORS = {
    "bg":       "#1a1a2e",   # dark navy background
    "panel":    "#16213e",   # slightly lighter panel
    "accent":   "#0f3460",   # blue accent
    "button":   "#e94560",   # red-pink button
    "button_hover": "#c73652",
    "text":     "#eaeaea",   # light text
    "muted":    "#888888",   # grey muted text
    "success":  "#4caf50",
    "error":    "#e94560",
    "white":    "#ffffff",
}


class LoginScreen:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("POS System — Login")
        self.root.geometry("420x520")
        self.root.resizable(False, False)
        self.root.configure(bg=COLORS["bg"])
        self._center_window()
        self._build_ui()

    def _center_window(self):
        """Place the window in the centre of the screen."""
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (420 // 2)
        y = (self.root.winfo_screenheight() // 2) - (520 // 2)
        self.root.geometry(f"420x520+{x}+{y}")

    def _build_ui(self):
        """Construct all widgets on the login screen."""
        # ── Logo / title area ─────────────────────────────────────────────
        header = tk.Frame(self.root, bg=COLORS["bg"], pady=40)
        header.pack(fill="x")

        tk.Label(
            header, text="🛒", font=("Segoe UI Emoji", 42),
            bg=COLORS["bg"], fg=COLORS["white"]
        ).pack()

        tk.Label(
            header, text="POS System",
            font=("Segoe UI", 22, "bold"),
            bg=COLORS["bg"], fg=COLORS["white"]
        ).pack()

        tk.Label(
            header, text="Sign in to continue",
            font=("Segoe UI", 10),
            bg=COLORS["bg"], fg=COLORS["muted"]
        ).pack(pady=(4, 0))

        # ── Login card ────────────────────────────────────────────────────
        card = tk.Frame(self.root, bg=COLORS["panel"], padx=36, pady=32)
        card.pack(fill="x", padx=36)

        # Username
        tk.Label(card, text="Username", font=("Segoe UI", 9),
                 bg=COLORS["panel"], fg=COLORS["muted"]).pack(anchor="w")
        self.username_var = tk.StringVar()
        self.username_entry = tk.Entry(
            card, textvariable=self.username_var,
            font=("Segoe UI", 12), bg=COLORS["accent"],
            fg=COLORS["white"], insertbackground=COLORS["white"],
            relief="flat", bd=8
        )
        self.username_entry.pack(fill="x", pady=(4, 14))

        # Password
        tk.Label(card, text="Password", font=("Segoe UI", 9),
                 bg=COLORS["panel"], fg=COLORS["muted"]).pack(anchor="w")
        self.password_var = tk.StringVar()
        self.password_entry = tk.Entry(
            card, textvariable=self.password_var, show="●",
            font=("Segoe UI", 12), bg=COLORS["accent"],
            fg=COLORS["white"], insertbackground=COLORS["white"],
            relief="flat", bd=8
        )
        self.password_entry.pack(fill="x", pady=(4, 20))

        # Error label (hidden until needed)
        self.error_var = tk.StringVar()
        self.error_label = tk.Label(
            card, textvariable=self.error_var,
            font=("Segoe UI", 9), bg=COLORS["panel"], fg=COLORS["error"]
        )
        self.error_label.pack()

        # Login button
        self.login_btn = tk.Button(
            card, text="LOGIN",
            font=("Segoe UI", 11, "bold"),
            bg=COLORS["button"], fg=COLORS["white"],
            activebackground=COLORS["button_hover"],
            activeforeground=COLORS["white"],
            relief="flat", bd=0, pady=10, cursor="hand2",
            command=self._attempt_login
        )
        self.login_btn.pack(fill="x", pady=(8, 0))

        # ── Bind Enter key ────────────────────────────────────────────────
        self.root.bind("<Return>", lambda e: self._attempt_login())
        self.username_entry.focus_set()

        # ── Hint ──────────────────────────────────────────────────────────
        tk.Label(
            self.root,
            text="Default: admin / admin123",
            font=("Segoe UI", 8),
            bg=COLORS["bg"], fg=COLORS["muted"]
        ).pack(pady=(14, 0))

    def _attempt_login(self):
        """Validate credentials and route the user to the correct screen."""
        username = self.username_var.get().strip()
        password = self.password_var.get()

        if not username or not password:
            self.error_var.set("Please enter username and password.")
            return

        user = auth.login(username, password)

        if user is None:
            self.error_var.set("Incorrect username or password.")
            self.password_var.set("")
            return

        # Successful login — open the correct screen
        self.root.destroy()
        self._open_next_screen(user["role"])

    def _open_next_screen(self, role: str):
        """Launch the appropriate screen for the user's role."""
        new_root = tk.Tk()

        if role in ("admin", "manager"):
            from ui.admin_dashboard import AdminDashboard
            AdminDashboard(new_root)
        else:
            from ui.cashier_screen import CashierScreen
            CashierScreen(new_root)

        new_root.mainloop()
