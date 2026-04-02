"""
Base test class: spins up a fresh isolated SQLite database for each test class.

Every test class that inherits from PosTestCase runs against a temporary DB
that is torn down after the class finishes — production data is never touched.
"""

import os
import sys
import unittest
import tempfile

# Point modules at the project root
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)


def add_product_get_id(name, category, price, qty, barcode):
    """Wrapper: add a product and return its database ID."""
    from modules.products import add_product, get_product_by_barcode
    ok, msg = add_product(name, category, price, qty, barcode)
    assert ok, f"add_product failed: {msg}"
    row = get_product_by_barcode(barcode)
    assert row is not None, f"Product not found after insert: {barcode}"
    return row["product_id"]


class PosTestCase(unittest.TestCase):
    """
    Base class that patches database.db_setup.DB_PATH to a temp file,
    initializes the schema, and deletes the file after the class finishes.

    Pattern borrowed from E2E fixture setup (beforeAll / afterAll).
    """

    @classmethod
    def setUpClass(cls):
        """Create isolated temp database and initialize schema."""
        import database.db_setup as db_mod

        cls._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls._tmp.close()
        cls._original_db_path = db_mod.DB_PATH
        db_mod.DB_PATH = cls._tmp.name          # redirect all connections
        db_mod.initialize_database()            # create tables + seed defaults

    @classmethod
    def tearDownClass(cls):
        """Restore original DB path and delete temp file."""
        import database.db_setup as db_mod
        db_mod.DB_PATH = cls._original_db_path
        try:
            os.unlink(cls._tmp.name)
        except OSError:
            pass
