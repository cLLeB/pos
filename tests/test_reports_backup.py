"""
E2E Scenarios 4 & 5: Reports generation + Backup & Restore.

Scenario 4: Admin → daily sales report → export CSV
Scenario 5: Admin → create backup → list backups → restore backup
"""

import os
import unittest
import tempfile
from datetime import datetime

from tests.test_base import PosTestCase, add_product_get_id
from modules import auth
from modules.products import add_product
from modules.customers import register_customer
from modules.sales import create_sale
from modules.payments import process_cash_payment
from modules.reports import (
    daily_sales_report, weekly_sales_report,
    product_performance_report, inventory_report,
    cashier_performance_report, profit_report,
    export_report_to_csv,
)
from modules.backup import (
    backup_database, list_backups, restore_database,
    delete_backup, export_all_to_csv, get_transaction_log,
)


def _seed_sale(user_id, pid, qty=2, method="Cash"):
    """Helper: create a sale and process its payment."""
    cart = [{"product_id": pid, "name": "Item", "price": 5.00, "quantity": qty}]
    ok, _, sale_id = create_sale(user_id, cart, method)
    if ok:
        from modules.sales import get_sale_by_id
        sale = get_sale_by_id(sale_id)
        process_cash_payment(sale_id, sale["total_amount"] + 10, sale["total_amount"])
    return ok, sale_id


