"""
Backup & Recovery UI.
Create backups, restore from backup, export all tables to CSV,
and view the transaction audit log.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ui.login_screen import COLORS
from modules.backup import (
    backup_database, list_backups, restore_database,
    delete_backup, export_all_to_csv, get_transaction_log,
)


class BackupUI(tk.Frame):
    """Backup & Recovery panel embedded in the admin dashboard."""

    def __init__(self, parent):
        super().__init__(parent, bg=COLORS["bg"])
        self.pack(fill="both", expand=True)
        self._build()
        self._refresh_backup_list()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        # Page title
        tk.Label(self, text="Backup & Recovery",
                 font=("Segoe UI", 14, "bold"),
                 bg=COLORS["bg"], fg=COLORS["white"]).pack(
                     anchor="w", padx=24, pady=(20, 0))

        # Top action buttons
        actions = tk.Frame(self, bg=COLORS["bg"])
        actions.pack(fill="x", padx=24, pady=(12, 0))

        btn_cfg = dict(font=("Segoe UI", 10, "bold"), relief="flat",
                       padx=16, pady=9, cursor="hand2")

        tk.Button(actions, text="Create Backup Now",
                  bg=COLORS["accent"], fg=COLORS["white"],
                  activebackground=COLORS["button"],
                  command=self._create_backup, **btn_cfg).pack(side="left", padx=(0, 8))

        tk.Button(actions, text="Export All Data to CSV",
                  bg=COLORS["panel"], fg=COLORS["white"],
                  activebackground=COLORS["accent"],
                  command=self._export_csv, **btn_cfg).pack(side="left", padx=(0, 8))

        tk.Button(actions, text="View Audit Log",
                  bg=COLORS["panel"], fg=COLORS["white"],
                  activebackground=COLORS["button"],
                  command=self._show_audit_log, **btn_cfg).pack(side="left")

        # Backup list
        list_frame = tk.LabelFrame(self, text="  Existing Backups  ",
                                   bg=COLORS["bg"], fg=COLORS["muted"],
                                   font=("Segoe UI", 9),
                                   relief="flat", bd=1)
        list_frame.pack(fill="both", expand=True, padx=24, pady=16)

        self._build_backup_table(list_frame)

    def _build_backup_table(self, parent):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Backup.Treeview",
                         background=COLORS["panel"],
                         foreground=COLORS["white"],
                         fieldbackground=COLORS["panel"],
                         rowheight=28, font=("Segoe UI", 9))
        style.configure("Backup.Treeview.Heading",
                         background=COLORS["button"],
                         foreground=COLORS["white"],
                         font=("Segoe UI", 9, "bold"))
        style.map("Backup.Treeview",
                  background=[("selected", COLORS["accent"])])

        cols = ("Filename", "Created", "Size (KB)")
        self._tree = ttk.Treeview(parent, columns=cols,
                                   show="headings", style="Backup.Treeview")
        self._tree.heading("Filename",   text="Filename")
        self._tree.heading("Created",    text="Created")
        self._tree.heading("Size (KB)",  text="Size (KB)")
        self._tree.column("Filename",  width=280, anchor="w")
        self._tree.column("Created",   width=160, anchor="w")
        self._tree.column("Size (KB)", width=80,  anchor="e")

        vsb = ttk.Scrollbar(parent, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._tree.pack(fill="both", expand=True)

        # Row action buttons below the table
        row_actions = tk.Frame(parent, bg=COLORS["bg"])
        row_actions.pack(fill="x", pady=(8, 0))

        tk.Button(row_actions, text="Restore Selected",
                  bg=COLORS["button"], fg=COLORS["white"],
                  activebackground=COLORS["button_hover"],
                  font=("Segoe UI", 9, "bold"), relief="flat",
                  padx=14, pady=7, cursor="hand2",
                  command=self._restore_selected).pack(side="left", padx=(0, 8))

        tk.Button(row_actions, text="Delete Selected",
                  bg="#7F1D1D", fg=COLORS["white"],
                  activebackground="#991B1B",
                  font=("Segoe UI", 9), relief="flat",
                  padx=14, pady=7, cursor="hand2",
                  command=self._delete_selected).pack(side="left")

        tk.Button(row_actions, text="Refresh",
                  bg=COLORS["panel"], fg=COLORS["white"],
                  activebackground=COLORS["accent"],
                  font=("Segoe UI", 9), relief="flat",
                  padx=14, pady=7, cursor="hand2",
                  command=self._refresh_backup_list).pack(side="right")

    # ── Data helpers ──────────────────────────────────────────────────────────

    def _refresh_backup_list(self):
        for row in self._tree.get_children():
            self._tree.delete(row)

        backups = list_backups()
        for b in backups:
            self._tree.insert("", "end",
                               iid=b["filepath"],
                               values=(b["filename"], b["created"], b["size_kb"]))

        if not backups:
            self._tree.insert("", "end", values=("No backups found.", "", ""))

    def _selected_backup(self) -> str | None:
        sel = self._tree.selection()
        if not sel:
            messagebox.showwarning("No Selection",
                "Please select a backup from the list.", parent=self)
            return None
        filepath = sel[0]   # iid is the filepath
        if not os.path.isfile(filepath):
            messagebox.showerror("Not Found",
                "The selected backup file no longer exists.", parent=self)
            return None
        return filepath

    # ── Actions ───────────────────────────────────────────────────────────────

    def _create_backup(self):
        ok, result = backup_database()
        if ok:
            messagebox.showinfo("Backup Created",
                f"Backup saved to:\n{result}", parent=self)
            self._refresh_backup_list()
        else:
            messagebox.showerror("Backup Failed", result, parent=self)

    def _restore_selected(self):
        filepath = self._selected_backup()
        if not filepath:
            return

        filename = os.path.basename(filepath)
        confirmed = messagebox.askyesno(
            "Confirm Restore",
            f"Restore database from:\n{filename}\n\n"
            "The current database will be overwritten.\n"
            "A safety backup will be created automatically.\n\n"
            "Continue?",
            parent=self
        )
        if not confirmed:
            return

        ok, msg = restore_database(filepath)
        if ok:
            messagebox.showinfo("Restore Complete", msg, parent=self)
            self._refresh_backup_list()
        else:
            messagebox.showerror("Restore Failed", msg, parent=self)

    def _delete_selected(self):
        filepath = self._selected_backup()
        if not filepath:
            return

        confirmed = messagebox.askyesno(
            "Confirm Delete",
            f"Delete backup:\n{os.path.basename(filepath)}\n\nThis cannot be undone.",
            parent=self
        )
        if not confirmed:
            return

        ok, msg = delete_backup(filepath)
        if ok:
            self._refresh_backup_list()
        else:
            messagebox.showerror("Delete Failed", msg, parent=self)

    def _export_csv(self):
        ok, result = export_all_to_csv()
        if ok:
            messagebox.showinfo("Export Complete",
                f"All tables exported to:\n{result}", parent=self)
        else:
            messagebox.showerror("Export Failed", result, parent=self)

    def _show_audit_log(self):
        AuditLogDialog(self)


# ── Audit Log Dialog ──────────────────────────────────────────────────────────

class AuditLogDialog(tk.Toplevel):
    """Popup showing the Transaction_Logs table."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Transaction Audit Log")
        self.geometry("780x500")
        self.configure(bg=COLORS["bg"])
        self.resizable(True, True)
        self.grab_set()
        self._build()

    def _build(self):
        # Header
        hdr = tk.Frame(self, bg=COLORS["accent"], height=40)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="Transaction Audit Log",
                 font=("Segoe UI", 11, "bold"),
                 bg=COLORS["accent"], fg=COLORS["white"]).pack(
                     side="left", padx=14, pady=8)

        # Table
        frame = tk.Frame(self, bg=COLORS["bg"])
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        style = ttk.Style()
        style.configure("Audit.Treeview",
                         background=COLORS["panel"],
                         foreground=COLORS["white"],
                         fieldbackground=COLORS["panel"],
                         rowheight=24, font=("Segoe UI", 8))
        style.configure("Audit.Treeview.Heading",
                         background=COLORS["button"],
                         foreground=COLORS["white"],
                         font=("Segoe UI", 8, "bold"))

        cols = ("#", "Timestamp", "User", "Action", "Details")
        tree = ttk.Treeview(frame, columns=cols,
                             show="headings", style="Audit.Treeview")
        tree.heading("#",         text="#")
        tree.heading("Timestamp", text="Timestamp")
        tree.heading("User",      text="User")
        tree.heading("Action",    text="Action")
        tree.heading("Details",   text="Details")
        tree.column("#",         width=45,  anchor="e")
        tree.column("Timestamp", width=150, anchor="w")
        tree.column("User",      width=90,  anchor="w")
        tree.column("Action",    width=120, anchor="w")
        tree.column("Details",   width=340, anchor="w")

        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)

        tree.tag_configure("odd",  background=COLORS["panel"])
        tree.tag_configure("even", background=COLORS["bg"])

        logs = get_transaction_log(limit=500)
        for i, entry in enumerate(logs):
            tag = "odd" if i % 2 else "even"
            tree.insert("", "end", tags=(tag,), values=(
                entry["log_id"],
                entry["timestamp"],
                entry["username"] or "—",
                entry["action"],
                entry["details"] or "",
            ))

        # Close button
        tk.Button(self, text="Close",
                  bg=COLORS["button"], fg=COLORS["white"],
                  activebackground=COLORS["button_hover"],
                  font=("Segoe UI", 10, "bold"), relief="flat",
                  padx=20, pady=8, cursor="hand2",
                  command=self.destroy).pack(pady=(0, 12))
