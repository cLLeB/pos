"""
Backup & Recovery module.
Creates timestamped DB backups, restores from a chosen backup,
and exports all tables to CSV files.
"""

import os
import sys
import csv
import shutil
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db_setup import get_connection, DB_PATH

BACKUPS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "backups"
)
EXPORTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "exports"
)
os.makedirs(BACKUPS_DIR, exist_ok=True)
os.makedirs(EXPORTS_DIR, exist_ok=True)

# Tables exported by export_all_to_csv (in dependency order)
_EXPORT_TABLES = [
    "Users", "Products", "Customers", "Sales",
    "Sales_Items", "Returns", "Return_Items", "Inventory", "Payments", "Transaction_Logs",
]


# ── Backup ────────────────────────────────────────────────────────────────────

def backup_database() -> tuple[bool, str]:
    """
    Copy the live database to /backups/backup_YYYY-MM-DD_HH-MM-SS.db.
    Returns (success, filepath_or_error_message).
    """
    ts       = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"backup_{ts}.db"
    dest     = os.path.join(BACKUPS_DIR, filename)

    try:
        # Use SQLite's online backup API so we don't copy a half-written file
        src_conn  = get_connection()
        dest_conn = __import__("sqlite3").connect(dest)
        src_conn.backup(dest_conn)
        dest_conn.close()
        src_conn.close()
        return True, dest
    except Exception as e:
        return False, f"Backup failed: {e}"


def list_backups() -> list[dict]:
    """
    Return all backup files in /backups/, newest first.
    Each entry: {filename, filepath, size_kb, created}.
    """
    if not os.path.isdir(BACKUPS_DIR):
        return []

    backups = []
    for name in sorted(os.listdir(BACKUPS_DIR), reverse=True):
        if name.endswith(".db"):
            path = os.path.join(BACKUPS_DIR, name)
            stat = os.stat(path)
            backups.append({
                "filename": name,
                "filepath": path,
                "size_kb":  round(stat.st_size / 1024, 1),
                "created":  datetime.fromtimestamp(stat.st_mtime).strftime(
                                "%Y-%m-%d %H:%M:%S"),
            })
    return backups


# ── Restore ───────────────────────────────────────────────────────────────────

def restore_database(backup_filepath: str) -> tuple[bool, str]:
    """
    Replace the live database with a chosen backup.
    Creates a safety backup of the current DB first.
    Returns (success, message).
    """
    if not os.path.isfile(backup_filepath):
        return False, f"Backup file not found: {backup_filepath}"

    # Safety snapshot before overwriting
    safety_ts   = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safety_path = os.path.join(BACKUPS_DIR, f"pre_restore_{safety_ts}.db")
    try:
        shutil.copy2(DB_PATH, safety_path)
    except Exception as e:
        return False, f"Could not create safety backup: {e}"

    try:
        src_conn  = __import__("sqlite3").connect(backup_filepath)
        dest_conn = get_connection()
        src_conn.backup(dest_conn)
        dest_conn.close()
        src_conn.close()
        return True, (
            f"Database restored from:\n{os.path.basename(backup_filepath)}\n\n"
            f"Safety backup saved as:\n{os.path.basename(safety_path)}"
        )
    except Exception as e:
        return False, f"Restore failed: {e}"


def delete_backup(backup_filepath: str) -> tuple[bool, str]:
    """Delete a backup file. Returns (success, message)."""
    try:
        os.remove(backup_filepath)
        return True, "Backup deleted."
    except Exception as e:
        return False, f"Could not delete backup: {e}"


# ── CSV Export ────────────────────────────────────────────────────────────────

def export_all_to_csv() -> tuple[bool, str]:
    """
    Export every table to a separate CSV in /exports/YYYY-MM-DD_HH-MM-SS/.
    Returns (success, folder_path_or_error).
    """
    ts         = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    export_dir = os.path.join(EXPORTS_DIR, f"export_{ts}")
    os.makedirs(export_dir, exist_ok=True)

    conn = get_connection()
    try:
        for table in _EXPORT_TABLES:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            if not rows:
                continue
            filepath = os.path.join(export_dir, f"{table}.csv")
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows([dict(r) for r in rows])
    except Exception as e:
        conn.close()
        return False, f"Export failed: {e}"

    conn.close()
    return True, export_dir


# ── Transaction log helper ─────────────────────────────────────────────────────

def log_action(user_id: int | None, action: str, details: str = "") -> None:
    """
    Append an entry to Transaction_Logs.
    Called from auth, sales, and admin operations for audit trail.
    """
    from utils.helpers import current_timestamp
    conn = get_connection()
    conn.execute(
        "INSERT INTO Transaction_Logs (user_id, action, details, timestamp) VALUES (?,?,?,?)",
        (user_id, action, details, current_timestamp())
    )
    conn.commit()
    conn.close()


def get_transaction_log(limit: int = 200) -> list[dict]:
    """Return the most recent Transaction_Log entries (newest first)."""
    conn  = get_connection()
    rows  = conn.execute(
        """SELECT tl.log_id, tl.timestamp, u.username, tl.action, tl.details
           FROM Transaction_Logs tl
           LEFT JOIN Users u ON tl.user_id = u.user_id
           ORDER BY tl.log_id DESC
           LIMIT ?""",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