class TestReports(PosTestCase):
    """Scenario 4: All 6 report types generate without errors."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        auth.login("admin", "admin123")
        cls.user_id = auth.get_current_user()["user_id"]

        cls.pid = add_product_get_id("RepProduct", "Test", 5.00, 100, "REP-001")

        # Create 3 test sales today
        for _ in range(3):
            _seed_sale(cls.user_id, cls.pid)

        cls.today = datetime.now().strftime("%Y-%m-%d")

    @classmethod
    def tearDownClass(cls):
        auth.logout()
        super().tearDownClass()

    # ── Daily report ─────────────────────────────────────────────────────────

    def test_daily_report_counts_todays_sales(self):
        data = daily_sales_report(self.today)
        self.assertGreaterEqual(data["transactions"], 3,
                                "Should see at least 3 sales today")
        self.assertGreater(data["revenue"], 0)

    def test_daily_report_structure(self):
        data = daily_sales_report(self.today)
        for key in ("transactions", "revenue", "total_discount",
                    "total_tax", "top_products"):
            self.assertIn(key, data)

    def test_daily_report_empty_date_returns_zeros(self):
        data = daily_sales_report("1990-01-01")
        self.assertEqual(data["transactions"], 0)
        self.assertEqual(data["revenue"],      0)

    # ── Weekly report ─────────────────────────────────────────────────────────

    def test_weekly_report_covers_period(self):
        data = weekly_sales_report("2000-01-01", self.today)
        self.assertGreaterEqual(data["transactions"], 3)
        self.assertIn("daily_breakdown", data)

    # ── Product performance ───────────────────────────────────────────────────

    def test_product_performance_lists_all_products(self):
        data = product_performance_report()
        self.assertGreater(len(data["products"]), 0)
        pid_list = [p["product_id"] for p in data["products"]]
        self.assertIn(self.pid, pid_list)

    def test_product_performance_units_sold_correct(self):
        data = product_performance_report()
        rep = next(p for p in data["products"] if p["product_id"] == self.pid)
        self.assertGreaterEqual(rep["units_sold"], 6)   # 3 sales × 2 qty

    # ── Inventory report ──────────────────────────────────────────────────────

    def test_inventory_report_includes_all_products(self):
        data = inventory_report()
        self.assertGreater(data["total_products"], 0)
        self.assertIn("products", data)
        self.assertIn("recent_log", data)

    # ── Cashier performance ───────────────────────────────────────────────────

    def test_cashier_performance_report_shows_users(self):
        data = cashier_performance_report()
        self.assertGreater(len(data["cashiers"]), 0)
        usernames = [c["cashier"] for c in data["cashiers"]]
        self.assertIn("admin", usernames)

    # ── Profit report ─────────────────────────────────────────────────────────

    def test_profit_report_revenue_positive(self):
        data = profit_report("2000-01-01", self.today)
        self.assertGreater(data["revenue"], 0)
        self.assertGreater(data["total_tax"], 0)

    # ── CSV export ────────────────────────────────────────────────────────────

    def test_export_product_performance_to_csv(self):
        data = product_performance_report()
        ok, result = export_report_to_csv(data)
        self.assertTrue(ok, result)
        self.assertTrue(os.path.isfile(result))
        self.assertGreater(os.path.getsize(result), 0)

    def test_export_daily_report_to_csv(self):
        data = daily_sales_report(self.today)
        ok, result = export_report_to_csv(data)
        # Daily report uses top_products list — may be empty if no items seeded
        if data["top_products"]:
            self.assertTrue(ok)
        else:
            self.assertFalse(ok)   # expected: no tabular data

    def test_export_inventory_report_to_csv(self):
        data = inventory_report()
        ok, result = export_report_to_csv(data)
        self.assertTrue(ok, result)
        self.assertTrue(os.path.isfile(result))


class TestBackupRestore(PosTestCase):
    """Scenario 5: Backup creation, listing, and restore."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Point backups to a temp directory so tests don't pollute /backups/
        import modules.backup as bmod
        cls._backup_dir = tempfile.mkdtemp()
        cls._orig_backup_dir = bmod.BACKUPS_DIR
        bmod.BACKUPS_DIR = cls._backup_dir

    @classmethod
    def tearDownClass(cls):
        import modules.backup as bmod
        bmod.BACKUPS_DIR = cls._orig_backup_dir
        import shutil
        shutil.rmtree(cls._backup_dir, ignore_errors=True)
        super().tearDownClass()

    def test_backup_creates_file(self):
        ok, path = backup_database()
        self.assertTrue(ok, path)
        self.assertTrue(os.path.isfile(path))
        self.assertGreater(os.path.getsize(path), 0)

    def test_list_backups_returns_entries(self):
        backup_database()   # ensure at least one exists
        backups = list_backups()
        self.assertGreater(len(backups), 0)

        b = backups[0]
        for key in ("filename", "filepath", "size_kb", "created"):
            self.assertIn(key, b)

    def test_backup_filename_contains_timestamp(self):
        ok, path = backup_database()
        self.assertTrue(ok)
        filename = os.path.basename(path)
        self.assertTrue(filename.startswith("backup_"),
                        f"Unexpected filename: {filename}")

    def test_restore_database_succeeds(self):
        ok_b, backup_path = backup_database()
        self.assertTrue(ok_b)

        ok_r, msg = restore_database(backup_path)
        self.assertTrue(ok_r, msg)
        # Safety backup must have been created
        backups = list_backups()
        names = [b["filename"] for b in backups]
        self.assertTrue(any("pre_restore" in n for n in names))

    def test_restore_nonexistent_file_fails(self):
        ok, msg = restore_database("/nonexistent/path/backup.db")
        self.assertFalse(ok)
        self.assertIn("not found", msg.lower())

    def test_delete_backup(self):
        ok, path = backup_database()
        self.assertTrue(ok)

        ok_d, _ = delete_backup(path)
        self.assertTrue(ok_d)
        self.assertFalse(os.path.exists(path))

    def test_export_all_to_csv_creates_folder(self):
        ok, folder = export_all_to_csv()
        self.assertTrue(ok, folder)
        self.assertTrue(os.path.isdir(folder))
        csv_files = os.listdir(folder)
        self.assertTrue(any(f.endswith(".csv") for f in csv_files))


class TestAuditLog(PosTestCase):
    """Transaction log is populated after key actions."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        auth.login("admin", "admin123")

    @classmethod
    def tearDownClass(cls):
        auth.logout()
        super().tearDownClass()

    def test_login_logged(self):
        logs = get_transaction_log()
        actions = [l["action"] for l in logs]
        self.assertIn("LOGIN", actions)

    def test_manual_log_action(self):
        from modules.backup import log_action
        log_action(1, "TEST_ACTION", "integration test entry")
        logs = get_transaction_log(limit=5)
        actions = [l["action"] for l in logs]
        self.assertIn("TEST_ACTION", actions)


if __name__ == "__main__":
    unittest.main()
