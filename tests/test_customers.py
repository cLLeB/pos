"""
E2E Scenario 3 (customer side): Registration, lookup, purchase history, loyalty.
"""

import unittest
from tests.test_base import PosTestCase, add_product_get_id
from modules.customers import (
    register_customer, update_customer, delete_customer,
    get_all_customers, get_customer_by_id, get_customer_by_phone,
    search_customers, get_purchase_history, get_customer_stats,
    add_loyalty_points, redeem_loyalty_points, get_loyalty_balance,
)
from modules import auth
from modules.products import add_product
from modules.sales import create_sale


class TestCustomerCRUD(PosTestCase):

    def test_register_customer_success(self):
        ok, msg, cid = register_customer("Alice", "+254711000001", "alice@x.com")
        self.assertTrue(ok, msg)
        self.assertGreater(cid, 0)

    def test_register_duplicate_phone_rejected(self):
        register_customer("Bob", "+254711000002")
        ok, msg, cid = register_customer("Bob2", "+254711000002")
        self.assertFalse(ok)
        self.assertEqual(cid, 0)

    def test_register_missing_name_rejected(self):
        ok, msg, _ = register_customer("", "+254711000099")
        self.assertFalse(ok)

    def test_register_missing_phone_rejected(self):
        ok, msg, _ = register_customer("NoPhone", "")
        self.assertFalse(ok)

    def test_get_customer_by_phone(self):
        register_customer("Carol", "+254711000003")
        c = get_customer_by_phone("+254711000003")
        self.assertIsNotNone(c)
        self.assertEqual(c["name"], "Carol")

    def test_update_customer(self):
        _, _, cid = register_customer("Dave", "+254711000004")
        ok, msg = update_customer(cid, "David Updated", "+254711000004")
        self.assertTrue(ok, msg)

        c = get_customer_by_id(cid)
        self.assertEqual(c["name"], "David Updated")

    def test_delete_customer_without_sales(self):
        _, _, cid = register_customer("Temp", "+254711000005")
        ok, msg = delete_customer(cid)
        self.assertTrue(ok, msg)
        self.assertIsNone(get_customer_by_id(cid))

    def test_search_by_name(self):
        register_customer("SearchableEve", "+254711000006")
        results = search_customers("SearchableEve")
        self.assertTrue(any("SearchableEve" in r["name"] for r in results))

    def test_search_by_phone(self):
        register_customer("Frank", "+254799888777")
        results = search_customers("888777")
        self.assertTrue(len(results) > 0)


class TestLoyaltyPoints(PosTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        auth.login("cashier1", "cashier123")
        cls.user_id = auth.get_current_user()["user_id"]
        cls.pid = add_product_get_id("LoyItem", "Test", 10.00, 200, "LOY-001")
        _, _, cls.cid = register_customer("LoyCustomer", "+254700999888")

    @classmethod
    def tearDownClass(cls):
        auth.logout()
        super().tearDownClass()

    def test_earn_points_from_sale(self):
        # $50 purchase → 5 points (1 per $10)
        cart = [{"product_id": self.pid, "name": "LoyItem",
                 "price": 10.00, "quantity": 5}]
        before = get_loyalty_balance(self.cid)

        ok, _, sale_id = create_sale(
            self.user_id, cart, "Cash",
            discount=0.0, tax_rate=0.0, customer_id=self.cid
        )
        self.assertTrue(ok)

        after = get_loyalty_balance(self.cid)
        self.assertGreater(after, before)

    def test_add_loyalty_points_directly(self):
        before = get_loyalty_balance(self.cid)
        earned = add_loyalty_points(self.cid, 100.00)   # $100 → 10 pts
        self.assertEqual(earned, 10)
        self.assertEqual(get_loyalty_balance(self.cid), before + 10)

    def test_redeem_loyalty_points(self):
        add_loyalty_points(self.cid, 50.00)   # ensure some points
        before = get_loyalty_balance(self.cid)
        redeem = min(5, before)

        ok, msg, discount = redeem_loyalty_points(self.cid, redeem)
        self.assertTrue(ok, msg)
        self.assertAlmostEqual(discount, redeem * 0.10, places=2)
        self.assertEqual(get_loyalty_balance(self.cid), before - redeem)

    def test_redeem_more_than_balance_rejected(self):
        balance = get_loyalty_balance(self.cid)
        ok, msg, discount = redeem_loyalty_points(self.cid, balance + 100)
        self.assertFalse(ok)
        self.assertEqual(discount, 0.0)

    def test_redeem_zero_points_rejected(self):
        ok, msg, _ = redeem_loyalty_points(self.cid, 0)
        self.assertFalse(ok)


class TestPurchaseHistory(PosTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        auth.login("cashier1", "cashier123")
        cls.user_id = auth.get_current_user()["user_id"]
        cls.pid = add_product_get_id("HistItem", "Test", 3.00, 100, "HIST-001")
        _, _, cls.cid = register_customer("HistCustomer", "+254700111222")

        # Create 2 sales for this customer
        for _ in range(2):
            cart = [{"product_id": cls.pid, "name": "HistItem",
                     "price": 3.00, "quantity": 1}]
            create_sale(cls.user_id, cart, "Cash", customer_id=cls.cid)

    @classmethod
    def tearDownClass(cls):
        auth.logout()
        super().tearDownClass()

    def test_purchase_history_returns_sales(self):
        history = get_purchase_history(self.cid)
        self.assertGreaterEqual(len(history), 2)

    def test_purchase_history_has_items(self):
        history = get_purchase_history(self.cid)
        for sale in history:
            self.assertIn("items", sale)
            self.assertGreater(len(sale["items"]), 0)

    def test_customer_stats(self):
        stats = get_customer_stats(self.cid)
        self.assertGreaterEqual(stats["visits"], 2)
        self.assertGreater(stats["total_spend"], 0)
        self.assertGreater(stats["avg_basket"],  0)


if __name__ == "__main__":
    unittest.main()
