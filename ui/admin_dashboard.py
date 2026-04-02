"""
Admin / Manager Dashboard.
Sidebar navigation that swaps content frames on the right.
"""

import tkinter as tk
from tkinter import ttk
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules import auth
from ui.login_screen import COLORS
from utils.tk_after import SafeAfterMixin


class AdminDashboard(SafeAfterMixin):
    # Session timeout: 30 minutes of inactivity → auto-logout
    _TIMEOUT_MS = 30 * 60 * 1000

    def __init__(self, root: tk.Tk):
        self.root = root
        self._is_closing = False
        self._init_after_manager(self.root)
        user = auth.get_current_user()
        self.root.title(f"POS System — {user['role'].capitalize()} Dashboard ({user['username']})")
        self.root.geometry("1100x680")
        self.root.configure(bg=COLORS["bg"])
        self.root.resizable(True, True)
        self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)
        self._center_window()
        self._build_ui()
        self._start_session_timeout()

    def _center_window(self):
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (1100 // 2)
        y = (self.root.winfo_screenheight() // 2) - (680 // 2)
        self.root.geometry(f"1100x680+{x}+{y}")

    def _build_ui(self):
        # ── Top bar ───────────────────────────────────────────────────────
        topbar = tk.Frame(self.root, bg=COLORS["accent"], height=50)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)

        tk.Label(
            topbar, text="🛒  POS System",
            font=("Segoe UI", 14, "bold"),
            bg=COLORS["accent"], fg=COLORS["white"]
        ).pack(side="left", padx=16)

        user = auth.get_current_user()
        tk.Label(
            topbar, text=f"👤  {user['username']}  |  {user['role'].capitalize()}",
            font=("Segoe UI", 10),
            bg=COLORS["accent"], fg=COLORS["white"]
        ).pack(side="right", padx=8)

        tk.Button(
            topbar, text="Logout",
            font=("Segoe UI", 9),
            bg=COLORS["button"], fg=COLORS["white"],
            activebackground=COLORS["button_hover"],
            relief="flat", bd=0, padx=12, pady=6,
            cursor="hand2", command=self._logout
        ).pack(side="right", padx=8)

        # ── Main body ─────────────────────────────────────────────────────
        body = tk.Frame(self.root, bg=COLORS["bg"])
        body.pack(fill="both", expand=True)

        # Sidebar
        self.sidebar = tk.Frame(body, bg=COLORS["panel"], width=200)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Content area
        self.content = tk.Frame(body, bg=COLORS["bg"])
        self.content.pack(side="left", fill="both", expand=True)

        self._build_sidebar()
        # Pre-select Home so it starts highlighted
        home_label = "🏠  Home"
        if home_label in self._nav_buttons:
            self._nav_select(home_label, self._show_home)
        else:
            self._show_home()

    def _build_sidebar(self):
        """Create navigation buttons in the sidebar."""
        user = auth.get_current_user()

        # ── User / role badge ─────────────────────────────────────────────
        badge_frame = tk.Frame(self.sidebar, bg=COLORS["accent"])
        badge_frame.pack(fill="x")
        tk.Label(badge_frame, text=user["username"],
                 font=("Segoe UI", 10, "bold"),
                 bg=COLORS["accent"], fg=COLORS["white"]).pack(
                     padx=14, pady=(12, 0), anchor="w")

        role_colors = {
            "admin":   ("#22c55e", "#15803d"),   # green
            "manager": ("#f59e0b", "#92400e"),   # amber
            "cashier": ("#3b82f6", "#1e40af"),   # blue
        }
        badge_bg, badge_fg = role_colors.get(user["role"], ("#888", "#333"))
        role_pill = tk.Frame(badge_frame, bg=badge_bg)
        role_pill.pack(anchor="w", padx=14, pady=(4, 12))
        tk.Label(role_pill, text=f"  {user['role'].upper()}  ",
                 font=("Segoe UI", 7, "bold"),
                 bg=badge_bg, fg=badge_fg).pack()

        tk.Frame(self.sidebar, bg="#0a2040", height=1).pack(fill="x")

        tk.Label(
            self.sidebar, text="MENU",
            font=("Segoe UI", 8, "bold"),
            bg=COLORS["panel"], fg=COLORS["muted"]
        ).pack(pady=(16, 8), padx=16, anchor="w")

        nav_items = [
            ("🏠  Home",          self._show_home),
            ("📦  Products",       self._show_products),
            ("📋  Inventory",      self._show_inventory),
            ("👥  Customers",      self._show_customers),
            ("💰  New Sale",       self._show_cashier),
            ("📊  Reports",        self._show_reports),
            ("📡  Payments Live",  self._show_payment_monitor),
        ]

        # Returns is visible to managers and admins
        if user["role"] in ("admin", "manager"):
            nav_items += [
                ("↩  Returns",     self._show_returns),
            ]

        # Backup, user management, and settings are admin-only
        if user["role"] == "admin":
            nav_items += [
                ("   Backup",     self._show_backup),
                ("   Users",      self._show_users),
                ("   Settings",   self._show_settings),
            ]

        self._nav_buttons = {}
        self._active_nav  = None

        for label, command in nav_items:
            btn = tk.Button(
                self.sidebar, text=label,
                font=("Segoe UI", 10),
                bg=COLORS["panel"], fg=COLORS["text"],
                activebackground=COLORS["accent"],
                activeforeground=COLORS["white"],
                relief="flat", bd=0,
                pady=12, padx=16, anchor="w",
                cursor="hand2",
                command=lambda lbl=label, cmd=command: self._nav_select(lbl, cmd)
            )
            btn.pack(fill="x")
            self._nav_buttons[label] = btn

        # Role access notice at sidebar bottom (UX: explain why items are hidden)
        if user["role"] == "manager":
            notice = tk.Frame(self.sidebar, bg=COLORS["panel"])
            notice.pack(side="bottom", fill="x", pady=8, padx=12)
            tk.Label(notice,
                     text="Backup, Users & Settings\nrequire Admin access.",
                     font=("Segoe UI", 7), justify="center",
                     bg=COLORS["panel"], fg=COLORS["muted"]).pack(pady=6)

    def _nav_select(self, label: str, command):
        """Highlight the active sidebar button and run the navigation command."""
        # Reset previous active button
        if self._active_nav and self._active_nav in self._nav_buttons:
            self._nav_buttons[self._active_nav].config(
                bg=COLORS["panel"], fg=COLORS["text"])

        # Highlight newly selected button
        self._active_nav = label
        self._nav_buttons[label].config(
            bg=COLORS["accent"], fg=COLORS["white"])

        command()

    def _clear_content(self):
        """Destroy all widgets in the content area."""
        for widget in self.content.winfo_children():
            widget.destroy()

    # ── Navigation handlers ───────────────────────────────────────────────────

    def _show_home(self):
        self._clear_content()
        from ui.home_panel import HomePanel
        HomePanel(self.content)

    def _show_products(self):
        self._clear_content()
        from ui.product_ui import ProductUI
        ProductUI(self.content)

    def _show_inventory(self):
        self._clear_content()
        from ui.inventory_ui import InventoryUI
        InventoryUI(self.content)

    def _show_customers(self):
        self._clear_content()
        from ui.customer_ui import CustomerUI
        CustomerUI(self.content)

    def _show_cashier(self):
        """Open the cashier screen in a new window."""
        new_win = tk.Toplevel(self.root)
        from ui.cashier_screen import CashierScreen
        CashierScreen(new_win)

    def _show_reports(self):
        self._clear_content()
        from ui.reports_ui import ReportsUI
        ReportsUI(self.content)

    def _show_payment_monitor(self):
        self._clear_content()
        from ui.payment_monitor_ui import PaymentMonitorUI
        PaymentMonitorUI(self.content)

    def _show_backup(self):
        self._clear_content()
        from ui.backup_ui import BackupUI
        BackupUI(self.content)

    def _show_users(self):
        self._clear_content()
        from ui.users_ui import UsersUI
        UsersUI(self.content)

    def _show_settings(self):
        self._clear_content()
        from ui.settings_ui import SettingsUI
        SettingsUI(self.content)

    def _show_returns(self):
        self._clear_content()
        from ui.returns_ui import ReturnsUI
        ReturnsUI(self.content)

    # ── Session timeout ───────────────────────────────────────────────────────

    def _start_session_timeout(self):
        """Reset the inactivity timer on mouse/keyboard events."""
        for event in ("<Motion>", "<KeyPress>", "<ButtonPress>"):
            self.root.bind_all(event, self._reset_timeout, add="+")
        self._reset_timeout()

    def _reset_timeout(self, _event=None):
        if self._is_closing:
            return
        self._after_schedule("session_timeout", self._TIMEOUT_MS, self._session_expired)

    def _cancel_scheduled_jobs(self):
        self._after_cancel_all()

    def _on_window_close(self):
        if self._is_closing:
            return
        self._is_closing = True
        self._after_mark_closing()
        self._cancel_scheduled_jobs()
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _session_expired(self):
        if self._is_closing:
            return
        from tkinter import messagebox
        messagebox.showwarning(
            "Session Expired",
            "You have been logged out due to 30 minutes of inactivity.",
            parent=self.root
        )
        self._logout()

    def _logout(self):
        if self._is_closing:
            return
        self._is_closing = True
        self._after_mark_closing()
        self._cancel_scheduled_jobs()
        auth.logout()
        self.root.destroy()
        import main
        main.launch()
