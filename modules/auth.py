"""
Authentication module: login, logout, session management, and role checking.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_setup import get_connection
from utils.security import verify_password
from utils.helpers import current_timestamp

# In-memory session: stores the currently logged-in user
_current_user: dict | None = None


def login(username: str, password: str) -> dict | None:
    """
    Attempt to log in with the given credentials.
    Returns the user dict on success, or None on failure.
    """
    global _current_user

    if not username or not password:
        return None

    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM Users WHERE username = ? AND is_active = 1", (username,)
    ).fetchone()
    conn.close()

    if row is None:
        return None

    if not verify_password(password, row["password_hash"]):
        return None

    _current_user = {
        "user_id":  row["user_id"],
        "username": row["username"],
        "role":     row["role"],
    }

    _log_action(_current_user["user_id"], "LOGIN", f"User '{username}' logged in")
    return _current_user


def logout():
    """Clear the current session."""
    global _current_user
    if _current_user:
        _log_action(_current_user["user_id"], "LOGOUT", f"User '{_current_user['username']}' logged out")
    _current_user = None


def get_current_user() -> dict | None:
    """Return the currently logged-in user, or None if not logged in."""
    return _current_user


def get_current_role() -> str:
    """Return the role of the current user ('admin', 'manager', 'cashier'), or empty string."""
    return _current_user["role"] if _current_user else ""


def is_admin() -> bool:
    return get_current_role() == "admin"


def is_manager_or_admin() -> bool:
    return get_current_role() in ("admin", "manager")


# ── User management (admin only) ─────────────────────────────────────────────

def get_all_users() -> list[dict]:
    """Return all users (for admin user management screen)."""
    conn = get_connection()
    rows = conn.execute("SELECT user_id, username, role, is_active, created_at FROM Users").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_user(username: str, password: str, role: str) -> tuple[bool, str]:
    """
    Create a new user account.
    Returns (success: bool, message: str).
    """
    from utils.security import hash_password

    if role not in ("admin", "manager", "cashier"):
        return False, "Invalid role."
    if not username or not password:
        return False, "Username and password are required."

    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO Users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            (username, hash_password(password), role, current_timestamp())
        )
        conn.commit()
        _log_action(_current_user["user_id"] if _current_user else None, "ADD_USER", f"Created user '{username}' as {role}")
        return True, f"User '{username}' created successfully."
    except Exception as e:
        return False, f"Failed to create user: {e}"
    finally:
        conn.close()


def update_user_role(user_id: int, new_role: str) -> tuple[bool, str]:
    """Change a user's role."""
    if new_role not in ("admin", "manager", "cashier"):
        return False, "Invalid role."
    conn = get_connection()
    conn.execute("UPDATE Users SET role = ? WHERE user_id = ?", (new_role, user_id))
    conn.commit()
    conn.close()
    return True, "Role updated."


def reset_user_password(user_id: int, new_password: str) -> tuple[bool, str]:
    """Reset a user's password."""
    from utils.security import hash_password
    if not new_password:
        return False, "Password cannot be empty."
    conn = get_connection()
    conn.execute("UPDATE Users SET password_hash = ? WHERE user_id = ?", (hash_password(new_password), user_id))
    conn.commit()
    conn.close()
    return True, "Password reset successfully."


def toggle_user_active(user_id: int, active: bool) -> tuple[bool, str]:
    """Activate or deactivate a user account."""
    conn = get_connection()
    conn.execute("UPDATE Users SET is_active = ? WHERE user_id = ?", (1 if active else 0, user_id))
    conn.commit()
    conn.close()
    status = "activated" if active else "deactivated"
    return True, f"User {status}."


# ── Internal helpers ──────────────────────────────────────────────────────────

def _log_action(user_id: int | None, action: str, details: str = ""):
    """Write an entry to the Transaction_Logs table."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO Transaction_Logs (user_id, action, details, timestamp) VALUES (?, ?, ?, ?)",
        (user_id, action, details, current_timestamp())
    )
    conn.commit()
    conn.close()
