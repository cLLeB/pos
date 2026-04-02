# POS Innovations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two production-grade, deeply polished features — Returns & Refunds and Smart Sales Intelligence — to an existing complete Python/Tkinter/SQLite POS system.

**Architecture:** Each feature follows the existing three-layer pattern: (1) a new module in `modules/` containing all business logic and DB access, (2) a new UI panel in `ui/` consuming only the module's public API, (3) tests in `tests/` using `PosTestCase` from `test_base.py`. Both features are integrated into the existing `AdminDashboard` sidebar and `HomePanel` summary cards.

**Tech Stack:** Python 3.10+, Tkinter (stdlib), SQLite (stdlib), unittest (stdlib), zero external dependencies.

**Key existing conventions (follow exactly):**
- DB connections: `from database.db_setup import get_connection` — returns `sqlite3.Connection` with row factory set
- Timestamps: `from utils.helpers import current_timestamp` (returns `"YYYY-MM-DD HH:MM:SS"`)
- Test base class: `from tests.test_base import PosTestCase` — class-level temp DB via `setUpClass/tearDownClass`; tests do NOT use `self.conn` — helpers call `get_connection()` directly
- UI colour palette: `from ui.login_screen import COLORS`
- Settings: `from database.db_setup import get_setting`

---

## File Map

### Feature 1 — Returns & Refunds

| Action | File | Responsibility |
|--------|------|----------------|
| MODIFY | `database/db_setup.py` | Add `Returns` and `Return_Items` tables |
| CREATE | `modules/returns.py` | All return/refund business logic |
| MODIFY | `modules/receipts.py` | Add `save_return_receipt_to_file(return_id)` |
| MODIFY | `modules/backup.py` | Include Returns and Return_Items in CSV export |
| CREATE | `ui/returns_ui.py` | Full returns panel (search → select items → confirm → receipt) |
| MODIFY | `ui/admin_dashboard.py` | Add Returns nav item (manager + admin only) |
| MODIFY | `ui/home_panel.py` | Add "Returns Today" stat card |
| CREATE | `tests/test_returns.py` | Full test suite |

### Feature 2 — Smart Sales Intelligence

| Action | File | Responsibility |
|--------|------|----------------|
| CREATE | `modules/intelligence.py` | Analytics engine (velocity, predictions, ABC, trends, forecast) |
| CREATE | `ui/intelligence_ui.py` | Multi-tab intelligence dashboard (6 tabs) |
| MODIFY | `ui/admin_dashboard.py` | Add Intelligence nav item (admin only) |
| MODIFY | `ui/home_panel.py` | Add "Critical Stockouts" alert card |
| CREATE | `tests/test_intelligence.py` | Full test suite |

---

## All commands run from:
```
cd "C:\Users\kyere\Downloads\Structured Programming Project\POS_System"
```

---

# FEATURE 1: RETURNS & REFUNDS

---

## Task 1: Extend the Database Schema

**Files:**
- Modify: `database/db_setup.py`

- [ ] **Step 1: Open `database/db_setup.py`. In `initialize_database()`, locate the `Payments` table `CREATE` statement. Add the two new tables immediately after it:**

```python
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Returns (
            return_id    TEXT PRIMARY KEY,
            sale_id      TEXT NOT NULL REFERENCES Sales(sale_id),
            date         TEXT NOT NULL,
            user_id      INTEGER NOT NULL REFERENCES Users(user_id),
            customer_id  INTEGER REFERENCES Customers(customer_id),
            reason       TEXT NOT NULL,
            total_refund REAL NOT NULL DEFAULT 0,
            status       TEXT NOT NULL DEFAULT 'completed'
                         CHECK(status IN ('completed', 'pending'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Return_Items (
            return_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            return_id      TEXT    NOT NULL REFERENCES Returns(return_id),
            sale_item_id   INTEGER NOT NULL REFERENCES Sales_Items(sale_item_id),
            product_id     INTEGER NOT NULL REFERENCES Products(product_id),
            quantity       INTEGER NOT NULL CHECK(quantity > 0),
            price          REAL    NOT NULL,
            restocked      INTEGER NOT NULL DEFAULT 1
        )
    """)
```

- [ ] **Step 2: Verify the app still starts with no errors:**

```bash
python main.py
```
Expected: Login screen appears. No traceback. Close the window.

- [ ] **Step 3: Commit:**

```bash
git add database/db_setup.py
git commit -m "feat: add Returns and Return_Items tables to schema"
```

---

## Task 2: Write Failing Tests for the Returns Module

**Files:**
- Create: `tests/test_returns.py`

- [ ] **Step 1: Create `tests/test_returns.py`:**

```python
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
        # Use a fresh sale to avoid cross-test qty conflicts
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
        # Return 2 of 5
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
              "quantity": 4, "price": 10.0}],   # only 3 remaining
            "Second return", 1
        )
        self.assertFalse(success)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to confirm tests fail (module missing):**

```bash
python -m unittest tests.test_returns -v 2>&1 | head -5
```
Expected output includes: `ModuleNotFoundError: No module named 'modules.returns'`

- [ ] **Step 3: Commit the failing tests:**

```bash
git add tests/test_returns.py
git commit -m "test: add failing tests for returns module (TDD red phase)"
```

---

## Task 3: Implement `modules/returns.py`

**Files:**
- Create: `modules/returns.py`

- [ ] **Step 1: Create `modules/returns.py`:**

```python
"""
Returns & Refunds Module
========================
Handles product returns, inventory restoration, and refund tracking.

Public API
----------
get_returnable_items(sale_id)                           -> list[dict]
process_return(sale_id, items, reason, user_id,
               restock=True)                            -> (bool, str, str)
get_return_by_id(return_id)                             -> dict | None
get_returns_by_sale(sale_id)                            -> list[dict]
get_recent_returns(limit=50)                            -> list[dict]
get_daily_return_summary(date_str)                      -> dict
"""

import uuid
from database.db_setup import get_connection
from utils.helpers import current_timestamp


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_returnable_items(sale_id: str) -> list:
    """
    Returns the items from *sale_id* that still have returnable quantity.

    returnable_qty = original_qty - already_returned_qty

    Each dict: sale_item_id, product_id, product_name, original_qty,
               returned_qty, returnable_qty, price
    """
    conn = get_connection()
    try:
        if not conn.execute(
            "SELECT 1 FROM Sales WHERE sale_id=?", (sale_id,)
        ).fetchone():
            return []

        items = conn.execute(
            """
            SELECT si.sale_item_id,
                   si.product_id,
                   p.product_name,
                   si.quantity AS original_qty,
                   si.price
            FROM   Sales_Items si
            JOIN   Products p ON p.product_id = si.product_id
            WHERE  si.sale_id = ?
            """,
            (sale_id,)
        ).fetchall()

        result = []
        for row in items:
            already = conn.execute(
                """
                SELECT COALESCE(SUM(ri.quantity), 0)
                FROM   Return_Items ri
                JOIN   Returns r ON r.return_id = ri.return_id
                WHERE  ri.sale_item_id = ?
                  AND  r.status = 'completed'
                """,
                (row["sale_item_id"],)
            ).fetchone()[0]

            result.append({
                "sale_item_id":  row["sale_item_id"],
                "product_id":    row["product_id"],
                "product_name":  row["product_name"],
                "original_qty":  row["original_qty"],
                "returned_qty":  already,
                "returnable_qty": row["original_qty"] - already,
                "price":         row["price"],
            })
        return result
    finally:
        conn.close()


