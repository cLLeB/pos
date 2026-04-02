"""
E2E Scenarios 1 & 7: Product management + inventory tracking.

Covers:
  - Admin adds product → product appears in list
  - Edit and delete product
  - Search by name / barcode
  - Low-stock alert when qty < threshold (Scenario 7)
  - Stock deduction and adjustment logging
"""

import unittest
from tests.test_base import PosTestCase, add_product_get_id
from modules.products import (
    add_product, update_product, delete_product,
    get_all_products, search_product, get_product_by_barcode,
)
from modules.inventory import (
    update_stock, check_low_stock, get_all_stock,
    restock_product, get_inventory_log,
)
from database.db_setup import get_setting, update_setting


class TestProductCRUD(PosTestCase):
    """Full CRUD lifecycle for a product."""

    def _add_test_product(self, name="TestBeer", qty=20):
        return add_product_get_id(name, "Beverages", 2.50, qty, f"BC-{name}")

    def test_add_product_appears_in_list(self):
        pid = self._add_test_product("Sprite")
        products = get_all_products()
        names = [p["product_name"] for p in products]
        self.assertIn("Sprite", names)

    def test_add_product_duplicate_barcode_rejected(self):
        add_product("Item A", "Cat", 1.00, 10, "UNIQUE-BC")
        ok, msg = add_product("Item B", "Cat", 2.00, 5, "UNIQUE-BC")
        self.assertFalse(ok, "Duplicate barcode must be rejected")

    def test_add_product_negative_price_rejected(self):
        ok, msg = add_product("Bad", "Cat", -1.00, 10, "BC-BAD")
        self.assertFalse(ok)

    def test_update_product(self):
        pid = self._add_test_product("UpdateMe")
        ok, msg = update_product(pid, "UpdatedName", "NewCat", 9.99, 50, "BC-UPD")
        self.assertTrue(ok, msg)
        products = get_all_products()
        updated = next((p for p in products if p["product_id"] == pid), None)
        self.assertIsNotNone(updated)
        self.assertEqual(updated["product_name"], "UpdatedName")
        self.assertEqual(updated["price"], 9.99)

    def test_delete_product(self):
        pid = self._add_test_product("DeleteMe")
        ok, msg = delete_product(pid)
        self.assertTrue(ok, msg)
        products = get_all_products()
        self.assertNotIn(pid, [p["product_id"] for p in products])

    def test_search_by_name(self):
        self._add_test_product("SearchTarget")
        results = search_product("SearchTarget")
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0]["product_name"], "SearchTarget")

    def test_search_by_barcode(self):
        self._add_test_product("BarcodeItem")
        result = get_product_by_barcode("BC-BarcodeItem")
        self.assertIsNotNone(result)
        self.assertEqual(result["product_name"], "BarcodeItem")

    def test_search_partial_name(self):
        self._add_test_product("PartialSearchable")
        results = search_product("Partial")
        self.assertTrue(any("PartialSearchable" in r["product_name"] for r in results))


class TestInventoryManagement(PosTestCase):
    """Stock tracking, adjustments, and low-stock alerts (Scenario 7)."""

    def _add_product(self, name, qty):
        return add_product_get_id(name, "Test", 5.00, qty, f"INV-{name}")

    def test_restock_increases_quantity(self):
        pid = self._add_product("RestockItem", 10)
        ok, msg = restock_product(pid, 15)
        self.assertTrue(ok, msg)

        stock = get_all_stock()
        item = next(s for s in stock if s["product_id"] == pid)
        self.assertEqual(item["quantity"], 25)

    def test_stock_adjustment_logged(self):
        pid = self._add_product("LoggedItem", 50)
        update_stock(pid, -10, "sold 10 units")

        log = get_inventory_log()
        entry = next((e for e in log if e["product_id"] == pid), None)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["adjustment"], -10)

    def test_low_stock_alert_triggers(self):
        """Scenario 7: alert appears when qty <= threshold."""
        update_setting("low_stock_threshold", "5")

        pid = self._add_product("LowStockItem", 3)   # below threshold

        low = check_low_stock()
        ids = [p["product_id"] for p in low]
        self.assertIn(pid, ids, "Product with qty=3 must appear in low-stock alert")

    def test_healthy_stock_not_in_alert(self):
        update_setting("low_stock_threshold", "5")

        pid = self._add_product("HealthyItem", 100)

        low = check_low_stock()
        ids = [p["product_id"] for p in low]
        self.assertNotIn(pid, ids)

    def test_status_field_reflects_stock_level(self):
        update_setting("low_stock_threshold", "5")

        pid_ok  = self._add_product("StockOK",  50)
        pid_low = self._add_product("StockLow",  2)
        pid_out = self._add_product("StockOut",  0)

        stock = {s["product_id"]: s for s in get_all_stock()}
        self.assertEqual(stock[pid_ok]["status"],  "ok")
        self.assertEqual(stock[pid_low]["status"], "low")
        self.assertEqual(stock[pid_out]["status"], "out")

    def test_cannot_reduce_stock_below_zero(self):
        pid = self._add_product("MinStock", 5)
        ok, msg = update_stock(pid, -10, "over-deduct")
        self.assertFalse(ok, "Stock must not go below zero")


if __name__ == "__main__":
    unittest.main()
