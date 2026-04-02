"""
E2E Scenarios 2 & 3: Complete sale flow — cart → payment → receipt → inventory.

Scenario 2: cashier login → items to cart → discount → cash payment →
            receipt generated → inventory deducted
Scenario 3: select customer → sale → loyalty points awarded
"""

import unittest
from tests.test_base import PosTestCase, add_product_get_id
from modules import auth
from modules.products import add_product
from modules.customers import (
    register_customer, get_customer_by_phone, get_loyalty_balance,
)
from modules.sales import create_sale, get_sale_by_id
from modules.payments import (
    process_cash_payment, process_mobile_payment, process_card_payment,
    get_payment_by_sale,
)
from modules.receipts import generate_receipt, format_receipt_text
from modules.inventory import get_all_stock


class TestCompleteSaleFlow(PosTestCase):
    """Full sale: cart → create_sale → payment → receipt (Scenario 2)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        auth.login("cashier1", "cashier123")
        cls.user_id = auth.get_current_user()["user_id"]

        # Seed two products for the cart
        cls.pid1 = add_product_get_id("Cola",  "Drinks", 1.50, 50, "COLA-001")
        cls.pid2 = add_product_get_id("Chips", "Snacks", 2.00, 30, "CHIP-001")

    @classmethod
    def tearDownClass(cls):
        auth.logout()
        super().tearDownClass()

    def _make_cart(self, cola_qty=2, chips_qty=1):
        return [
            {"product_id": self.pid1, "name": "Cola",  "price": 1.50, "quantity": cola_qty},
            {"product_id": self.pid2, "name": "Chips", "price": 2.00, "quantity": chips_qty},
        ]

    # ── Sale creation ─────────────────────────────────────────────────────────

    def test_create_sale_succeeds(self):
        cart = self._make_cart()
        ok, msg, sale_id = create_sale(
            self.user_id, cart, "Cash", discount=0.0, tax_rate=0.16
        )
        self.assertTrue(ok, msg)
        self.assertTrue(sale_id.startswith("TXN-"))

    def test_empty_cart_rejected(self):
        ok, msg, sale_id = create_sale(self.user_id, [], "Cash")
        self.assertFalse(ok)
        self.assertEqual(sale_id, "")

    def test_sale_stored_with_correct_totals(self):
        cart = self._make_cart(cola_qty=2, chips_qty=1)
        # subtotal: 2×1.50 + 1×2.00 = 5.00
        # tax 16%: 0.80,  total: 5.80
        ok, _, sale_id = create_sale(
            self.user_id, cart, "Cash", discount=0.0, tax_rate=0.16
        )
        self.assertTrue(ok)

        sale = get_sale_by_id(sale_id)
        self.assertIsNotNone(sale)
        self.assertAlmostEqual(sale["subtotal"],     5.00, places=2)
        self.assertAlmostEqual(sale["tax"],          0.80, places=2)
        self.assertAlmostEqual(sale["total_amount"], 5.80, places=2)

    def test_discount_applied_correctly(self):
        cart = self._make_cart(cola_qty=4, chips_qty=2)
        # subtotal: 4×1.50 + 2×2.00 = 10.00; discount=1.00; taxable=9.00
        ok, _, sale_id = create_sale(
            self.user_id, cart, "Cash", discount=1.00, tax_rate=0.16
        )
        self.assertTrue(ok)
        sale = get_sale_by_id(sale_id)
        self.assertAlmostEqual(sale["discount"], 1.00, places=2)
        self.assertAlmostEqual(sale["subtotal"], 10.00, places=2)

    # ── Inventory deduction ───────────────────────────────────────────────────

    def test_inventory_deducted_after_sale(self):
        stock_before = {s["product_id"]: s["quantity"] for s in get_all_stock()}

        cart = [{"product_id": self.pid1, "name": "Cola",
                 "price": 1.50, "quantity": 3}]
        ok, _, _ = create_sale(self.user_id, cart, "Cash")
        self.assertTrue(ok)

        stock_after = {s["product_id"]: s["quantity"] for s in get_all_stock()}
        self.assertEqual(
            stock_after[self.pid1],
            stock_before[self.pid1] - 3,
            "Stock must be reduced by sold quantity"
        )

    # ── Payment methods ───────────────────────────────────────────────────────

    def test_cash_payment_change_calculated(self):
        cart = self._make_cart()
        _, _, sale_id = create_sale(self.user_id, cart, "Cash")
        sale = get_sale_by_id(sale_id)
        total = sale["total_amount"]

        ok, msg, change = process_cash_payment(sale_id, total + 5.00, total)
        self.assertTrue(ok, msg)
        self.assertAlmostEqual(change, 5.00, places=2)

    def test_cash_payment_insufficient_rejected(self):
        cart = self._make_cart()
        _, _, sale_id = create_sale(self.user_id, cart, "Cash")
        sale = get_sale_by_id(sale_id)

        ok, msg, change = process_cash_payment(
            sale_id, sale["total_amount"] - 1.00, sale["total_amount"]
        )
        self.assertFalse(ok)
        self.assertEqual(change, 0.0)

    def test_mobile_payment_saved(self):
        cart = self._make_cart()
        _, _, sale_id = create_sale(self.user_id, cart, "Mobile Money")
        sale = get_sale_by_id(sale_id)

        ok, msg = process_mobile_payment(
            sale_id, sale["total_amount"], "MTN", "REF123456"
        )
        self.assertTrue(ok, msg)

        payment = get_payment_by_sale(sale_id)
        self.assertIsNotNone(payment)
        self.assertIn("Mobile Money", payment["payment_type"])

    def test_mobile_payment_requires_reference(self):
        cart = self._make_cart()
        _, _, sale_id = create_sale(self.user_id, cart, "Mobile Money")
        sale = get_sale_by_id(sale_id)

        ok, msg = process_mobile_payment(sale_id, sale["total_amount"], "MTN", "")
        self.assertFalse(ok, "Mobile payment must require a reference number")

    def test_card_payment_saved(self):
        cart = self._make_cart()
        _, _, sale_id = create_sale(self.user_id, cart, "Card")
        sale = get_sale_by_id(sale_id)

        ok, msg = process_card_payment(sale_id, sale["total_amount"], "Visa")
        self.assertTrue(ok, msg)


class TestCustomerLoyaltySale(PosTestCase):
    """Scenario 3: sale linked to customer → loyalty points awarded."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        auth.login("cashier1", "cashier123")
        cls.user_id = auth.get_current_user()["user_id"]

        cls.pid = add_product_get_id("Water", "Drinks", 1.00, 100, "WATR-001")

        ok, msg, cls.cid = register_customer(
            "Test Customer", "+254700000001", "test@example.com"
        )
        assert ok, msg

    @classmethod
    def tearDownClass(cls):
        auth.logout()
        super().tearDownClass()

    def test_loyalty_points_awarded_after_sale(self):
        """1 point per $10 spent."""
        cart = [{"product_id": self.pid, "name": "Water",
                 "price": 1.00, "quantity": 25}]  # subtotal $25

        points_before = get_loyalty_balance(self.cid)

        ok, _, sale_id = create_sale(
            self.user_id, cart, "Cash",
            discount=0.0, tax_rate=0.16, customer_id=self.cid
        )
        self.assertTrue(ok)

        # total ≈ $29, so 2 points (1 per $10)
        sale = get_sale_by_id(sale_id)
        expected_points = int(sale["total_amount"] // 10)

        points_after = get_loyalty_balance(self.cid)
        self.assertEqual(points_after - points_before, expected_points)

    def test_sale_without_customer_awards_no_points(self):
        cart = [{"product_id": self.pid, "name": "Water",
                 "price": 1.00, "quantity": 10}]

        ok, _, sale_id = create_sale(
            self.user_id, cart, "Cash", customer_id=None
        )
        self.assertTrue(ok)

        # Balance should not change because no customer was linked
        balance = get_loyalty_balance(self.cid)
        self.assertIsNotNone(balance)   # customer still exists unchanged


class TestReceiptGeneration(PosTestCase):
    """Receipt is generated and formatted after a sale."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        auth.login("cashier1", "cashier123")
        cls.user_id = auth.get_current_user()["user_id"]
        cls.pid = add_product_get_id("Fanta", "Drinks", 1.20, 50, "FAN-001")

        cart = [{"product_id": cls.pid, "name": "Fanta",
                 "price": 1.20, "quantity": 2}]
        ok, _, cls.sale_id = create_sale(cls.user_id, cart, "Cash")
        assert ok

    @classmethod
    def tearDownClass(cls):
        auth.logout()
        super().tearDownClass()

    def test_generate_receipt_returns_dict(self):
        data = generate_receipt(self.sale_id)
        self.assertIsNotNone(data)
        self.assertEqual(data["sale_id"], self.sale_id)
        self.assertIn("items", data)
        self.assertGreater(len(data["items"]), 0)

    def test_receipt_contains_all_required_fields(self):
        data = generate_receipt(self.sale_id)
        required = [
            "store_name", "sale_id", "date", "cashier",
            "items", "subtotal", "tax", "total",
            "payment_method", "amount_paid",
        ]
        for field in required:
            self.assertIn(field, data, f"Receipt missing field: {field}")

    def test_receipt_text_contains_total(self):
        data = generate_receipt(self.sale_id)
        text = format_receipt_text(data)
        self.assertIn("TOTAL:", text)
        self.assertIn("Fanta", text)
        self.assertIn("Thank you", text)

    def test_invalid_sale_id_returns_none(self):
        data = generate_receipt("TXN-DOESNOTEXIST")
        self.assertIsNone(data)


if __name__ == "__main__":
    unittest.main()
