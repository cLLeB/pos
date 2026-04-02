================================================================================
  POS SYSTEM — Point of Sale Application
  Structured Programming Project
================================================================================

  Stack  : Python 3.10+ | Tkinter (GUI) | SQLite (database)
  Author : [Your Name]
  Version: 1.0.0

================================================================================
  QUICK START
================================================================================

  1. Make sure Python 3.10 or newer is installed:
       python --version

  2. No external packages needed — every library used is part of the
     Python standard library (tkinter, sqlite3, hashlib, csv, shutil ...).

  3. Run the application:
       python main.py

  4. (Optional) Enable real-time Paystack MoMo:
       Set environment variables before starting the app:
         MOMO_PROVIDER_MODE=paystack
         PAYSTACK_PUBLIC_KEY=pk_test_ecb64d8f2f5f2167210a2f87c37e94d1a7b4e460
         PAYSTACK_SECRET_KEY=sk_test_xxxxxxxxxxxxx
         PAYSTACK_CUSTOMER_EMAIL=payments@yourstore.com

       Live public key (switch when going live):
         PAYSTACK_PUBLIC_KEY=pk_live_09be1b7da418b5dd065b58088c8b72a909318925

       Then start the webhook listener in another terminal:
         python paystack_webhook_server.py

  5. (Optional) Deploy webhook service to Render (recommended for live mode):
       - `render.yaml` is included for one-click blueprint deploy.
    - Set `PAYSTACK_PUBLIC_KEY` (test first, then live when ready).
       - Set secret env var `PAYSTACK_SECRET_KEY` in Render dashboard.
       - Render automatically provides a public domain.
       - Set Paystack webhook URL to:
           https://<your-render-domain>/webhook/paystack

  The database file (pos_database.db) is created automatically on first run
  inside the  database/  folder.

================================================================================
  DEFAULT LOGIN CREDENTIALS
================================================================================

  Role     | Username  | Password
  ---------|-----------|----------
  Admin    | admin     | admin123
  Manager  | manager1  | manager123
  Cashier  | cashier1  | cashier123

  IMPORTANT: Change these passwords after the first login via the
  Settings → Users screen.

================================================================================
  USER ROLES & ACCESS
================================================================================

  ADMIN
    Full access: Products, Inventory, Customers, New Sale,
                 Reports, Backup & Recovery, User Management, Settings.

  MANAGER
    Operations access: Products, Inventory, Customers, New Sale, Reports, Returns.
    Cannot access: Backup, User Management, Settings.

  CASHIER
    Goes directly to the cashier POS screen.
    No access to the admin dashboard.

  Session Timeout: All roles are automatically logged out after 30 minutes
  of inactivity.

================================================================================
  MODULE OVERVIEW
================================================================================

  Module 1 — Authentication (modules/auth.py)
    Login with username + password. Role-based routing. Session management.
    Transaction log records every login and logout.

  Module 2 — Product Management (modules/products.py, ui/product_ui.py)
    Add, edit, delete, and search products by name or barcode.
    Duplicate barcode detection. Category management.

  Module 3 — Inventory Management (modules/inventory.py, ui/inventory_ui.py)
    Real-time stock tracking. Manual stock adjustments with reason logging.
    Low-stock alerts when quantity falls at or below the configured threshold.
    Full adjustment history log.

  Module 4 — Sales Processing (modules/sales.py, ui/cashier_screen.py)
    Barcode scan or name search to add items to cart.
    Cart supports editing quantities and removing items.
    Calculates subtotal, discount (fixed amount), 16% tax, and total.
    Inventory automatically deducted after every confirmed sale.

  Module 5 — Payment Processing (modules/payments.py, ui/payment_dialog.py)
    Supports three payment methods:
      Cash       — enter amount tendered, change calculated automatically.
      Mobile Money — select provider (MTN/Airtel/Vodafone), enter reference.
      Card       — select card type (Visa/Mastercard/Amex).

    Real-time MoMo via Paystack (April 2026 update):
      - `modules/paystack.py` handles charge + verify + webhook signature checks.
      - `modules/momo.py` now supports `MOMO_PROVIDER_MODE=paystack`.
      - `paystack_webhook_server.py` receives `POST /webhook/paystack` callbacks.
      - Webhook events are logged into `Payment_Events` for reconciliation.
      - Admin/Manager dashboard now includes `Payments Live` monitor.

  Module 6 — Customer Management (modules/customers.py, ui/customer_ui.py)
    Register customer profiles (name, phone, email, address).
    Link customers to sales for purchase history tracking.
    Loyalty points: earn 1 point per $10 spent; redeem 1 point = $0.10 off.
    Walk-in sales require no customer selection.

  Module 7 — Receipt Generation (modules/receipts.py, ui/receipt_window.py)
    Auto-generated after every completed sale.
    Shows store info, itemised list, totals, payment details, loyalty balance.
    Print to default system printer or save as .txt file in /receipts/.

  Module 8 — Reports & Analytics (modules/reports.py, ui/reports_ui.py)
    Six report types:
      1. Daily Sales          — transactions, revenue, top products
      2. Weekly / Period      — day-by-day breakdown for any date range
      3. Product Performance  — ranked by units sold and revenue
      4. Inventory Status     — stock levels with low/out-of-stock flags
      5. Cashier Performance  — sales totals and averages per cashier
      6. Profit Report        — revenue, discount, and tax by day
    All reports can be exported to CSV (saved in /exports/).

  Module 9 — Returns & Refunds (modules/returns.py, ui/returns_ui.py)
    Search by Sale ID to load the original transaction.
    Select items and enter return quantities per line item.
    Optionally restock returned items (restores inventory automatically).
    Generates and saves a formatted return receipt.
    Accessible to managers and admins.

  Optional — Backup & Recovery (modules/backup.py, ui/backup_ui.py)
    Create timestamped database backups in /backups/.
    Restore from any backup (a safety pre-restore snapshot is auto-created).
    Export every database table to CSV in /exports/.
    View the full transaction audit log.

  Optional — User Management (ui/users_ui.py)
    Admin-only: add users, change roles, reset passwords, deactivate accounts.

  Optional — Settings (ui/settings_ui.py)
    Store name, address, phone number, currency symbol, tax rate,
    low-stock threshold — all saved to the database and read at runtime.

