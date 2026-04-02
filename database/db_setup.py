"""
Database initialization for the POS system.
Creates all tables and seeds default data on first run.
Uses SQLite (built-in, no server required).
"""

import sqlite3
import os
import sys

# Add project root to path so we can import utils
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.security import hash_password

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pos_database.db")


def get_connection() -> sqlite3.Connection:
    """Open and return a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row      # rows accessible like dicts
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_database():
    """Create all tables if they don't exist, then seed default data."""
    conn = get_connection()
    cursor = conn.cursor()

    # ── Users ────────────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Users (
            user_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT    NOT NULL UNIQUE,
            password_hash TEXT  NOT NULL,
            role        TEXT    NOT NULL CHECK(role IN ('admin', 'manager', 'cashier')),
            is_active   INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT    NOT NULL
        )
    """)

    # ── Products ─────────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Products (
            product_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT    NOT NULL,
            category     TEXT    NOT NULL,
            price        REAL    NOT NULL CHECK(price >= 0),
            quantity     INTEGER NOT NULL DEFAULT 0 CHECK(quantity >= 0),
            barcode      TEXT    UNIQUE
        )
    """)

    # ── Customers ────────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Customers (
            customer_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            name           TEXT NOT NULL,
            phone          TEXT UNIQUE,
            email          TEXT,
            address        TEXT,
            loyalty_points INTEGER NOT NULL DEFAULT 0
        )
    """)

    # ── Sales ────────────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Sales (
            sale_id        TEXT    PRIMARY KEY,
            date           TEXT    NOT NULL,
            user_id        INTEGER NOT NULL REFERENCES Users(user_id),
            customer_id    INTEGER REFERENCES Customers(customer_id),
            subtotal       REAL    NOT NULL DEFAULT 0,
            discount       REAL    NOT NULL DEFAULT 0,
            tax            REAL    NOT NULL DEFAULT 0,
            total_amount   REAL    NOT NULL DEFAULT 0,
            payment_method TEXT    NOT NULL
        )
    """)

    # ── Sales Items ──────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Sales_Items (
            sale_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id      TEXT    NOT NULL REFERENCES Sales(sale_id),
            product_id   INTEGER NOT NULL REFERENCES Products(product_id),
            quantity     INTEGER NOT NULL CHECK(quantity > 0),
            price        REAL    NOT NULL
        )
    """)

    # ── Inventory Log ────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Inventory (
            inventory_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id   INTEGER NOT NULL REFERENCES Products(product_id),
            adjustment   INTEGER NOT NULL,
            reason       TEXT    NOT NULL,
            date         TEXT    NOT NULL
        )
    """)

    # ── Payments ─────────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Payments (
            payment_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id      TEXT    NOT NULL REFERENCES Sales(sale_id),
            amount_paid  REAL    NOT NULL,
            change_given REAL    NOT NULL DEFAULT 0,
            payment_type TEXT    NOT NULL,
            payment_status TEXT  NOT NULL DEFAULT 'COMPLETED'
                         CHECK(payment_status IN ('PENDING','COMPLETED','FAILED','REFUNDED')),
            provider     TEXT,
            external_reference TEXT,
            paid_at      TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Payment_Events (
            event_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            payment_ref    TEXT,
            source         TEXT NOT NULL,
            event_type     TEXT NOT NULL,
            event_status   TEXT NOT NULL,
            payload_json   TEXT,
            received_at    TEXT NOT NULL
        )
    """)

    # ── Returns ──────────────────────────────────────────────────────────────
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

    # ── Return Items ─────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Return_Items (
            return_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            return_id      TEXT    NOT NULL REFERENCES Returns(return_id),
            sale_item_id   INTEGER NOT NULL REFERENCES Sales_Items(sale_item_id),
            product_id     INTEGER NOT NULL REFERENCES Products(product_id),
            quantity       INTEGER NOT NULL CHECK(quantity > 0),
            price          REAL    NOT NULL CHECK(price >= 0),
            restocked      INTEGER NOT NULL DEFAULT 1
        )
    """)

    # ── Transaction Logs ─────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Transaction_Logs (
            log_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id   INTEGER REFERENCES Users(user_id),
            action    TEXT NOT NULL,
            details   TEXT,
            timestamp TEXT NOT NULL
        )
    """)

    # ── MoMo Transactions ────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS MoMo_Transactions (
            txn_id         TEXT PRIMARY KEY,
            sale_id        TEXT REFERENCES Sales(sale_id),
            phone          TEXT NOT NULL,
            amount         REAL NOT NULL,
            provider       TEXT NOT NULL,
            reference      TEXT NOT NULL UNIQUE,
            status         TEXT NOT NULL DEFAULT 'PENDING'
                           CHECK(status IN ('PENDING','SUCCESS','FAILED','EXPIRED')),
            failure_reason TEXT,
            created_at     TEXT NOT NULL,
            updated_at     TEXT NOT NULL
        )
    """)

    # ── Card Transactions ─────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Card_Transactions (
            txn_id       TEXT PRIMARY KEY,
            sale_id      TEXT REFERENCES Sales(sale_id),
            card_type    TEXT NOT NULL,
            last_four    TEXT,
            amount       REAL NOT NULL,
            terminal_ref TEXT,
            status       TEXT NOT NULL DEFAULT 'MANUAL'
                         CHECK(status IN ('MANUAL','APPROVED','DECLINED','ERROR')),
            created_at   TEXT NOT NULL
        )
    """)

    # ── Settings ─────────────────────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    conn.commit()
    _migrate_schema(conn)
    _seed_defaults(cursor, conn)
    conn.close()


def _migrate_schema(conn: sqlite3.Connection):
    """Apply lightweight additive migrations for older DB files."""
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(Payments)")
    cols = {r[1] for r in cursor.fetchall()}

    if "payment_status" not in cols:
        cursor.execute(
            "ALTER TABLE Payments ADD COLUMN payment_status TEXT NOT NULL DEFAULT 'COMPLETED'"
        )
    if "provider" not in cols:
        cursor.execute("ALTER TABLE Payments ADD COLUMN provider TEXT")
    if "external_reference" not in cols:
        cursor.execute("ALTER TABLE Payments ADD COLUMN external_reference TEXT")
    if "paid_at" not in cols:
        cursor.execute("ALTER TABLE Payments ADD COLUMN paid_at TEXT")

    conn.commit()


def _seed_defaults(cursor: sqlite3.Cursor, conn: sqlite3.Connection):
    """Insert default data only if the tables are empty."""

    # Default admin user
    cursor.execute("SELECT COUNT(*) FROM Users")
    if cursor.fetchone()[0] == 0:
        from utils.helpers import current_timestamp
        users = [
            ("admin",   hash_password("admin123"),   "admin"),
            ("manager1",hash_password("manager123"), "manager"),
            ("cashier1",hash_password("cashier123"), "cashier"),
        ]
        cursor.executemany(
            "INSERT INTO Users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            [(u, p, r, current_timestamp()) for u, p, r in users]
        )

    # Sample products
    cursor.execute("SELECT COUNT(*) FROM Products")
    if cursor.fetchone()[0] == 0:
        products = [
            ("Coca Cola 500ml", "Beverages",  1.50, 100, "8901234567890"),
            ("Bread Loaf",      "Bakery",     2.00,  50, "8901234567891"),
            ("Milk 1L",         "Dairy",      1.20,  80, "8901234567892"),
            ("Rice 1kg",        "Grains",     3.50,  60, "8901234567893"),
            ("Eggs (12 pack)",  "Dairy",      4.00,  40, "8901234567894"),
        ]
        cursor.executemany(
            "INSERT INTO Products (product_name, category, price, quantity, barcode) VALUES (?, ?, ?, ?, ?)",
            products
        )

    # Default settings
    cursor.execute("SELECT COUNT(*) FROM Settings")
    if cursor.fetchone()[0] == 0:
        settings = [
            ("store_name",       "My POS Store"),
            ("store_address",    "123 Main Street"),
            ("store_phone",      "+1-800-000-0000"),
            ("tax_rate",         "0.16"),
            ("low_stock_threshold", "5"),
            ("currency_symbol",  "₵"),
        ]
        cursor.executemany("INSERT INTO Settings (key, value) VALUES (?, ?)", settings)

    conn.commit()


def get_setting(key: str) -> str:
    """Retrieve a single setting value by key."""
    conn = get_connection()
    row = conn.execute("SELECT value FROM Settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else ""


def update_setting(key: str, value: str):
    """Update a setting value by key."""
    conn = get_connection()
    conn.execute("INSERT OR REPLACE INTO Settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    initialize_database()
