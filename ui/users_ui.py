"""
User Management UI — Admin only.
Allows admins to view, add, edit roles, reset passwords, and deactivate users.
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ui.login_screen import COLORS
from modules import auth


class UsersUI:
    def __init__(self, parent: tk.Frame):
        self.parent = parent
        self._build_ui()
        self._load_users()

    # ── Layout ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Header row
        header = tk.Frame(self.parent, bg=COLORS["bg"])
        header.pack(fill="x", padx=32, pady=(24, 0))

        tk.Label(
            header, text="User Management",
            font=("Segoe UI", 18, "bold"),
            bg=COLORS["bg"], fg=COLORS["white"]
        ).pack(side="left")

        tk.Button(
            header, text="+ Add User",
            font=("Segoe UI", 10, "bold"),
            bg=COLORS["button"], fg=COLORS["white"],
            activebackground=COLORS["button_hover"],
            relief="flat", bd=0, padx=14, pady=6,
            cursor="hand2", command=self._open_add_dialog
        ).pack(side="right")

        tk.Label(
            header,
            text="Admin-only: manage accounts and roles.",
            font=("Segoe UI", 9),
            bg=COLORS["bg"], fg=COLORS["muted"]
        ).pack(side="left", padx=12)

        # Table frame
        table_frame = tk.Frame(self.parent, bg=COLORS["bg"])
        table_frame.pack(fill="both", expand=True, padx=32, pady=16)

        # Scrollbar
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")

        # Treeview table
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview",
            background=COLORS["panel"],
            foreground=COLORS["text"],
            rowheight=34,
            fieldbackground=COLORS["panel"],
            borderwidth=0,
            font=("Segoe UI", 10)
        )
        style.configure("Treeview.Heading",
            background=COLORS["accent"],
            foreground=COLORS["white"],
            font=("Segoe UI", 10, "bold"),
            relief="flat"
        )
        style.map("Treeview", background=[("selected", COLORS["button"])])

        columns = ("user_id", "username", "role", "status", "created_at")
        self.tree = ttk.Treeview(
            table_frame, columns=columns, show="headings",
            yscrollcommand=scrollbar.set, selectmode="browse"
        )
        scrollbar.config(command=self.tree.yview)

        self.tree.heading("user_id",    text="ID")
        self.tree.heading("username",   text="Username")
        self.tree.heading("role",       text="Role")
        self.tree.heading("status",     text="Status")
        self.tree.heading("created_at", text="Created At")

        self.tree.column("user_id",    width=50,  anchor="center")
        self.tree.column("username",   width=160, anchor="w")
        self.tree.column("role",       width=120, anchor="center")
        self.tree.column("status",     width=90,  anchor="center")
        self.tree.column("created_at", width=180, anchor="center")

        self.tree.pack(fill="both", expand=True)

        # Action buttons row
        actions = tk.Frame(self.parent, bg=COLORS["bg"])
        actions.pack(fill="x", padx=32, pady=(0, 20))

        btn_cfg = dict(
            font=("Segoe UI", 10),
            bg=COLORS["accent"], fg=COLORS["white"],
            activebackground=COLORS["button"],
            activeforeground=COLORS["white"],
            relief="flat", bd=0, padx=14, pady=6,
            cursor="hand2"
        )

        tk.Button(actions, text="Change Role",     command=self._change_role,     **btn_cfg).pack(side="left", padx=(0, 8))
        tk.Button(actions, text="Reset Password",  command=self._reset_password,  **btn_cfg).pack(side="left", padx=(0, 8))
        tk.Button(actions, text="Toggle Active",   command=self._toggle_active,   **btn_cfg).pack(side="left", padx=(0, 8))
        tk.Button(actions, text="Refresh",         command=self._load_users,      **btn_cfg).pack(side="right")

    # ── Data loading ─────────────────────────────────────────────────────────

    def _load_users(self):
        """Fetch all users from DB and populate the table."""
        for row in self.tree.get_children():
            self.tree.delete(row)

        users = auth.get_all_users()
        for u in users:
            status = "Active" if u["is_active"] else "Inactive"
            tag = "inactive" if not u["is_active"] else ""
            self.tree.insert("", "end", values=(
                u["user_id"],
                u["username"],
                u["role"].capitalize(),
                status,
                u["created_at"]
            ), tags=(tag,))

        self.tree.tag_configure("inactive", foreground=COLORS["muted"])

    def _get_selected_user(self) -> dict | None:
        """Return the selected row as a dict, or None if nothing selected."""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select a user first.")
            return None
        values = self.tree.item(selected[0])["values"]
        return {
            "user_id":  values[0],
            "username": values[1],
            "role":     values[2].lower(),
            "is_active": values[3] == "Active",
        }

    # ── Actions ───────────────────────────────────────────────────────────────

    def _open_add_dialog(self):
        """Open a popup dialog to create a new user."""
        AddUserDialog(self.parent, on_success=self._load_users)

    def _change_role(self):
        user = self._get_selected_user()
        if not user:
            return

        # Guard: don't let admin demote themselves
        current = auth.get_current_user()
        if user["user_id"] == current["user_id"]:
            messagebox.showerror("Not Allowed", "You cannot change your own role.")
            return

        RoleDialog(self.parent, user, on_success=self._load_users)

    def _reset_password(self):
        user = self._get_selected_user()
        if not user:
            return

        new_pw = simpledialog.askstring(
            "Reset Password",
            f"Enter new password for '{user['username']}':",
            show="*"
        )
        if not new_pw:
            return

        ok, msg = auth.reset_user_password(user["user_id"], new_pw)
        if ok:
            messagebox.showinfo("Success", msg)
        else:
            messagebox.showerror("Error", msg)

    def _toggle_active(self):
        user = self._get_selected_user()
        if not user:
            return

        current = auth.get_current_user()
        if user["user_id"] == current["user_id"]:
            messagebox.showerror("Not Allowed", "You cannot deactivate your own account.")
            return

        new_state = not user["is_active"]
        action = "activate" if new_state else "deactivate"
        confirm = messagebox.askyesno("Confirm", f"Are you sure you want to {action} '{user['username']}'?")
        if not confirm:
            return

        ok, msg = auth.toggle_user_active(user["user_id"], new_state)
        if ok:
            messagebox.showinfo("Success", msg)
            self._load_users()
        else:
            messagebox.showerror("Error", msg)


# ── Add User Dialog ───────────────────────────────────────────────────────────

class AddUserDialog(tk.Toplevel):
    def __init__(self, parent, on_success):
        super().__init__(parent)
        self.on_success = on_success
        self.title("Add New User")
        self.geometry("360x340")
        self.configure(bg=COLORS["bg"])
        self.resizable(False, False)
        self.grab_set()   # modal
        self._build()

    def _build(self):
        tk.Label(self, text="Add New User", font=("Segoe UI", 14, "bold"),
                 bg=COLORS["bg"], fg=COLORS["white"]).pack(pady=(20, 4))

        form = tk.Frame(self, bg=COLORS["bg"], padx=30)
        form.pack(fill="x")

        # Username
        tk.Label(form, text="Username", font=("Segoe UI", 9),
                 bg=COLORS["bg"], fg=COLORS["muted"]).pack(anchor="w", pady=(12, 2))
        self.username_var = tk.StringVar()
        tk.Entry(form, textvariable=self.username_var,
                 font=("Segoe UI", 11), bg=COLORS["accent"],
                 fg=COLORS["white"], insertbackground=COLORS["white"],
                 relief="flat", bd=6).pack(fill="x")

        # Password
        tk.Label(form, text="Password", font=("Segoe UI", 9),
                 bg=COLORS["bg"], fg=COLORS["muted"]).pack(anchor="w", pady=(10, 2))
        self.password_var = tk.StringVar()
        tk.Entry(form, textvariable=self.password_var, show="●",
                 font=("Segoe UI", 11), bg=COLORS["accent"],
                 fg=COLORS["white"], insertbackground=COLORS["white"],
                 relief="flat", bd=6).pack(fill="x")

        # Role
        tk.Label(form, text="Role", font=("Segoe UI", 9),
                 bg=COLORS["bg"], fg=COLORS["muted"]).pack(anchor="w", pady=(10, 2))
        self.role_var = tk.StringVar(value="cashier")
        role_frame = tk.Frame(form, bg=COLORS["bg"])
        role_frame.pack(fill="x")
        for r in ("admin", "manager", "cashier"):
            tk.Radiobutton(
                role_frame, text=r.capitalize(), variable=self.role_var, value=r,
                font=("Segoe UI", 10),
                bg=COLORS["bg"], fg=COLORS["text"],
                selectcolor=COLORS["accent"],
                activebackground=COLORS["bg"]
            ).pack(side="left", padx=(0, 12))

        # Error label
        self.error_var = tk.StringVar()
        tk.Label(form, textvariable=self.error_var, font=("Segoe UI", 9),
                 bg=COLORS["bg"], fg=COLORS["error"]).pack(pady=(8, 0))

        # Submit button
        tk.Button(form, text="Create User",
                  font=("Segoe UI", 11, "bold"),
                  bg=COLORS["button"], fg=COLORS["white"],
                  activebackground=COLORS["button_hover"],
                  relief="flat", bd=0, pady=8,
                  cursor="hand2", command=self._submit).pack(fill="x", pady=(12, 0))

    def _submit(self):
        username = self.username_var.get().strip()
        password = self.password_var.get()
        role = self.role_var.get()

        ok, msg = auth.add_user(username, password, role)
        if ok:
            self.on_success()
            self.destroy()
            messagebox.showinfo("Success", msg)
        else:
            self.error_var.set(msg)


# ── Role Change Dialog ────────────────────────────────────────────────────────

class RoleDialog(tk.Toplevel):
    def __init__(self, parent, user: dict, on_success):
        super().__init__(parent)
        self.user = user
        self.on_success = on_success
        self.title("Change Role")
        self.geometry("300x220")
        self.configure(bg=COLORS["bg"])
        self.resizable(False, False)
        self.grab_set()
        self._build()

    def _build(self):
        tk.Label(self, text=f"Change role for: {self.user['username']}",
                 font=("Segoe UI", 11, "bold"),
                 bg=COLORS["bg"], fg=COLORS["white"]).pack(pady=(20, 4))

        tk.Label(self, text=f"Current role: {self.user['role'].capitalize()}",
                 font=("Segoe UI", 9),
                 bg=COLORS["bg"], fg=COLORS["muted"]).pack()

        self.role_var = tk.StringVar(value=self.user["role"])
        frame = tk.Frame(self, bg=COLORS["bg"])
        frame.pack(pady=16)
        for r in ("admin", "manager", "cashier"):
            tk.Radiobutton(
                frame, text=r.capitalize(), variable=self.role_var, value=r,
                font=("Segoe UI", 11),
                bg=COLORS["bg"], fg=COLORS["text"],
                selectcolor=COLORS["accent"],
                activebackground=COLORS["bg"]
            ).pack(anchor="w", padx=30, pady=2)

        tk.Button(self, text="Save Role",
                  font=("Segoe UI", 11, "bold"),
                  bg=COLORS["button"], fg=COLORS["white"],
                  activebackground=COLORS["button_hover"],
                  relief="flat", bd=0, padx=20, pady=8,
                  cursor="hand2", command=self._save).pack(pady=(4, 0))

    def _save(self):
        ok, msg = auth.update_user_role(self.user["user_id"], self.role_var.get())
        if ok:
            self.on_success()
            self.destroy()
            messagebox.showinfo("Success", msg)
        else:
            messagebox.showerror("Error", msg)
