"""
E2E Scenario 6: Authentication flows.

Covers:
  - Correct credentials → login succeeds, session set
  - Wrong password → returns None, no session
  - Deactivated account → blocked
  - Logout clears session
  - Role-based routing helpers
"""

import unittest
from tests.test_base import PosTestCase
from modules import auth


class TestAuthLogin(PosTestCase):
    """Login / logout / role check flow."""

    def tearDown(self):
        auth.logout()   # clean session between tests

    # ── Happy path ────────────────────────────────────────────────────────────

    def test_admin_login_succeeds(self):
        user = auth.login("admin", "admin123")
        self.assertIsNotNone(user, "admin login must succeed")
        self.assertEqual(user["role"], "admin")
        self.assertEqual(auth.get_current_user()["username"], "admin")

    def test_manager_login_succeeds(self):
        user = auth.login("manager1", "manager123")
        self.assertIsNotNone(user)
        self.assertEqual(user["role"], "manager")

    def test_cashier_login_succeeds(self):
        user = auth.login("cashier1", "cashier123")
        self.assertIsNotNone(user)
        self.assertEqual(user["role"], "cashier")

    def test_session_persists_after_login(self):
        auth.login("admin", "admin123")
        self.assertIsNotNone(auth.get_current_user())
        self.assertTrue(auth.is_admin())

    # ── Error cases ───────────────────────────────────────────────────────────

    def test_wrong_password_returns_none(self):
        result = auth.login("admin", "wrongpassword")
        self.assertIsNone(result, "Wrong password must return None")
        self.assertIsNone(auth.get_current_user(),
                          "Session must not be set on failed login")

    def test_nonexistent_user_returns_none(self):
        result = auth.login("ghost", "anything")
        self.assertIsNone(result)

    def test_empty_credentials_rejected(self):
        self.assertIsNone(auth.login("", ""))
        self.assertIsNone(auth.login("admin", ""))
        self.assertIsNone(auth.login("", "admin123"))

    # ── Logout ────────────────────────────────────────────────────────────────

    def test_logout_clears_session(self):
        auth.login("admin", "admin123")
        auth.logout()
        self.assertIsNone(auth.get_current_user())
        self.assertFalse(auth.is_admin())

    # ── User management ───────────────────────────────────────────────────────

    def test_add_and_login_new_user(self):
        ok, msg = auth.add_user("testcashier", "pass1234", "cashier")
        self.assertTrue(ok, msg)

        user = auth.login("testcashier", "pass1234")
        self.assertIsNotNone(user)
        self.assertEqual(user["role"], "cashier")

    def test_deactivated_user_cannot_login(self):
        ok, msg = auth.add_user("tempuser", "pass1234", "cashier")
        self.assertTrue(ok, msg)

        # Fetch ID then deactivate
        from database.db_setup import get_connection
        conn = get_connection()
        row = conn.execute(
            "SELECT user_id FROM Users WHERE username='tempuser'"
        ).fetchone()
        conn.close()

        ok2, _ = auth.toggle_user_active(row["user_id"], active=False)
        self.assertTrue(ok2)

        result = auth.login("tempuser", "pass1234")
        self.assertIsNone(result, "Deactivated user must be blocked")


class TestRoleHelpers(PosTestCase):
    """is_admin / is_manager_or_admin helpers."""

    def tearDown(self):
        auth.logout()

    def test_admin_role_flags(self):
        auth.login("admin", "admin123")
        self.assertTrue(auth.is_admin())
        self.assertTrue(auth.is_manager_or_admin())

    def test_manager_role_flags(self):
        auth.login("manager1", "manager123")
        self.assertFalse(auth.is_admin())
        self.assertTrue(auth.is_manager_or_admin())

    def test_cashier_role_flags(self):
        auth.login("cashier1", "cashier123")
        self.assertFalse(auth.is_admin())
        self.assertFalse(auth.is_manager_or_admin())


if __name__ == "__main__":
    unittest.main()