def process_return(
    sale_id: str,
    return_items: list,
    reason: str,
    user_id: int,
    restock: bool = True,
) -> tuple:
    """
    Creates a completed return record and optionally restores stock.

    Parameters
    ----------
    sale_id      : original sale identifier
    return_items : list[dict] — each must have:
                   {sale_item_id, product_id, quantity, price}
    reason       : free-text return reason (required)
    user_id      : user processing the return
    restock      : True  → restore quantity to Products (default)
                   False → item is damaged / write-off, no restock

    Returns
    -------
    (success: bool, message: str, return_id: str)
    return_id is "" on failure.
    """
    if not return_items:
        return False, "No items selected for return.", ""

    conn = get_connection()
    try:
        sale = conn.execute(
            "SELECT sale_id, customer_id FROM Sales WHERE sale_id=?",
            (sale_id,)
        ).fetchone()
        if not sale:
            return False, f"Sale '{sale_id}' not found.", ""

        # ── Validate all quantities before touching any data ──────────────
        for item in return_items:
            original_row = conn.execute(
                "SELECT quantity FROM Sales_Items WHERE sale_item_id=?",
                (item["sale_item_id"],)
            ).fetchone()
            if not original_row:
                return (
                    False,
                    f"Sale item {item['sale_item_id']} not found.",
                    ""
                )
            already = conn.execute(
                """
                SELECT COALESCE(SUM(ri.quantity), 0)
                FROM   Return_Items ri
                JOIN   Returns r ON r.return_id = ri.return_id
                WHERE  ri.sale_item_id = ?
                  AND  r.status = 'completed'
                """,
                (item["sale_item_id"],)
            ).fetchone()[0]

            max_returnable = original_row["quantity"] - already
            if item["quantity"] > max_returnable:
                return (
                    False,
                    f"Return quantity ({item['quantity']}) would exceed "
                    f"returnable amount ({max_returnable}).",
                    ""
                )

        # ── Write the return ──────────────────────────────────────────────
        return_id    = "RTN-" + str(uuid.uuid4()).upper()[:8]
        total_refund = sum(i["quantity"] * i["price"] for i in return_items)
        now          = current_timestamp()

        conn.execute(
            """
            INSERT INTO Returns
                (return_id, sale_id, date, user_id, customer_id,
                 reason, total_refund, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'completed')
            """,
            (
                return_id, sale_id, now, user_id,
                sale["customer_id"], reason, total_refund,
            )
        )

        for item in return_items:
            conn.execute(
                """
                INSERT INTO Return_Items
                    (return_id, sale_item_id, product_id,
                     quantity, price, restocked)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    return_id,
                    item["sale_item_id"],
                    item["product_id"],
                    item["quantity"],
                    item["price"],
                    1 if restock else 0,
                )
            )

            if restock:
                conn.execute(
                    "UPDATE Products "
                    "SET quantity = quantity + ? "
                    "WHERE product_id = ?",
                    (item["quantity"], item["product_id"])
                )
                conn.execute(
                    "INSERT INTO Inventory "
                    "    (product_id, adjustment, reason, date) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        item["product_id"],
                        item["quantity"],
                        f"Return #{return_id}",
                        now,
                    )
                )

        conn.commit()
        return True, "Return processed successfully.", return_id

    except Exception as exc:
        conn.rollback()
        return False, f"Error processing return: {exc}", ""
    finally:
        conn.close()


def get_return_by_id(return_id: str) -> dict | None:
    """Returns the full return record including line items, or None."""
    conn = get_connection()
    try:
        ret = conn.execute(
            """
            SELECT r.*, u.username AS cashier_name
            FROM   Returns r
            JOIN   Users u ON u.user_id = r.user_id
            WHERE  r.return_id = ?
            """,
            (return_id,)
        ).fetchone()
        if not ret:
            return None

        result = dict(ret)
        result["items"] = [
            dict(row)
            for row in conn.execute(
                """
                SELECT ri.*, p.product_name
                FROM   Return_Items ri
                JOIN   Products p ON p.product_id = ri.product_id
                WHERE  ri.return_id = ?
                """,
                (return_id,)
            ).fetchall()
        ]
        return result
    finally:
        conn.close()


def get_returns_by_sale(sale_id: str) -> list:
    """Returns all return records for a given sale, newest first."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM Returns WHERE sale_id=? ORDER BY date DESC",
            (sale_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_recent_returns(limit: int = 50) -> list:
    """Returns the most recent return records, newest first."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT r.*, u.username AS cashier_name
            FROM   Returns r
            JOIN   Users u ON u.user_id = r.user_id
            ORDER  BY r.date DESC
            LIMIT  ?
            """,
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_daily_return_summary(date_str: str) -> dict:
    """
    Summary of completed returns for date_str (YYYY-MM-DD).

    Keys: date, count, total_refunded, items_restocked
    """
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count,
                   COALESCE(SUM(total_refund), 0) AS total_refunded
            FROM   Returns
            WHERE  date LIKE ? AND status = 'completed'
            """,
            (f"{date_str}%",)
        ).fetchone()

        restocked = conn.execute(
            """
            SELECT COALESCE(SUM(ri.quantity), 0)
            FROM   Return_Items ri
            JOIN   Returns r ON r.return_id = ri.return_id
            WHERE  r.date LIKE ?
              AND  ri.restocked = 1
              AND  r.status = 'completed'
            """,
            (f"{date_str}%",)
        ).fetchone()[0]

        return {
            "date":            date_str,
            "count":           row["count"],
            "total_refunded":  row["total_refunded"],
            "items_restocked": restocked,
        }
    finally:
        conn.close()
```

- [ ] **Step 2: Run the return tests — expect all green:**

```bash
python -m unittest tests.test_returns -v
```
Expected: All tests PASS. Zero failures.

- [ ] **Step 3: Commit:**

```bash
git add modules/returns.py
git commit -m "feat: implement returns and refunds module"
```

---

## Task 4: Add `save_return_receipt_to_file` to `modules/receipts.py`

**Files:**
- Modify: `modules/receipts.py`

- [ ] **Step 1: Open `modules/receipts.py`. Add the following two functions at the very end of the file (after `print_receipt`):**

```python
def format_return_receipt(return_id: str) -> str | None:
    """
    Generates a formatted return receipt string.
    Returns None if the return_id is not found.
    """
    from modules.returns import get_return_by_id

    ret = get_return_by_id(return_id)
    if not ret:
        return None

    store_name  = get_setting("store_name")
    store_phone = get_setting("store_phone")
    currency    = get_setting("currency_symbol") or "$"
    W = RECEIPT_WIDTH

    def centre(text):
        return text.center(W)

    def divider(char="-"):
        return char * W

    def row_lr(label, value):
        gap = W - len(label) - len(value)
        return label + " " * max(1, gap) + value

    lines = [
        divider("="),
        centre(store_name),
        centre(store_phone),
        divider("="),
        centre("*** RETURN / REFUND RECEIPT ***"),
        divider("="),
        f"Return ID  : {ret['return_id']}",
        f"Sale Ref   : {ret['sale_id']}",
        f"Date       : {ret['date']}",
        f"Cashier    : {ret['cashier_name']}",
        f"Reason     : {ret['reason']}",
        divider(),
        f"{'ITEM':<22} {'QTY':>4} {'PRICE':>7} {'TOTAL':>7}",
        divider(),
    ]

    for item in ret["items"]:
        total = item["quantity"] * item["price"]
        name  = item["product_name"][:21]
        lines.append(
            f"{name:<22} {item['quantity']:>4} "
            f"{currency}{item['price']:>6.2f} {currency}{total:>6.2f}"
        )
        if not item["restocked"]:
            lines.append("  (item not restocked — write-off)")

    lines += [
        divider(),
        row_lr("TOTAL REFUND:", f"{currency}{ret['total_refund']:.2f}"),
        divider("="),
        centre("Thank you. Returned items in good condition"),
        centre("have been restocked."),
        divider("="),
    ]
    return "\n".join(lines)


def save_return_receipt_to_file(return_id: str) -> tuple:
    """
    Generate and save a return receipt as a .txt file in /receipts/.
    Returns (success: bool, file_path_or_error: str).
    """
    text = format_return_receipt(return_id)
    if text is None:
        return False, f"Return '{return_id}' not found."

    filename = f"return_{return_id}.txt"
    filepath = os.path.join(RECEIPTS_DIR, filename)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(text)
        return True, filepath
    except OSError as e:
        return False, f"Could not save receipt: {e}"
```

- [ ] **Step 2: Verify import:**

```bash
python -c "from modules.receipts import format_return_receipt, save_return_receipt_to_file; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit:**

```bash
git add modules/receipts.py
git commit -m "feat: add format_return_receipt and save_return_receipt_to_file"
```

---

## Task 5: Add Returns to `modules/backup.py` CSV Export

**Files:**
- Modify: `modules/backup.py`

- [ ] **Step 1: Open `modules/backup.py`. Find the list that defines which tables are exported to CSV (it will contain entries like `"Products"`, `"Sales"`, etc.). Add `"Returns"` and `"Return_Items"` to that list, in dependency order (after `"Sales"`).**

The list looks like:
```python
_EXPORT_TABLES = [
    "Users", "Products", "Customers",
    "Sales", "Sales_Items",
    "Inventory", "Payments",
    "Transaction_Logs", "Settings",
]
```

Change it to:
```python
_EXPORT_TABLES = [
    "Users", "Products", "Customers",
    "Sales", "Sales_Items",
    "Returns", "Return_Items",
    "Inventory", "Payments",
    "Transaction_Logs", "Settings",
]
```

- [ ] **Step 2: Verify the backup module still imports cleanly:**

```bash
python -c "from modules.backup import export_all_to_csv; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit:**

```bash
git add modules/backup.py
git commit -m "feat: include Returns and Return_Items in CSV backup export"
```

---

## Task 6: Build `ui/returns_ui.py`

**Files:**
- Create: `ui/returns_ui.py`

- [ ] **Step 1: Create `ui/returns_ui.py`:**

```python
"""
Returns UI Panel
================
Three-phase workflow (all in one screen):
  1. Search  — enter a Sale ID to load the original sale
  2. Select  — double-click a row to set the return quantity
  3. Confirm — enter a reason and click Process Return

Accessible from the sidebar for manager and admin roles.
"""

import tkinter as tk
from tkinter import ttk, messagebox

from ui.login_screen import COLORS
from database.db_setup import get_setting
import modules.auth as auth
import modules.returns as returns
import modules.sales as sales
from modules.receipts import format_return_receipt, save_return_receipt_to_file


class ReturnsUI:
    def __init__(self, parent: tk.Frame):
        self.parent = parent
        self.parent.configure(bg=COLORS["bg"])

        self._sale       = None   # currently loaded sale dict
        self._returnable = []     # list of returnable item dicts
        self._qty_vars   = {}     # {sale_item_id: int}

        self._build_ui()

    # -----------------------------------------------------------------------
    # Layout
    # -----------------------------------------------------------------------

    def _build_ui(self):
        # ── Title ────────────────────────────────────────────────────────
        hdr = tk.Frame(self.parent, bg=COLORS["panel"], pady=10)
        hdr.pack(fill="x", padx=20, pady=(20, 0))
        tk.Label(
            hdr, text="Returns & Refunds",
            font=("Helvetica", 18, "bold"),
            bg=COLORS["panel"], fg=COLORS["white"]
        ).pack(side="left", padx=15)

        # ── Search bar ───────────────────────────────────────────────────
        sf = tk.Frame(self.parent, bg=COLORS["bg"], pady=10)
        sf.pack(fill="x", padx=20, pady=10)

        tk.Label(sf, text="Sale ID:",
                 bg=COLORS["bg"], fg=COLORS["text"],
                 font=("Helvetica", 11)).pack(side="left")

        self._sid_var = tk.StringVar()
        entry = tk.Entry(
            sf, textvariable=self._sid_var,
            font=("Helvetica", 12), width=28,
            bg=COLORS["panel"], fg=COLORS["white"],
            insertbackground=COLORS["white"]
        )
        entry.pack(side="left", padx=8)
        entry.bind("<Return>", lambda _e: self._load_sale())

        tk.Button(
            sf, text="Load Sale",
            bg=COLORS["accent"], fg=COLORS["white"],
            font=("Helvetica", 10, "bold"),
            relief="flat", padx=12, pady=4, cursor="hand2",
            command=self._load_sale
        ).pack(side="left", padx=4)

        tk.Button(
            sf, text="Clear",
            bg=COLORS["button"], fg=COLORS["text"],
            font=("Helvetica", 10),
            relief="flat", padx=10, pady=4, cursor="hand2",
            command=self._clear
        ).pack(side="left")

        # ── Sale info bar ────────────────────────────────────────────────
        self._info_bar = tk.Frame(self.parent, bg=COLORS["panel"], pady=8)
        self._info_bar.pack(fill="x", padx=20)
        self._info_lbl = tk.Label(
            self._info_bar,
            text="Enter a Sale ID above to begin. Double-click a row to set return quantity.",
            bg=COLORS["panel"], fg=COLORS["muted"],
            font=("Helvetica", 10)
        )
        self._info_lbl.pack(padx=15, anchor="w")

        # ── Items table ──────────────────────────────────────────────────
        tf = tk.Frame(self.parent, bg=COLORS["bg"])
        tf.pack(fill="both", expand=True, padx=20, pady=8)

        cols = ("product", "original_qty", "returned_qty",
                "returnable_qty", "unit_price", "return_qty")
        self._tree = ttk.Treeview(tf, columns=cols, show="headings", height=10)

        col_cfg = [
            ("product",        "Product",       200, "w"),
            ("original_qty",   "Bought",         70, "center"),
            ("returned_qty",   "Returned",        80, "center"),
            ("returnable_qty", "Available",       85, "center"),
            ("unit_price",     "Unit Price",      90, "center"),
            ("return_qty",     "Return Qty ✎",   110, "center"),
        ]
        for cid, label, width, anchor in col_cfg:
            self._tree.heading(cid, text=label)
            self._tree.column(cid, width=width, anchor=anchor)

        vsb = ttk.Scrollbar(tf, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self._tree.bind("<Double-1>", self._edit_return_qty)

        # ── Action bar ───────────────────────────────────────────────────
        af = tk.Frame(self.parent, bg=COLORS["panel"], pady=10)
        af.pack(fill="x", padx=20, pady=(0, 20))

        tk.Label(af, text="Reason:",
                 bg=COLORS["panel"], fg=COLORS["text"],
                 font=("Helvetica", 11)).pack(side="left", padx=(15, 5))

        self._reason_var = tk.StringVar()
        tk.Entry(
            af, textvariable=self._reason_var,
            font=("Helvetica", 11), width=32,
            bg=COLORS["bg"], fg=COLORS["white"],
            insertbackground=COLORS["white"]
        ).pack(side="left", padx=5)

        self._restock_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            af, text="Restock items",
            variable=self._restock_var,
            bg=COLORS["panel"], fg=COLORS["text"],
            selectcolor=COLORS["bg"],
            activebackground=COLORS["panel"],
            font=("Helvetica", 10)
        ).pack(side="left", padx=10)

        tk.Button(
            af, text="Process Return",
            bg="#e74c3c", fg=COLORS["white"],
            font=("Helvetica", 11, "bold"),
            relief="flat", padx=16, pady=6, cursor="hand2",
            command=self._confirm_return
        ).pack(side="right", padx=15)

        self._total_lbl = tk.Label(
            af, text="Refund: $0.00",
            bg=COLORS["panel"], fg=COLORS["accent"],
            font=("Helvetica", 12, "bold")
        )
        self._total_lbl.pack(side="right", padx=10)

    # -----------------------------------------------------------------------
    # Actions
    # -----------------------------------------------------------------------

    def _load_sale(self):
        sale_id = self._sid_var.get().strip().upper()
        if not sale_id:
            messagebox.showwarning("Input Required", "Please enter a Sale ID.")
            return

        sale = sales.get_sale_by_id(sale_id)
        if not sale:
            messagebox.showerror("Not Found",
                                 f"No sale found with ID: {sale_id}")
            return

        self._sale       = sale
        self._returnable = returns.get_returnable_items(sale_id)
        self._qty_vars   = {item["sale_item_id"]: 0 for item in self._returnable}

        currency = get_setting("currency_symbol") or "$"
        info = (
            f"  Sale: {sale['sale_id']}   |   "
            f"Date: {sale['date'][:16]}   |   "
            f"Total: {currency}{sale['total_amount']:.2f}   |   "
            f"Cashier: {sale.get('cashier_name', '—')}"
        )
        self._info_lbl.config(
            text=info, fg=COLORS["text"],
            font=("Helvetica", 10, "bold")
        )
        self._populate_table()

    def _populate_table(self):
        for row in self._tree.get_children():
            self._tree.delete(row)

        currency = get_setting("currency_symbol") or "$"
        for item in self._returnable:
            tag = "disabled" if item["returnable_qty"] == 0 else ""
            self._tree.insert(
                "", "end",
                iid=str(item["sale_item_id"]),
                tags=(tag,),
                values=(
                    item["product_name"],
                    item["original_qty"],
                    item["returned_qty"],
                    item["returnable_qty"],
                    f"{currency}{item['price']:.2f}",
                    self._qty_vars.get(item["sale_item_id"], 0),
                )
            )
        self._tree.tag_configure("disabled", foreground="#555")
        self._update_total()

    def _edit_return_qty(self, _event):
        sel = self._tree.selection()
        if not sel:
            return
        siid = int(sel[0])
        item = next(
            (i for i in self._returnable if i["sale_item_id"] == siid), None
        )
        if not item or item["returnable_qty"] == 0:
            return

        dlg = tk.Toplevel(self.parent)
        dlg.title("Set Return Quantity")
        dlg.resizable(False, False)
        dlg.configure(bg=COLORS["panel"])
        dlg.grab_set()

        tk.Label(
            dlg,
            text=(f"Return qty for:\n{item['product_name']}\n"
                  f"(max {item['returnable_qty']})"),
            bg=COLORS["panel"], fg=COLORS["text"],
            font=("Helvetica", 11), pady=10, padx=20
        ).pack()

        qty_var = tk.IntVar(value=self._qty_vars.get(siid, 0))
        tk.Spinbox(
            dlg, from_=0, to=item["returnable_qty"],
            textvariable=qty_var,
            font=("Helvetica", 14), width=6,
            bg=COLORS["bg"], fg=COLORS["white"],
            buttonbackground=COLORS["button"]
        ).pack(pady=8)

        def _apply():
            self._qty_vars[siid] = qty_var.get()
            self._tree.set(str(siid), "return_qty", self._qty_vars[siid])
            self._update_total()
            dlg.destroy()

        tk.Button(
            dlg, text="Set", command=_apply,
            bg=COLORS["accent"], fg=COLORS["white"],
            font=("Helvetica", 11, "bold"),
            relief="flat", padx=14, pady=6
        ).pack(pady=(0, 12))

    def _update_total(self):
        currency = get_setting("currency_symbol") or "$"
        total = sum(
            self._qty_vars.get(i["sale_item_id"], 0) * i["price"]
            for i in self._returnable
        )
        self._total_lbl.config(text=f"Refund: {currency}{total:.2f}")

    def _confirm_return(self):
        if not self._sale:
            messagebox.showwarning("No Sale Loaded",
                                   "Please load a sale first.")
            return

        reason = self._reason_var.get().strip()
        if not reason:
            messagebox.showwarning("Reason Required",
                                   "Please enter a reason for the return.")
            return

        items_to_return = [
            {
                "sale_item_id": item["sale_item_id"],
                "product_id":   item["product_id"],
                "quantity":     self._qty_vars.get(item["sale_item_id"], 0),
                "price":        item["price"],
            }
            for item in self._returnable
            if self._qty_vars.get(item["sale_item_id"], 0) > 0
        ]

        if not items_to_return:
            messagebox.showwarning(
                "No Items Selected",
                "Double-click a row to set the return quantity first."
            )
            return

        currency = get_setting("currency_symbol") or "$"
        total    = sum(i["quantity"] * i["price"] for i in items_to_return)

        if not messagebox.askyesno(
            "Confirm Return",
            f"Process return of {len(items_to_return)} item(s) for a "
            f"refund of {currency}{total:.2f}?\n\nReason: {reason}"
        ):
            return

        user = auth.get_current_user()
        success, msg, return_id = returns.process_return(
            self._sale["sale_id"],
            items_to_return,
            reason,
            user["user_id"],
            restock=self._restock_var.get()
        )

        if not success:
            messagebox.showerror("Return Failed", msg)
            return

        receipt_text = format_return_receipt(return_id)
        if receipt_text:
            self._show_receipt_window(receipt_text, return_id)

        self._clear()
        messagebox.showinfo("Return Complete",
                            f"Return {return_id} processed successfully.")

    def _show_receipt_window(self, receipt_text: str, return_id: str):
        win = tk.Toplevel(self.parent)
        win.title(f"Return Receipt — {return_id}")
        win.configure(bg=COLORS["bg"])
        win.resizable(False, False)

        tk.Label(
            win, text="Return Receipt",
            font=("Helvetica", 14, "bold"),
            bg=COLORS["bg"], fg=COLORS["white"]
        ).pack(pady=(12, 4))

        txt = tk.Text(
            win, font=("Courier", 10),
            bg=COLORS["panel"], fg=COLORS["white"],
            width=46, height=28,
            relief="flat", padx=8, pady=8
        )
        txt.insert("1.0", receipt_text)
        txt.config(state="disabled")
        txt.pack(padx=16, pady=8)

        bf = tk.Frame(win, bg=COLORS["bg"])
        bf.pack(pady=(0, 12))

        def _save():
            ok, path = save_return_receipt_to_file(return_id)
            if ok:
                messagebox.showinfo("Saved", f"Receipt saved:\n{path}")
            else:
                messagebox.showerror("Error", path)

        tk.Button(
            bf, text="Save to File", command=_save,
            bg=COLORS["button"], fg=COLORS["text"],
            font=("Helvetica", 10), relief="flat", padx=12, pady=5
        ).pack(side="left", padx=6)

        tk.Button(
            bf, text="Close", command=win.destroy,
            bg=COLORS["accent"], fg=COLORS["white"],
            font=("Helvetica", 10, "bold"), relief="flat", padx=12, pady=5
        ).pack(side="left", padx=6)

    def _clear(self):
        self._sale       = None
        self._returnable = []
        self._qty_vars   = {}
        self._sid_var.set("")
        self._reason_var.set("")
        self._restock_var.set(True)
        for row in self._tree.get_children():
            self._tree.delete(row)
        self._info_lbl.config(
            text="Enter a Sale ID above to begin. Double-click a row to set return quantity.",
            fg=COLORS["muted"], font=("Helvetica", 10)
        )
        self._total_lbl.config(text="Refund: $0.00")
```

- [ ] **Step 2: Verify import:**

```bash
python -c "from ui.returns_ui import ReturnsUI; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit:**

```bash
git add ui/returns_ui.py
git commit -m "feat: add Returns UI panel with search/select/confirm/receipt workflow"
```

---

## Task 7: Wire Returns into the Dashboard

**Files:**
- Modify: `ui/admin_dashboard.py`
- Modify: `ui/home_panel.py`

- [ ] **Step 1: Open `ui/admin_dashboard.py`. In `_build_sidebar()`, locate the block where manager/admin nav items are added. Add a new conditional block for manager + admin (between the common items and the admin-only block):**

```python
# Add after the common nav_items list, before the admin-only block:
if user["role"] in ("admin", "manager"):
    nav_items.append(("↩  Returns", self._show_returns))
```

Then add the handler method to the `AdminDashboard` class (near the other `_show_*` methods):
```python
def _show_returns(self):
    self._clear_content()
    from ui.returns_ui import ReturnsUI
    ReturnsUI(self.content)
```

- [ ] **Step 2: Open `ui/home_panel.py`. In `_fetch_summary()`, add a returns-today query (import at top of function or module level):**

```python
# At the top of _fetch_summary(), after existing imports:
from datetime import date as _date
today = _date.today().strftime("%Y-%m-%d")

# Add this query before conn.close():
returns_today = conn.execute(
    "SELECT COUNT(*) FROM Returns "
    "WHERE date LIKE ? AND status='completed'",
    (f"{today}%",)
).fetchone()[0]
```

Add `"returns_today": returns_today` to the returned dict.

In `_build_ui()`, add to the `cards` list:
```python
("↩ Returns Today", str(summary["returns_today"]), "#e74c3c"),
```

- [ ] **Step 3: Launch and verify:**

```bash
python main.py
```
Login as admin → sidebar shows "↩  Returns" → click it → panel loads.
Home shows "↩ Returns Today" card.
Login as manager → "↩  Returns" visible. Login as cashier → NOT visible.

- [ ] **Step 4: Commit:**

```bash
git add ui/admin_dashboard.py ui/home_panel.py
git commit -m "feat: wire Returns into dashboard sidebar (manager+admin) and home stats"
```

---

## Task 8: Full Return Test Suite Run

- [ ] **Step 1: Run all tests:**

```bash
python -m unittest discover -s tests -v
```
Expected: ALL tests PASS (original 81 + new return tests). Zero failures.

- [ ] **Step 2: Fix any failures before proceeding. Do not move to Feature 2 until green.**

- [ ] **Step 3: Final Feature 1 commit:**

```bash
git add -A
git commit -m "feat: complete Returns & Refunds — module, UI, receipts, backup, tests"
```

---

# FEATURE 2: SMART SALES INTELLIGENCE

---

## Task 9: Write Failing Tests for `modules/intelligence.py`

**Files:**
- Create: `tests/test_intelligence.py`

- [ ] **Step 1: Create `tests/test_intelligence.py`:**

```python
"""Tests for modules/intelligence.py

Helpers insert data directly to avoid slow module-level create_sale calls
where date control is needed. All DB access uses get_connection() (not self.conn)
because PosTestCase patches DB_PATH at the class level.
"""
import unittest
import uuid
from datetime import date, timedelta
from tests.test_base import PosTestCase
from modules import intelligence


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _seed_product(name, price=10.0, qty=100):
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


def _insert_sale(user_id, product_id, qty, price, days_ago=0):
    """Insert a sale with a controlled date (bypasses sales module for date control)."""
    from database.db_setup import get_connection
    conn = get_connection()
    sale_date = (date.today() - timedelta(days=days_ago)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    sid   = "TXN-" + str(uuid.uuid4()).upper()[:8]
    total = qty * price
    conn.execute(
        "INSERT INTO Sales (sale_id, date, user_id, subtotal, "
        "discount, tax, total_amount, payment_method) "
        "VALUES (?,?,?,?,0,0,?,'cash')",
        (sid, sale_date, user_id, total, total)
    )
    conn.execute(
        "INSERT INTO Sales_Items (sale_id, product_id, quantity, price) "
        "VALUES (?,?,?,?)",
        (sid, product_id, qty, price)
    )
    conn.execute(
        "UPDATE Products SET quantity = MAX(0, quantity - ?) "
        "WHERE product_id=?",
        (qty, product_id)
    )
    conn.commit()
    conn.close()
    return sid


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------

class TestSalesVelocity(PosTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pid = _seed_product("VelProd", qty=500)
        for i in range(14):
            _insert_sale(1, cls.pid, qty=2, price=10.0, days_ago=i)

    def test_single_product_returns_float(self):
        v = intelligence.get_sales_velocity(self.pid, days=14)
        self.assertIsInstance(v, float)

    def test_single_product_velocity_positive(self):
        v = intelligence.get_sales_velocity(self.pid, days=14)
        self.assertGreater(v, 0)

    def test_zero_velocity_for_unsold_product(self):
        pid2 = _seed_product("NoSalesProd", qty=50)
        self.assertEqual(intelligence.get_sales_velocity(pid2, days=30), 0.0)

    def test_all_products_returns_dict(self):
        result = intelligence.get_sales_velocity(days=14)
        self.assertIsInstance(result, dict)
        self.assertIn(self.pid, result)


class TestStockoutPredictions(PosTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pid = _seed_product("FastSeller", qty=10)
        for i in range(7):
            _insert_sale(1, cls.pid, qty=2, price=5.0, days_ago=i)

    def test_is_list(self):
        self.assertIsInstance(intelligence.get_stockout_predictions(), list)

    def test_required_keys_present(self):
        result = intelligence.get_stockout_predictions()
        if result:
            required = {"product_id", "product_name", "current_stock",
                        "avg_daily_sales", "days_until_stockout", "urgency"}
            self.assertTrue(required.issubset(result[0].keys()))

    def test_urgency_values_valid(self):
        valid = {"critical", "warning", "ok"}
        for item in intelligence.get_stockout_predictions():
            self.assertIn(item["urgency"], valid)

    def test_sorted_ascending_by_days(self):
        result = intelligence.get_stockout_predictions()
        if len(result) > 1:
            days_list = [r["days_until_stockout"] for r in result]
            self.assertEqual(days_list, sorted(days_list))

    def test_out_of_stock_excluded(self):
        pid_zero = _seed_product("ZeroStock", qty=0)
        ids = [r["product_id"] for r in intelligence.get_stockout_predictions()]
        self.assertNotIn(pid_zero, ids)


class TestTrendingProducts(PosTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pid_up = _seed_product("TrendUp",   qty=500)
        cls.pid_dn = _seed_product("TrendDown", qty=500)
        # pid_up: heavy recent, light older
        for i in range(7):
            _insert_sale(1, cls.pid_up, qty=5, price=10.0, days_ago=i)
        for i in range(7, 14):
            _insert_sale(1, cls.pid_up, qty=1, price=10.0, days_ago=i)
        # pid_dn: light recent, heavy older
        for i in range(7):
            _insert_sale(1, cls.pid_dn, qty=1, price=10.0, days_ago=i)
        for i in range(7, 14):
            _insert_sale(1, cls.pid_dn, qty=5, price=10.0, days_ago=i)

    def test_returns_list(self):
        self.assertIsInstance(intelligence.get_trending_products(), list)

    def test_direction_values_valid(self):
        valid = {"up", "down", "stable"}
        for item in intelligence.get_trending_products():
            self.assertIn(item["direction"], valid)

    def test_trending_product_is_up(self):
        result = intelligence.get_trending_products()
        entry = next((r for r in result if r["product_id"] == self.pid_up), None)
        if entry:
            self.assertEqual(entry["direction"], "up")

    def test_declining_product_is_down(self):
        result = intelligence.get_trending_products()
        entry = next((r for r in result if r["product_id"] == self.pid_dn), None)
        if entry:
            self.assertEqual(entry["direction"], "down")


class TestReorderSuggestions(PosTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pid = _seed_product("NeedReorder", qty=5)
        for i in range(14):
            _insert_sale(1, cls.pid, qty=1, price=10.0, days_ago=i)

    def test_returns_list(self):
        self.assertIsInstance(intelligence.get_smart_reorder_suggestions(), list)

    def test_required_keys_present(self):
        result = intelligence.get_smart_reorder_suggestions()
        if result:
            required = {"product_id", "product_name", "current_stock",
                        "avg_daily_sales", "days_remaining",
                        "suggested_order_qty"}
            self.assertTrue(required.issubset(result[0].keys()))

    def test_suggested_qty_is_positive(self):
        for item in intelligence.get_smart_reorder_suggestions():
            self.assertGreater(item["suggested_order_qty"], 0)


class TestABCAnalysis(PosTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        for i, (price, qty) in enumerate(
            [(100, 50), (50, 30), (20, 20), (10, 15), (5, 10)]
        ):
            pid = _seed_product(f"ABCProd{i}", price=price, qty=500)
            for _ in range(qty):
                _insert_sale(1, pid, qty=1, price=price)

    def test_has_three_tiers(self):
        result = intelligence.get_abc_analysis()
        for tier in ("A", "B", "C"):
            self.assertIn(tier, result)

    def test_all_products_classified(self):
        from database.db_setup import get_connection
        conn = get_connection()
        total_products = conn.execute(
            "SELECT COUNT(*) FROM Products"
        ).fetchone()[0]
        conn.close()
        result = intelligence.get_abc_analysis()
        classified = (len(result["A"]) + len(result["B"]) + len(result["C"]))
        self.assertEqual(classified, total_products)

    def test_items_have_product_name(self):
        result = intelligence.get_abc_analysis()
        for tier in ("A", "B", "C"):
            for item in result[tier]:
                self.assertIn("product_name", item)

    def test_total_revenue_positive(self):
        self.assertGreater(intelligence.get_abc_analysis()["total_revenue"], 0)


class TestRevenueForecast(PosTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        pid = _seed_product("ForecastProd", qty=1000)
        for i in range(28):
            _insert_sale(1, pid, qty=3, price=10.0, days_ago=i)

    def test_returns_list_of_correct_length(self):
        result = intelligence.get_revenue_forecast(forecast_days=7)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 7)

    def test_required_keys(self):
        for day in intelligence.get_revenue_forecast(forecast_days=7):
            self.assertIn("date", day)
            self.assertIn("forecasted_revenue", day)
            self.assertIn("confidence", day)

    def test_forecasted_revenue_positive(self):
        for day in intelligence.get_revenue_forecast(forecast_days=7):
            self.assertGreater(day["forecasted_revenue"], 0)

    def test_confidence_values_valid(self):
        valid = {"low", "medium", "high"}
        for day in intelligence.get_revenue_forecast(forecast_days=7):
            self.assertIn(day["confidence"], valid)


class TestPeakHoursAnalysis(PosTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        pid = _seed_product("PeakProd", qty=500)
        for i in range(10):
            _insert_sale(1, pid, qty=1, price=10.0, days_ago=i)

    def test_structure_keys(self):
        result = intelligence.get_peak_hours_analysis()
        self.assertIn("hourly", result)
        self.assertIn("daily", result)

    def test_hourly_has_24_slots(self):
        self.assertEqual(len(intelligence.get_peak_hours_analysis()["hourly"]), 24)

    def test_daily_has_7_days(self):
        self.assertEqual(len(intelligence.get_peak_hours_analysis()["daily"]), 7)


class TestDashboardSummary(PosTestCase):
    def test_required_keys(self):
        result = intelligence.get_dashboard_summary()
        required = {
            "critical_stockouts", "warning_stockouts",
            "trending_up", "trending_down",
            "reorder_needed", "forecast_tomorrow",
        }
        self.assertTrue(required.issubset(result.keys()))

    def test_all_values_numeric(self):
        for key, val in intelligence.get_dashboard_summary().items():
            self.assertIsInstance(val, (int, float), f"{key} is not numeric")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to confirm failure (module missing):**

```bash
python -m unittest tests.test_intelligence -v 2>&1 | head -5
```
Expected: `ModuleNotFoundError: No module named 'modules.intelligence'`

- [ ] **Step 3: Commit:**

```bash
git add tests/test_intelligence.py
git commit -m "test: add failing tests for intelligence module (TDD red phase)"
```

---

## Task 10: Implement `modules/intelligence.py`

**Files:**
- Create: `modules/intelligence.py`

- [ ] **Step 1: Create `modules/intelligence.py`:**

```python
"""
Smart Sales Intelligence Module
================================
Pure stdlib analytics engine — zero external dependencies.

Public API
----------
get_sales_velocity(product_id=None, days=30)  -> float | dict
get_stockout_predictions()                     -> list[dict]
get_trending_products(days=7, limit=10)        -> list[dict]
get_smart_reorder_suggestions(lead_time=7)     -> list[dict]
get_peak_hours_analysis(days=30)               -> dict
get_abc_analysis()                             -> dict
get_revenue_forecast(forecast_days=7)          -> list[dict]
get_dashboard_summary()                        -> dict
"""

from datetime import date, timedelta
from database.db_setup import get_connection


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _date_range(days: int) -> tuple:
    end   = date.today()
    start = end - timedelta(days=days - 1)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _velocity_for_product(conn, product_id: int, days: int) -> float:
    """Average units sold per day over the last *days* days."""
    start, end = _date_range(days)
    total = conn.execute(
        """
        SELECT COALESCE(SUM(si.quantity), 0)
        FROM   Sales_Items si
        JOIN   Sales s ON s.sale_id = si.sale_id
        WHERE  si.product_id = ?
          AND  DATE(s.date) BETWEEN ? AND ?
        """,
        (product_id, start, end)
    ).fetchone()[0]
    return round(total / days, 4)


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def get_sales_velocity(product_id: int = None, days: int = 30):
    """
    Average units sold per day.

    product_id given → single float
    product_id omitted → dict {product_id: velocity}
    """
    conn = get_connection()
    try:
        if product_id is not None:
            return _velocity_for_product(conn, product_id, days)

        rows = conn.execute("SELECT product_id FROM Products").fetchall()
        return {
            r["product_id"]: _velocity_for_product(conn, r["product_id"], days)
            for r in rows
        }
    finally:
        conn.close()


def get_stockout_predictions() -> list:
    """
    Days-to-stockout per in-stock product (velocity > 0 only).
    Sorted ascending by days_until_stockout.

    urgency: 'critical' < 7 days | 'warning' 7–14 | 'ok' > 14
    """
    conn = get_connection()
    try:
        products = conn.execute(
            "SELECT product_id, product_name, quantity AS current_stock "
            "FROM Products WHERE quantity > 0"
        ).fetchall()

        results = []
        for p in products:
            velocity = _velocity_for_product(conn, p["product_id"], 30)
            if velocity == 0.0:
                continue

            days_left = round(p["current_stock"] / velocity, 1)
            urgency   = (
                "critical" if days_left < 7 else
                "warning"  if days_left < 14 else
                "ok"
            )
            results.append({
                "product_id":          p["product_id"],
                "product_name":        p["product_name"],
                "current_stock":       p["current_stock"],
                "avg_daily_sales":     velocity,
                "days_until_stockout": days_left,
                "urgency":             urgency,
            })

        results.sort(key=lambda x: x["days_until_stockout"])
        return results
    finally:
        conn.close()


def get_trending_products(days: int = 7, limit: int = 10) -> list:
    """
    Compares last *days* velocity vs previous *days* period.

    direction: 'up' (>+10%) | 'down' (<-10%) | 'stable'
    Sorted by abs(trend_pct) descending.
    """
    conn = get_connection()
    try:
        products = conn.execute(
            "SELECT product_id, product_name FROM Products"
        ).fetchall()

        results = []
        for p in products:
            recent   = _velocity_for_product(conn, p["product_id"], days)

            prev_start = date.today() - timedelta(days=days * 2 - 1)
            prev_end   = date.today() - timedelta(days=days)
            prev_sold  = conn.execute(
                """
                SELECT COALESCE(SUM(si.quantity), 0)
                FROM   Sales_Items si
                JOIN   Sales s ON s.sale_id = si.sale_id
                WHERE  si.product_id = ?
                  AND  DATE(s.date) BETWEEN ? AND ?
                """,
                (
                    p["product_id"],
                    prev_start.strftime("%Y-%m-%d"),
                    prev_end.strftime("%Y-%m-%d"),
                )
            ).fetchone()[0]
            previous  = round(prev_sold / days, 4)

            trend_pct = (recent - previous) / (previous + 0.01)
            direction = (
                "up"     if trend_pct >  0.10 else
                "down"   if trend_pct < -0.10 else
                "stable"
            )

            results.append({
                "product_id":   p["product_id"],
                "product_name": p["product_name"],
                "recent_sales": round(recent * days, 2),
                "prev_sales":   round(previous * days, 2),
                "trend_pct":    round(trend_pct * 100, 1),
                "direction":    direction,
            })

        results.sort(key=lambda x: abs(x["trend_pct"]), reverse=True)
        return results[:limit]
    finally:
        conn.close()


def get_smart_reorder_suggestions(lead_time_days: int = 7) -> list:
    """
    Products to order now: days_remaining < lead_time_days + 7.

    suggested_order_qty = (velocity * (lead_time + 14)) - current_stock
    """
    threshold   = lead_time_days + 7
    predictions = get_stockout_predictions()

    suggestions = []
    for p in predictions:
        if p["days_until_stockout"] < threshold:
            suggested = max(
                1,
                round(
                    (p["avg_daily_sales"] * (lead_time_days + 14))
                    - p["current_stock"]
                )
            )
            suggestions.append({
                "product_id":          p["product_id"],
                "product_name":        p["product_name"],
                "current_stock":       p["current_stock"],
                "avg_daily_sales":     p["avg_daily_sales"],
                "days_remaining":      p["days_until_stockout"],
                "suggested_order_qty": suggested,
            })

    suggestions.sort(key=lambda x: x["days_remaining"])
    return suggestions


def get_peak_hours_analysis(days: int = 30) -> dict:
    """
    Breaks sales down by hour of day (0–23) and day of week (Mon–Sun).

    Returns:
        {
            "hourly": [{hour, sales_count, revenue}] × 24,
            "daily":  [{day_name, sales_count, revenue}] × 7,
        }
    """
    from datetime import datetime

    start, end = _date_range(days)
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT date, total_amount FROM Sales "
            "WHERE DATE(date) BETWEEN ? AND ?",
            (start, end)
        ).fetchall()

        hourly = {h: {"hour": h, "sales_count": 0, "revenue": 0.0}
                  for h in range(24)}
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday",
                     "Friday", "Saturday", "Sunday"]
        daily = {i: {"day_name": day_names[i], "sales_count": 0, "revenue": 0.0}
                 for i in range(7)}

        for row in rows:
            try:
                dt = datetime.strptime(row["date"], "%Y-%m-%d %H:%M:%S")
                hourly[dt.hour]["sales_count"]  += 1
                hourly[dt.hour]["revenue"]       += row["total_amount"]
                daily[dt.weekday()]["sales_count"] += 1
                daily[dt.weekday()]["revenue"]     += row["total_amount"]
            except (ValueError, KeyError):
                continue

        for h in hourly.values():
            h["revenue"] = round(h["revenue"], 2)
        for d in daily.values():
            d["revenue"] = round(d["revenue"], 2)

        return {
            "hourly": list(hourly.values()),
            "daily":  list(daily.values()),
        }
    finally:
        conn.close()


def get_abc_analysis() -> dict:
    """
    Pareto ABC classification of all products by all-time revenue.

    A: cumulative revenue ≤ 70%
    B: cumulative revenue 70–90%
    C: remaining

    Returns:
        {"A": [...], "B": [...], "C": [...], "total_revenue": float}
    Each item: product_id, product_name, revenue, revenue_pct, tier
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT p.product_id,
                   p.product_name,
                   COALESCE(SUM(si.quantity * si.price), 0) AS revenue
            FROM   Products p
            LEFT JOIN Sales_Items si ON si.product_id = p.product_id
            GROUP  BY p.product_id
            ORDER  BY revenue DESC
            """
        ).fetchall()

        total_revenue = sum(r["revenue"] for r in rows)
        result = {"A": [], "B": [], "C": [], "total_revenue": round(total_revenue, 2)}

        cumulative = 0.0
        for r in rows:
            pct        = (r["revenue"] / total_revenue * 100) if total_revenue else 0
            cumulative += pct
            tier = "A" if cumulative <= 70 else "B" if cumulative <= 90 else "C"
            result[tier].append({
                "product_id":   r["product_id"],
                "product_name": r["product_name"],
                "revenue":      round(r["revenue"], 2),
                "revenue_pct":  round(pct, 2),
                "tier":         tier,
            })

        return result
    finally:
        conn.close()


def get_revenue_forecast(forecast_days: int = 7) -> list:
    """
    Rolling-average revenue forecast using the last 28 days.

    confidence:
        'high'   — 28 days of non-zero history
        'medium' — 14–27 days
        'low'    — fewer than 14 days
    """
    conn = get_connection()
    try:
        daily_revenues = []
        for i in range(1, 29):
            d = (date.today() - timedelta(days=i)).strftime("%Y-%m-%d")
            rev = conn.execute(
                "SELECT COALESCE(SUM(total_amount), 0) FROM Sales "
                "WHERE DATE(date)=?",
                (d,)
            ).fetchone()[0]
            daily_revenues.append(rev)

        days_with_data = sum(1 for v in daily_revenues if v > 0)
        confidence = (
            "high"   if days_with_data >= 28 else
            "medium" if days_with_data >= 14 else
            "low"
        )
        daily_avg = sum(daily_revenues) / 28 if daily_revenues else 0.0

        return [
            {
                "date": (date.today() + timedelta(days=i + 1)).strftime("%Y-%m-%d"),
                "forecasted_revenue": round(daily_avg, 2),
                "confidence":         confidence,
            }
            for i in range(forecast_days)
        ]
    finally:
        conn.close()


def get_dashboard_summary() -> dict:
    """
    Aggregated summary for the intelligence panel header cards.

    Keys: critical_stockouts, warning_stockouts, trending_up,
          trending_down, reorder_needed, forecast_tomorrow
    """
    predictions = get_stockout_predictions()
    trending    = get_trending_products()
    reorders    = get_smart_reorder_suggestions()
    forecast    = get_revenue_forecast(forecast_days=1)

    return {
        "critical_stockouts": sum(1 for p in predictions if p["urgency"] == "critical"),
        "warning_stockouts":  sum(1 for p in predictions if p["urgency"] == "warning"),
        "trending_up":        sum(1 for t in trending if t["direction"] == "up"),
        "trending_down":      sum(1 for t in trending if t["direction"] == "down"),
        "reorder_needed":     len(reorders),
        "forecast_tomorrow":  forecast[0]["forecasted_revenue"] if forecast else 0.0,
    }
```

- [ ] **Step 2: Run intelligence tests:**

```bash
python -m unittest tests.test_intelligence -v
```
Expected: All tests PASS.

- [ ] **Step 3: Commit:**

```bash
git add modules/intelligence.py
git commit -m "feat: implement Smart Sales Intelligence analytics engine"
```

---

## Task 11: Build `ui/intelligence_ui.py`

**Files:**
- Create: `ui/intelligence_ui.py`

- [ ] **Step 1: Create `ui/intelligence_ui.py`:**

```python
"""
Smart Sales Intelligence UI Panel
===================================
Six tabs, each a different analytical view:
  Tab 1 — Reorder Alerts : products that need ordering now
  Tab 2 — Stock Radar    : days-to-stockout countdown per product
  Tab 3 — Trends         : velocity comparison (this week vs last)
  Tab 4 — ABC Analysis   : Pareto revenue tier classification
  Tab 5 — Forecast       : 7-day revenue projection
  Tab 6 — Peak Hours     : busiest hours and days of week

No business logic — all computation delegated to modules/intelligence.py.
"""

import tkinter as tk
from tkinter import ttk

from ui.login_screen import COLORS
from modules import intelligence

_RED    = "#e74c3c"
_ORANGE = "#e67e22"
_GREEN  = "#27ae60"
_BLUE   = "#3498db"
_PURPLE = "#9b59b6"


class IntelligenceUI:
    def __init__(self, parent: tk.Frame):
        self.parent = parent
        self.parent.configure(bg=COLORS["bg"])
        self._build_ui()

    # -----------------------------------------------------------------------
    # Shell
    # -----------------------------------------------------------------------

    def _build_ui(self):
        hdr = tk.Frame(self.parent, bg=COLORS["panel"], pady=10)
        hdr.pack(fill="x", padx=20, pady=(20, 0))
        tk.Label(
            hdr, text="Smart Sales Intelligence",
            font=("Helvetica", 18, "bold"),
            bg=COLORS["panel"], fg=COLORS["white"]
        ).pack(side="left", padx=15)
        tk.Button(
            hdr, text="⟳  Refresh",
            bg=COLORS["button"], fg=COLORS["text"],
            font=("Helvetica", 9), relief="flat",
            padx=10, pady=4, cursor="hand2",
            command=self._refresh
        ).pack(side="right", padx=15)

        # Summary cards
        self._cards_frame = tk.Frame(self.parent, bg=COLORS["bg"])
        self._cards_frame.pack(fill="x", padx=20, pady=10)
        self._render_summary_cards()

        # Styled notebook
        style = ttk.Style()
        style.theme_use("default")
        style.configure("TNotebook",        background=COLORS["bg"], borderwidth=0)
        style.configure("TNotebook.Tab",
                        background=COLORS["panel"],
                        foreground=COLORS["text"],
                        padding=[12, 6],
                        font=("Helvetica", 10))
        style.map("TNotebook.Tab",
                  background=[("selected", COLORS["accent"])],
                  foreground=[("selected", COLORS["white"])])

        self._nb = ttk.Notebook(self.parent)
        self._nb.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        self._build_tab_reorder()
        self._build_tab_stockradar()
        self._build_tab_trends()
        self._build_tab_abc()
        self._build_tab_forecast()
        self._build_tab_peak_hours()

    # -----------------------------------------------------------------------
    # Summary cards
    # -----------------------------------------------------------------------

    def _render_summary_cards(self):
        for w in self._cards_frame.winfo_children():
            w.destroy()

        summary = intelligence.get_dashboard_summary()
        cards = [
            ("Critical Stockouts",  summary["critical_stockouts"], _RED,    "< 7 days left"),
            ("Needs Reorder",       summary["reorder_needed"],      _ORANGE, "order now"),
            ("Trending Up",         summary["trending_up"],         _GREEN,  "products this week"),
            ("Trending Down",       summary["trending_down"],       _PURPLE, "products this week"),
            ("Forecast Tomorrow",   f"${summary['forecast_tomorrow']:.2f}", _BLUE, "est. revenue"),
        ]
        for title, value, colour, subtitle in cards:
            card = tk.Frame(self._cards_frame, bg=colour, padx=14, pady=10)
            card.pack(side="left", fill="y", expand=True, padx=5)
            tk.Label(card, text=str(value),
                     font=("Helvetica", 22, "bold"),
                     bg=colour, fg="white").pack()
            tk.Label(card, text=title,
                     font=("Helvetica", 9, "bold"),
                     bg=colour, fg="white").pack()
            tk.Label(card, text=subtitle,
                     font=("Helvetica", 8),
                     bg=colour, fg="#ddd").pack()

    # -----------------------------------------------------------------------
    # Tab factory helpers
    # -----------------------------------------------------------------------

    def _make_tab(self, label: str) -> tk.Frame:
        frame = tk.Frame(self._nb, bg=COLORS["bg"])
        self._nb.add(frame, text=label)
        return frame

    def _make_tree(self, parent, columns, col_widths) -> ttk.Treeview:
        frame = tk.Frame(parent, bg=COLORS["bg"])
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        tree = ttk.Treeview(frame, columns=columns, show="headings")
        for col in columns:
            w = col_widths.get(col, 100)
            tree.heading(col, text=col.replace("_", " ").title())
            tree.column(col, width=w, anchor="center")
        if columns:
            tree.column(columns[0], anchor="w")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        return tree

    # -----------------------------------------------------------------------
    # Tab 1: Reorder Alerts
    # -----------------------------------------------------------------------

    def _build_tab_reorder(self):
        tab = self._make_tab("  Reorder Alerts  ")
        tk.Label(tab,
                 text="Products that need ordering before stock runs out",
                 font=("Helvetica", 10), bg=COLORS["bg"], fg=COLORS["muted"]
                 ).pack(anchor="w", padx=12, pady=(8, 0))
        cols   = ["product_name", "current_stock", "avg_daily_sales",
                  "days_remaining", "suggested_order_qty"]
        widths = {"product_name": 200, "current_stock": 100,
                  "avg_daily_sales": 120, "days_remaining": 120,
                  "suggested_order_qty": 140}
        self._reorder_tree = self._make_tree(tab, cols, widths)
        self._populate_reorder()

    def _populate_reorder(self):
        for r in self._reorder_tree.get_children():
            self._reorder_tree.delete(r)
        for item in intelligence.get_smart_reorder_suggestions():
            tag = "critical" if item["days_remaining"] < 7 else "warning"
            self._reorder_tree.insert("", "end", tags=(tag,), values=(
                item["product_name"],
                item["current_stock"],
                f"{item['avg_daily_sales']:.2f}/day",
                f"{item['days_remaining']} days",
                item["suggested_order_qty"],
            ))
        self._reorder_tree.tag_configure("critical", foreground=_RED)
        self._reorder_tree.tag_configure("warning",  foreground=_ORANGE)
        if not self._reorder_tree.get_children():
            self._reorder_tree.insert("", "end",
                values=("All products have adequate stock.", "", "", "", ""))

    # -----------------------------------------------------------------------
    # Tab 2: Stock Radar
    # -----------------------------------------------------------------------

    def _build_tab_stockradar(self):
        tab = self._make_tab("  Stock Radar  ")
        tk.Label(tab,
                 text="Predicted days until each product stocks out (30-day velocity)",
                 font=("Helvetica", 10), bg=COLORS["bg"], fg=COLORS["muted"]
                 ).pack(anchor="w", padx=12, pady=(8, 0))
        cols   = ["product_name", "current_stock", "avg_daily_sales",
                  "days_until_stockout", "urgency"]
        widths = {"product_name": 200, "current_stock": 100,
                  "avg_daily_sales": 120, "days_until_stockout": 140, "urgency": 90}
        self._radar_tree = self._make_tree(tab, cols, widths)
        self._populate_radar()

    def _populate_radar(self):
        for r in self._radar_tree.get_children():
            self._radar_tree.delete(r)
        for item in intelligence.get_stockout_predictions():
            self._radar_tree.insert("", "end", tags=(item["urgency"],), values=(
                item["product_name"],
                item["current_stock"],
                f"{item['avg_daily_sales']:.2f}/day",
                f"{item['days_until_stockout']} days",
                item["urgency"].upper(),
            ))
        self._radar_tree.tag_configure("critical", foreground=_RED)
        self._radar_tree.tag_configure("warning",  foreground=_ORANGE)
        self._radar_tree.tag_configure("ok",        foreground=_GREEN)

    # -----------------------------------------------------------------------
    # Tab 3: Trends
    # -----------------------------------------------------------------------

    def _build_tab_trends(self):
        tab = self._make_tab("  Trends  ")
        tk.Label(tab,
                 text="Sales velocity: last 7 days vs previous 7 days",
                 font=("Helvetica", 10), bg=COLORS["bg"], fg=COLORS["muted"]
                 ).pack(anchor="w", padx=12, pady=(8, 0))
        cols   = ["product_name", "recent_sales", "prev_sales",
                  "trend_pct", "direction"]
        widths = {"product_name": 200, "recent_sales": 110,
                  "prev_sales": 110, "trend_pct": 100, "direction": 90}
        self._trends_tree = self._make_tree(tab, cols, widths)
        self._populate_trends()

    def _populate_trends(self):
        for r in self._trends_tree.get_children():
            self._trends_tree.delete(r)
        arrows  = {"up": "↑ UP", "down": "↓ DOWN", "stable": "→ STABLE"}
        colours = {"up": _GREEN, "down": _RED, "stable": COLORS["muted"]}
        for item in intelligence.get_trending_products(limit=20):
            d = item["direction"]
            self._trends_tree.insert("", "end", tags=(d,), values=(
                item["product_name"],
                f"{item['recent_sales']:.1f} units",
                f"{item['prev_sales']:.1f} units",
                f"{item['trend_pct']:+.1f}%",
                arrows[d],
            ))
        for direction, colour in colours.items():
            self._trends_tree.tag_configure(direction, foreground=colour)

    # -----------------------------------------------------------------------
    # Tab 4: ABC Analysis
    # -----------------------------------------------------------------------

    def _build_tab_abc(self):
        tab = self._make_tab("  ABC Analysis  ")
        tk.Label(tab,
                 text="A = top revenue drivers  |  B = moderate  |  C = low contributors",
                 font=("Helvetica", 10), bg=COLORS["bg"], fg=COLORS["muted"]
                 ).pack(anchor="w", padx=12, pady=(8, 0))
        cols   = ["tier", "product_name", "revenue", "revenue_pct"]
        widths = {"tier": 60, "product_name": 220,
                  "revenue": 110, "revenue_pct": 110}
        self._abc_tree = self._make_tree(tab, cols, widths)
        self._populate_abc()

    def _populate_abc(self):
        for r in self._abc_tree.get_children():
            self._abc_tree.delete(r)
        data         = intelligence.get_abc_analysis()
        tier_colours = {"A": _GREEN, "B": _ORANGE, "C": COLORS["muted"]}
        for tier in ("A", "B", "C"):
            for item in data[tier]:
                self._abc_tree.insert("", "end", tags=(tier,), values=(
                    tier,
                    item["product_name"],
                    f"${item['revenue']:.2f}",
                    f"{item['revenue_pct']:.1f}%",
                ))
        for tier, colour in tier_colours.items():
            self._abc_tree.tag_configure(tier, foreground=colour)
        tk.Label(self._abc_tree.master,
                 text=f"Total revenue analysed: ${data['total_revenue']:.2f}",
                 font=("Helvetica", 9), bg=COLORS["bg"], fg=COLORS["muted"]
                 ).pack(anchor="e", padx=10)

    # -----------------------------------------------------------------------
    # Tab 5: Revenue Forecast
    # -----------------------------------------------------------------------

    def _build_tab_forecast(self):
        tab = self._make_tab("  Forecast  ")
        tk.Label(tab,
                 text="7-day revenue forecast (28-day rolling average)",
                 font=("Helvetica", 10), bg=COLORS["bg"], fg=COLORS["muted"]
                 ).pack(anchor="w", padx=12, pady=(8, 0))
        cols   = ["date", "forecasted_revenue", "confidence"]
        widths = {"date": 140, "forecasted_revenue": 160, "confidence": 100}
        self._forecast_tree = self._make_tree(tab, cols, widths)
        self._populate_forecast()

    def _populate_forecast(self):
        for r in self._forecast_tree.get_children():
            self._forecast_tree.delete(r)
        conf_colours = {"high": _GREEN, "medium": _ORANGE, "low": _RED}
        for item in intelligence.get_revenue_forecast(forecast_days=7):
            c = item["confidence"]
            self._forecast_tree.insert("", "end", tags=(c,), values=(
                item["date"],
                f"${item['forecasted_revenue']:.2f}",
                item["confidence"].upper(),
            ))
        for conf, colour in conf_colours.items():
            self._forecast_tree.tag_configure(conf, foreground=colour)

    # -----------------------------------------------------------------------
    # Tab 6: Peak Hours
    # -----------------------------------------------------------------------

    def _build_tab_peak_hours(self):
        tab = self._make_tab("  Peak Hours  ")
        container = tk.Frame(tab, bg=COLORS["bg"])
        container.pack(fill="both", expand=True, padx=10, pady=10)

        # Hourly (left)
        left = tk.Frame(container, bg=COLORS["bg"])
        left.pack(side="left", fill="both", expand=True, padx=(0, 5))
        tk.Label(left, text="By Hour of Day",
                 font=("Helvetica", 11, "bold"),
                 bg=COLORS["bg"], fg=COLORS["text"]
                 ).pack(anchor="w", pady=(0, 4))
        self._hourly_tree = ttk.Treeview(
            left, columns=["hour", "sales_count", "revenue"],
            show="headings", height=14
        )
        for col, label, width in [
            ("hour", "Hour", 90), ("sales_count", "Transactions", 110),
            ("revenue", "Revenue", 100)
        ]:
            self._hourly_tree.heading(col, text=label)
            self._hourly_tree.column(col, width=width, anchor="center")
        self._hourly_tree.pack(fill="both", expand=True)

        # Daily (right)
        right = tk.Frame(container, bg=COLORS["bg"])
        right.pack(side="left", fill="both", expand=True, padx=(5, 0))
        tk.Label(right, text="By Day of Week",
                 font=("Helvetica", 11, "bold"),
                 bg=COLORS["bg"], fg=COLORS["text"]
                 ).pack(anchor="w", pady=(0, 4))
        self._daily_tree = ttk.Treeview(
            right, columns=["day_name", "sales_count", "revenue"],
            show="headings", height=14
        )
        for col, label, width in [
            ("day_name", "Day", 100), ("sales_count", "Transactions", 110),
            ("revenue", "Revenue", 100)
        ]:
            self._daily_tree.heading(col, text=label)
            self._daily_tree.column(col, width=width, anchor="center")
        self._daily_tree.pack(fill="both", expand=True)

        self._populate_peak_hours()

    def _populate_peak_hours(self):
        data = intelligence.get_peak_hours_analysis()
        for r in self._hourly_tree.get_children():
            self._hourly_tree.delete(r)
        for item in data["hourly"]:
            h = item["hour"]
            self._hourly_tree.insert("", "end", values=(
                f"{h:02d}:00–{h:02d}:59",
                item["sales_count"],
                f"${item['revenue']:.2f}",
            ))
        for r in self._daily_tree.get_children():
            self._daily_tree.delete(r)
        for item in data["daily"]:
            self._daily_tree.insert("", "end", values=(
                item["day_name"],
                item["sales_count"],
                f"${item['revenue']:.2f}",
            ))

    # -----------------------------------------------------------------------
    # Refresh
    # -----------------------------------------------------------------------

    def _refresh(self):
        self._render_summary_cards()
        self._populate_reorder()
        self._populate_radar()
        self._populate_trends()
        self._populate_abc()
        self._populate_forecast()
        self._populate_peak_hours()
```

- [ ] **Step 2: Verify import:**

```bash
python -c "from ui.intelligence_ui import IntelligenceUI; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit:**

```bash
git add ui/intelligence_ui.py
git commit -m "feat: add Smart Sales Intelligence UI panel (6 tabs)"
```

---

## Task 12: Wire Intelligence into the Dashboard

**Files:**
- Modify: `ui/admin_dashboard.py`
- Modify: `ui/home_panel.py`

- [ ] **Step 1: In `ui/admin_dashboard.py`, add to the admin-only `nav_items` block:**

```python
# Inside: if user["role"] == "admin":
nav_items += [
    ("📈  Intelligence",    self._show_intelligence),
    # ... existing admin items ...
]
```

Add the handler method:
```python
def _show_intelligence(self):
    self._clear_content()
    from ui.intelligence_ui import IntelligenceUI
    IntelligenceUI(self.content)
```

- [ ] **Step 2: In `ui/home_panel.py`, in `_fetch_summary()`, add:**

```python
from modules.intelligence import get_dashboard_summary
intel = get_dashboard_summary()
```

Add to returned dict: `"critical_stockouts": intel["critical_stockouts"]`

In the `cards` list add:
```python
("⚠ Critical Stockouts", str(summary["critical_stockouts"]), "#e74c3c"),
```

- [ ] **Step 3: Launch and verify:**

```bash
python main.py
```
- Admin login → sidebar shows "📈  Intelligence" → click → 6-tab panel loads
- Home dashboard shows "⚠ Critical Stockouts" card
- Cashier login → Intelligence NOT visible (admin-only)

- [ ] **Step 4: Commit:**

```bash
git add ui/admin_dashboard.py ui/home_panel.py
git commit -m "feat: wire Intelligence panel into dashboard (admin) and home stats"
```

---

## Task 13: Full Regression Test Run

- [ ] **Step 1: Run the complete test suite:**

```bash
python -m unittest discover -s tests -v
```
Expected: ALL tests PASS. Zero failures across original tests + returns tests + intelligence tests.

- [ ] **Step 2: Manual smoke test:**

1. `python main.py`
2. Login as **admin** → check both "↩  Returns" and "📈  Intelligence" in sidebar
3. Create a new sale with 2+ products (New Sale screen)
4. Navigate to Returns → load that sale → double-click a row → set qty → enter reason → Process Return → return receipt appears
5. Navigate to Intelligence → verify all 6 tabs render and contain data
6. Check Home panel shows "⚠ Critical Stockouts" and "↩ Returns Today" cards
7. Login as **cashier** → confirm neither Returns nor Intelligence is visible

- [ ] **Step 3: Final commit:**

```bash
git add -A
git commit -m "feat: complete POS innovations — Returns & Refunds + Smart Sales Intelligence"
```

---

## Completion Checklist

**Feature 1: Returns & Refunds**
- [ ] `Returns` and `Return_Items` tables in schema
- [ ] `modules/returns.py` — fully implemented
- [ ] `modules/receipts.py` — `format_return_receipt` + `save_return_receipt_to_file`
- [ ] `modules/backup.py` — Returns tables included in CSV export
- [ ] `ui/returns_ui.py` — complete 3-phase UI
- [ ] Sidebar integration (manager + admin)
- [ ] Home dashboard card
- [ ] All tests green

**Feature 2: Smart Sales Intelligence**
- [ ] `modules/intelligence.py` — 8 analytics functions
- [ ] `ui/intelligence_ui.py` — 6-tab dashboard
- [ ] Sidebar integration (admin only)
- [ ] Home dashboard card
- [ ] All tests green

**Regression**
- [ ] Full test suite passes (original 81 + new tests)
- [ ] App launches, all features reachable, role gating correct
