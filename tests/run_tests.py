"""
Test runner — Day 13 integration test suite.
Discovers all test_*.py files in this folder and runs them.

Usage:
    python tests/run_tests.py
    python tests/run_tests.py -v           # verbose
"""

import sys
import os
import unittest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

VERBOSITY = 2 if "-v" in sys.argv else 1


def run():
    loader = unittest.TestLoader()
    suite  = loader.discover(
        start_dir=os.path.dirname(os.path.abspath(__file__)),
        pattern="test_*.py",
    )

    runner = unittest.TextTestRunner(verbosity=VERBOSITY, stream=sys.stdout)
    result = runner.run(suite)

    # Exit with non-zero code if any tests failed (useful for CI)
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    run()