================================================================================
  FILE & FOLDER STRUCTURE
================================================================================

  POS_System/
  ├── main.py                   Entry point — run this to start the app
  ├── paystack_webhook_server.py Local webhook receiver for Paystack events
  ├── render.yaml               Render blueprint (webhook deployment)
  ├── requirements.txt          Dependency manifest for cloud builds
  ├── runtime.txt               Python runtime pin for Render
  ├── README.txt                This file
  │
  ├── database/
  │   ├── db_setup.py           Schema creation, seeding, DB helpers
  │   └── pos_database.db       SQLite database (auto-created on first run)
  │
  ├── modules/                  Business logic (no UI code)
  │   ├── auth.py               Authentication & session management
  │   ├── products.py           Product CRUD
  │   ├── inventory.py          Stock tracking & adjustment log
  │   ├── sales.py              Sale creation & cart calculations
  │   ├── payments.py           Payment processing (cash, mobile, card)
  │   ├── paystack.py           Paystack client (MoMo charge/verify/webhook)
  │   ├── customers.py          Customer profiles & loyalty points
  │   ├── receipts.py           Receipt generation, formatting, printing
  │   ├── reports.py            All six report types & CSV export
  │   ├── returns.py            Returns & refunds processing, stock restoration
  │   └── backup.py             DB backup/restore, CSV export, audit log
  │
  ├── ui/                       Tkinter screens and dialogs
  │   ├── login_screen.py       Login window & shared COLORS palette
  │   ├── admin_dashboard.py    Admin/Manager dashboard with sidebar nav
  │   ├── home_panel.py         Dashboard home — summary cards & stats
  │   ├── cashier_screen.py     Main POS cashier interface
  │   ├── payment_dialog.py     Cash/Mobile/Card payment modal
  │   ├── payment_monitor_ui.py Real-time payment/webhook operations panel
  │   ├── receipt_window.py     Receipt viewer (print / save / close)
  │   ├── product_ui.py         Product management table & dialogs
  │   ├── inventory_ui.py       Inventory levels & adjustment dialogs
  │   ├── customer_ui.py        Customer management, history, loyalty
  │   ├── reports_ui.py         Report generator with date picker & CSV export
  │   ├── returns_ui.py         Returns & refunds panel (manager + admin)
  │   ├── backup_ui.py          Backup panel & audit log viewer
  │   ├── users_ui.py           User management (admin only)
  │   └── settings_ui.py        System settings editor (admin only)
  │
  ├── utils/
  │   ├── security.py           Password hashing (SHA-256 + salt)
  │   └── helpers.py            Shared utilities (transaction IDs, totals)
  │
  ├── tests/                    Integration test suite (Day 13)
  │   ├── run_tests.py          Run all tests: python tests/run_tests.py
  │   ├── test_auth.py          Authentication scenarios
  │   ├── test_products_inventory.py  Product & inventory scenarios
  │   ├── test_sales_flow.py    Full sale flow scenarios
  │   ├── test_customers.py     Customer & loyalty scenarios
  │   ├── test_reports_backup.py      Reports & backup scenarios
  │   └── test_returns.py       Returns & refunds scenarios
  │
  ├── receipts/                 Saved .txt receipt files
  ├── backups/                  Timestamped .db backup files
  └── exports/                  CSV exports from reports and backup

