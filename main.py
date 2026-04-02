"""
POS System — Entry Point
Run this file to start the application: python main.py

Default login credentials:
  Admin:   admin   / admin123
  Manager: manager1 / manager123
  Cashier: cashier1 / cashier123
"""

import tkinter as tk
import sys
import os

# Ensure all imports resolve from the project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.db_setup import initialize_database
from ui.login_screen import LoginScreen


def launch():
    """Initialize the database and open the login screen."""
    initialize_database()
    root = tk.Tk()
    LoginScreen(root)
    root.mainloop()


if __name__ == "__main__":
    launch()
