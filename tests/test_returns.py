"""Tests for modules/returns.py

Helper functions call get_connection() directly (not self.conn) because
PosTestCase is a class-level fixture — it patches DB_PATH in setUpClass
so every subsequent get_connection() call hits the temp DB automatically.
"""
import unittest
from tests.test_base import PosTestCase
from modules import returns, sales


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_product(name="Widget", price=10.0, qty=20):
    from database.db_setup import get_connection
    conn = get_connection()
    conn.execute(
        "INSERT INTO Products (product_name, category, price, quantity, barcode) "
        "VALUES (?, 'Test', ?, ?, ?)",
        (name, price, qty, f"BC-{name}")
    )
    conn.commit()
    pid = conn.execute(
        "SELECT product_id FROM Products WHERE barcode=?", (f"BC-{name}",)
    ).fetchone()["product_id"]
    conn.close()
    return pid


def _make_sale(user_id, product_id, qty=2, price=10.0):
    """Creates a sale via the sales module and returns (success, msg, sale_id)."""
    cart = [{"product_id": product_id, "quantity": qty, "price": price}]
    return sales.create_sale(user_id, cart, "cash")


def _get_sale_item_id(sale_id):
    from database.db_setup import get_connection
    conn = get_connection()
    row = conn.execute(
        "SELECT sale_item_id FROM Sales_Items WHERE sale_id=?", (sale_id,)
    ).fetchone()
    conn.close()
    return row["sale_item_id"]


def _get_stock(product_id):
    from database.db_setup import get_connection
    conn = get_connection()
    qty = conn.execute(
        "SELECT quantity FROM Products WHERE product_id=?", (product_id,)
    ).fetchone()["quantity"]
    conn.close()
    return qty


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------

class TestGetReturnableItems(PosTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pid = _make_product("RetItem", qty=30)
        _, _, cls.sale_id = _make_sale(1, cls.pid, qty=3)
        cls.siid = _get_sale_item_id(cls.sale_id)

    def test_full_qty_returnable_on_fresh_sale(self):
        items = returns.get_returnable_items(self.sale_id)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["returnable_qty"], 3)
        self.assertEqual(items[0]["returned_qty"], 0)

    def test_invalid_sale_id_returns_empty(self):
        self.assertEqual(returns.get_returnable_items("FAKE-SALE-ID"), [])