================================================================================
  RENDER DEPLOYMENT (LIVE PAYMENTS)
================================================================================

  Why deploy?
    Paystack webhooks need a public HTTPS URL. Render gives you that domain
    without managing your own server.

  Option A: Blueprint deploy (recommended)
    1. Push this repo to GitHub.
    2. In Render: New + -> Blueprint -> select your repo.
    3. Confirm service from `render.yaml`.
    4. In Render service env vars, set:
         PAYSTACK_PUBLIC_KEY = pk_test_ecb64d8f2f5f2167210a2f87c37e94d1a7b4e460
         PAYSTACK_SECRET_KEY = sk_live_...
       (keep MOMO_PROVIDER_MODE=paystack)
    5. Deploy.

    Staged rollout (recommended):
      - Phase 1 (simulation): keep test keys
          PAYSTACK_PUBLIC_KEY = pk_test_ecb64d8f2f5f2167210a2f87c37e94d1a7b4e460
          PAYSTACK_SECRET_KEY = sk_test_...
      - Phase 2 (go live): switch both keys
          PAYSTACK_PUBLIC_KEY = pk_live_09be1b7da418b5dd065b58088c8b72a909318925
          PAYSTACK_SECRET_KEY = sk_live_...

  Option B: Manual web service deploy
    Build command:
      pip install -r requirements.txt
    Start command:
      python paystack_webhook_server.py
    Health check path:
      /health

  After deploy
    1. Copy your Render URL, e.g. https://pos-paystack-webhook.onrender.com
    2. In Paystack Dashboard -> Settings -> Webhooks:
         https://pos-paystack-webhook.onrender.com/webhook/paystack
    3. Keep desktop POS running with:
         MOMO_PROVIDER_MODE=paystack
      PAYSTACK_PUBLIC_KEY=pk_live_09be1b7da418b5dd065b58088c8b72a909318925
         PAYSTACK_SECRET_KEY=sk_live_...

  Go-live checklist
    [ ] Paystack account verified and in Live mode
    [ ] Render webhook endpoint deployed and healthy (/health returns ok)
    [ ] Paystack webhook URL saved and enabled
    [ ] POS environment uses live secret key
    [ ] Test with a small real MoMo amount first

================================================================================
  RUNNING THE TEST SUITE
================================================================================

  All integration tests run against a temporary isolated database —
  production data is never affected.

    python tests/run_tests.py          # summary output
    python tests/run_tests.py -v       # verbose (test-by-test)

================================================================================
  KEYBOARD SHORTCUTS (Cashier Screen)
================================================================================

  F1          Focus the search / barcode field
  F5          Clear the cart (with confirmation)
  Delete      Remove the selected cart item
  Enter       Add item by barcode (in search field)
  Double-click  Edit quantity of a cart item

================================================================================
  TECHNICAL NOTES
================================================================================

  - Database: SQLite with foreign-key enforcement (PRAGMA foreign_keys = ON).
    All queries use parameterised statements — no SQL injection risk.

  - Passwords: SHA-256 with a random per-user salt stored as "salt:hash".
    Plain-text passwords are never written to disk.

  - Tax rate: stored as a decimal (0.16 = 16%) in the Settings table.
    The Settings screen accepts and displays it as a percentage (16).

  - Transaction IDs: UUID4-based, prefixed "TXN-" (e.g. TXN-A1B2C3D4).

  - Loyalty points: 1 point per $10 spent (rounded down). Redemption rate:
    1 point = $0.10 discount applied before tax.

  - Session timeout: 30 minutes of mouse/keyboard inactivity triggers
    automatic logout on both the admin dashboard and the cashier screen.

  - Backup safety: every database restore first saves a "pre_restore_*"
    snapshot so the previous state can always be recovered.

  - Real-time MoMo callbacks:
      The local app can process asynchronous Paystack events through
      `paystack_webhook_server.py` at `/webhook/paystack`.
      In production, expose this endpoint publicly (e.g., VPS + HTTPS)
      and register that URL in your Paystack dashboard.

================================================================================