class TestProcessReturn(PosTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pid = _make_product("RetProc", qty=50)
        _, _, cls.sale_id = _make_sale(1, cls.pid, qty=4)
        cls.siid = _get_sale_item_id(cls.sale_id)

    def _item(self, qty):
        return [{"sale_item_id": self.siid, "product_id": self.pid,
                 "quantity": qty, "price": 10.0}]

    def test_process_return_succeeds(self):
        pid = _make_product("RetSucc", qty=10)
        _, _, sid = _make_sale(1, pid, qty=2)
        siid = _get_sale_item_id(sid)
        success, msg, rid = returns.process_return(
            sid, [{"sale_item_id": siid, "product_id": pid,
                   "quantity": 1, "price": 10.0}],
            "Damaged", 1
        )
        self.assertTrue(success, msg)
        self.assertTrue(rid.startswith("RTN-"))

    def test_return_restores_inventory(self):
        pid = _make_product("RetStock", qty=20)
        _, _, sid = _make_sale(1, pid, qty=3)
        siid = _get_sale_item_id(sid)
        stock_before = _get_stock(pid)
        returns.process_return(
            sid, [{"sale_item_id": siid, "product_id": pid,
                   "quantity": 2, "price": 10.0}],
            "Wrong item", 1
        )
        self.assertEqual(_get_stock(pid), stock_before + 2)

    def test_return_calculates_correct_refund_total(self):
        pid = _make_product("RetCalc", qty=20)
        _, _, sid = _make_sale(1, pid, qty=5)
        siid = _get_sale_item_id(sid)
        _, _, rid = returns.process_return(
            sid, [{"sale_item_id": siid, "product_id": pid,
                   "quantity": 3, "price": 10.0}],
            "Too many", 1
        )
        ret = returns.get_return_by_id(rid)
        self.assertAlmostEqual(ret["total_refund"], 30.0)

    def test_cannot_return_more_than_purchased(self):
        pid = _make_product("RetOver", qty=10)
        _, _, sid = _make_sale(1, pid, qty=2)
        siid = _get_sale_item_id(sid)
        success, msg, _ = returns.process_return(
            sid, [{"sale_item_id": siid, "product_id": pid,
                   "quantity": 99, "price": 10.0}],
            "Overage test", 1
        )
        self.assertFalse(success)
        self.assertIn("exceed", msg.lower())

    def test_return_with_restock_false_does_not_restore_inventory(self):
        pid = _make_product("RetNoStock", qty=10)
        _, _, sid = _make_sale(1, pid, qty=3)
        siid = _get_sale_item_id(sid)
        stock_before = _get_stock(pid)
        returns.process_return(
            sid, [{"sale_item_id": siid, "product_id": pid,
                   "quantity": 2, "price": 10.0}],
            "Destroyed", 1, restock=False
        )
        self.assertEqual(_get_stock(pid), stock_before)

    def test_return_logs_inventory_adjustment(self):
        pid = _make_product("RetLog", qty=10)
        _, _, sid = _make_sale(1, pid, qty=2)
        siid = _get_sale_item_id(sid)
        returns.process_return(
            sid, [{"sale_item_id": siid, "product_id": pid,
                   "quantity": 1, "price": 10.0}],
            "Test log", 1
        )
        from database.db_setup import get_connection
        conn = get_connection()
        log = conn.execute(
            "SELECT reason FROM Inventory WHERE product_id=? "
            "ORDER BY inventory_id DESC LIMIT 1",
            (pid,)
        ).fetchone()
        conn.close()
        self.assertIn("return", log["reason"].lower())

    def test_invalid_sale_id_fails(self):
        success, msg, _ = returns.process_return(
            "FAKE-ID",
            [{"sale_item_id": 999, "product_id": self.pid,
              "quantity": 1, "price": 10.0}],
            "Bad sale", 1
        )
        self.assertFalse(success)


class TestGetReturnById(PosTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        pid = _make_product("RetById", qty=10)
        _, _, sid = _make_sale(1, pid, qty=2)
        siid = _get_sale_item_id(sid)
        _, _, cls.rid = returns.process_return(
            sid, [{"sale_item_id": siid, "product_id": pid,
                   "quantity": 1, "price": 10.0}],
            "Test reason", 1
        )

    def test_returns_full_record_with_items(self):
        ret = returns.get_return_by_id(self.rid)
        self.assertIsNotNone(ret)
        self.assertEqual(ret["return_id"], self.rid)
        self.assertIn("items", ret)
        self.assertEqual(len(ret["items"]), 1)

    def test_invalid_id_returns_none(self):
        self.assertIsNone(returns.get_return_by_id("RTN-FAKE"))


class TestGetRecentReturns(PosTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        pid = _make_product("RetRecent", qty=10)
        _, _, sid = _make_sale(1, pid, qty=3)
        siid = _get_sale_item_id(sid)
        returns.process_return(
            sid, [{"sale_item_id": siid, "product_id": pid,
                   "quantity": 1, "price": 10.0}],
            "Reason", 1
        )

    def test_recent_returns_is_list(self):
        self.assertIsInstance(returns.get_recent_returns(limit=10), list)

    def test_recent_returns_has_entries(self):
        self.assertGreaterEqual(len(returns.get_recent_returns(limit=10)), 1)


class TestDailyReturnSummary(PosTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from datetime import date
        cls.today = date.today().strftime("%Y-%m-%d")
        pid = _make_product("RetSumm", qty=10)
        _, _, sid = _make_sale(1, pid, qty=3)
        siid = _get_sale_item_id(sid)
        returns.process_return(
            sid, [{"sale_item_id": siid, "product_id": pid,
                   "quantity": 2, "price": 10.0}],
            "Summary test", 1
        )

    def test_summary_has_required_keys(self):
        s = returns.get_daily_return_summary(self.today)
        for key in ("date", "count", "total_refunded", "items_restocked"):
            self.assertIn(key, s)

    def test_summary_count_is_positive(self):
        s = returns.get_daily_return_summary(self.today)
        self.assertGreaterEqual(s["count"], 1)
        self.assertGreater(s["total_refunded"], 0)


class TestPartialReturnReducesReturnableQty(PosTestCase):
    """Verifies the returnable-qty decreases after a partial return."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pid = _make_product("RetPartial", qty=20)
        _, _, cls.sid = _make_sale(1, cls.pid, qty=5)
        cls.siid = _get_sale_item_id(cls.sid)
        returns.process_return(
            cls.sid,
            [{"sale_item_id": cls.siid, "product_id": cls.pid,
              "quantity": 2, "price": 10.0}],
            "Partial", 1
        )

    def test_returnable_qty_decreases(self):
        items = returns.get_returnable_items(self.sid)
        self.assertEqual(items[0]["returnable_qty"], 3)
        self.assertEqual(items[0]["returned_qty"], 2)

    def test_cannot_exceed_remaining_returnable(self):
        success, msg, _ = returns.process_return(
            self.sid,
            [{"sale_item_id": self.siid, "product_id": self.pid,
              "quantity": 4, "price": 10.0}],
            "Second return", 1
        )
        self.assertFalse(success)


if __name__ == "__main__":
    unittest.main()
