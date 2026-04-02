"""
Reports & Analytics module.
Provides 6 report types: daily sales, weekly sales, product performance,
inventory, cashier performance, and profit reports.
"""

import os
import sys
import csv
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db_setup import get_connection

EXPORTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "exports"
)
os.makedirs(EXPORTS_DIR, exist_ok=True)


# ── Report Functions ───────────────────────────────────────────────────────────

def daily_sales_report(date: str) -> dict:
    """
    Summary of sales for a single date (YYYY-MM-DD).
    Returns totals, transaction count, and top 5 products sold.
    """
    conn = get_connection()

    summary = conn.execute(
        """SELECT COUNT(*)                       AS transactions,
                  COALESCE(SUM(total_amount), 0) AS revenue,
                  COALESCE(SUM(subtotal),     0) AS subtotal,
                  COALESCE(SUM(discount),     0) AS total_discount,
                  COALESCE(SUM(tax),          0) AS total_tax
           FROM Sales
           WHERE DATE(date) = ?""",
        (date,)
    ).fetchone()

    top_products = conn.execute(
        """SELECT p.product_name,
                  SUM(si.quantity)             AS units_sold,
                  SUM(si.quantity * si.price)  AS revenue
           FROM Sales_Items si
           JOIN Sales    s ON si.sale_id    = s.sale_id
           JOIN Products p ON si.product_id = p.product_id
           WHERE DATE(s.date) = ?
           GROUP BY si.product_id
           ORDER BY units_sold DESC
           LIMIT 5""",
        (date,)
    ).fetchall()

    payment_breakdown = conn.execute(
        """SELECT payment_method,
                  COUNT(*)          AS count,
                  SUM(total_amount) AS total
           FROM Sales
           WHERE DATE(date) = ?
           GROUP BY payment_method""",
        (date,)
    ).fetchall()

    conn.close()

    return {
        "report_type": "Daily Sales Report",
        "date": date,
        "transactions":    summary["transactions"],
        "revenue":         round(summary["revenue"],         2),
        "subtotal":        round(summary["subtotal"],        2),
        "total_discount":  round(summary["total_discount"],  2),
        "total_tax":       round(summary["total_tax"],       2),
        "top_products":    [dict(r) for r in top_products],
        "payment_breakdown": [dict(r) for r in payment_breakdown],
    }


def weekly_sales_report(start_date: str, end_date: str) -> dict:
    """
    Aggregated sales summary between start_date and end_date (inclusive).
    Also returns a day-by-day breakdown.
    """
    conn = get_connection()

    summary = conn.execute(
        """SELECT COUNT(*)                       AS transactions,
                  COALESCE(SUM(total_amount), 0) AS revenue,
                  COALESCE(SUM(discount),     0) AS total_discount,
                  COALESCE(SUM(tax),          0) AS total_tax
           FROM Sales
           WHERE DATE(date) BETWEEN ? AND ?""",
        (start_date, end_date)
    ).fetchone()

    daily = conn.execute(
        """SELECT DATE(date) AS day,
                  COUNT(*)                       AS transactions,
                  COALESCE(SUM(total_amount), 0) AS revenue
           FROM Sales
           WHERE DATE(date) BETWEEN ? AND ?
           GROUP BY DATE(date)
           ORDER BY day""",
        (start_date, end_date)
    ).fetchall()

    conn.close()

    return {
        "report_type":    "Weekly / Period Sales Report",
        "start_date":     start_date,
        "end_date":       end_date,
        "transactions":   summary["transactions"],
        "revenue":        round(summary["revenue"],        2),
        "total_discount": round(summary["total_discount"], 2),
        "total_tax":      round(summary["total_tax"],      2),
        "daily_breakdown": [dict(r) for r in daily],
    }


def product_performance_report() -> dict:
    """
    All-time sales performance per product: units sold, revenue, and rank.
    """
    conn = get_connection()

    rows = conn.execute(
        """SELECT p.product_id,
                  p.product_name,
                  p.category,
                  p.price                        AS current_price,
                  p.quantity                     AS current_stock,
                  COALESCE(SUM(si.quantity), 0)  AS units_sold,
                  COALESCE(SUM(si.quantity * si.price), 0) AS revenue
           FROM Products p
           LEFT JOIN Sales_Items si ON p.product_id = si.product_id
           GROUP BY p.product_id
           ORDER BY units_sold DESC"""
    ).fetchall()

    conn.close()

    products = [dict(r) for r in rows]
    for p in products:
        p["revenue"] = round(p["revenue"], 2)

    return {
        "report_type": "Product Performance Report",
        "products":    products,
    }


def inventory_report() -> dict:
    """
    Current stock levels for all products with low-stock and out-of-stock flags.
    Also returns the 20 most recent stock adjustments.
    """
    from database.db_setup import get_setting

    threshold = int(get_setting("low_stock_threshold") or 5)

    conn = get_connection()

    stock = conn.execute(
        """SELECT product_id, product_name, category, price, quantity, barcode
           FROM Products
           ORDER BY quantity ASC, product_name"""
    ).fetchall()

    recent_log = conn.execute(
        """SELECT i.date, p.product_name, i.adjustment, i.reason
           FROM Inventory i
           JOIN Products p ON i.product_id = p.product_id
           ORDER BY i.date DESC
           LIMIT 20"""
    ).fetchall()

    conn.close()

    products = []
    low_count = out_count = 0
    for r in stock:
        p = dict(r)
        if p["quantity"] == 0:
            p["status"] = "out"
            out_count += 1
        elif p["quantity"] <= threshold:
            p["status"] = "low"
            low_count += 1
        else:
            p["status"] = "ok"
        products.append(p)

    return {
        "report_type":   "Inventory Report",
        "threshold":     threshold,
        "total_products": len(products),
        "low_stock_count": low_count,
        "out_of_stock_count": out_count,
        "products":      products,
        "recent_log":    [dict(r) for r in recent_log],
    }


def cashier_performance_report(start_date: str = None, end_date: str = None) -> dict:
    """
    Sales totals and transaction counts per cashier.
    If no dates are provided, returns all-time data.
    """
    conn = get_connection()

    if start_date and end_date:
        rows = conn.execute(
            """SELECT u.username AS cashier,
                      COUNT(*)                       AS transactions,
                      COALESCE(SUM(s.total_amount), 0) AS revenue,
                      COALESCE(AVG(s.total_amount), 0) AS avg_sale
               FROM Sales s
               JOIN Users u ON s.user_id = u.user_id
               WHERE DATE(s.date) BETWEEN ? AND ?
               GROUP BY s.user_id
               ORDER BY revenue DESC""",
            (start_date, end_date)
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT u.username AS cashier,
                      COUNT(*)                       AS transactions,
                      COALESCE(SUM(s.total_amount), 0) AS revenue,
                      COALESCE(AVG(s.total_amount), 0) AS avg_sale
               FROM Sales s
               JOIN Users u ON s.user_id = u.user_id
               GROUP BY s.user_id
               ORDER BY revenue DESC"""
        ).fetchall()

    conn.close()

    cashiers = []
    for r in rows:
        c = dict(r)
        c["revenue"]  = round(c["revenue"],  2)
        c["avg_sale"] = round(c["avg_sale"], 2)
        cashiers.append(c)

    return {
        "report_type": "Cashier Performance Report",
        "start_date":  start_date or "All time",
        "end_date":    end_date   or "All time",
        "cashiers":    cashiers,
    }


def profit_report(start_date: str, end_date: str) -> dict:
    """
    Revenue breakdown (subtotal, discount, tax, net) aggregated by day
    between start_date and end_date.
    """
    conn = get_connection()

    totals = conn.execute(
        """SELECT COALESCE(SUM(total_amount), 0) AS revenue,
                  COALESCE(SUM(subtotal),     0) AS subtotal,
                  COALESCE(SUM(discount),     0) AS total_discount,
                  COALESCE(SUM(tax),          0) AS total_tax,
                  COUNT(*)                        AS transactions
           FROM Sales
           WHERE DATE(date) BETWEEN ? AND ?""",
        (start_date, end_date)
    ).fetchone()

    by_day = conn.execute(
        """SELECT DATE(date)                    AS day,
                  COUNT(*)                      AS transactions,
                  SUM(total_amount)             AS revenue,
                  SUM(subtotal)                 AS subtotal,
                  SUM(discount)                 AS discount,
                  SUM(tax)                      AS tax
           FROM Sales
           WHERE DATE(date) BETWEEN ? AND ?
           GROUP BY DATE(date)
           ORDER BY day""",
        (start_date, end_date)
    ).fetchall()

    conn.close()

    daily = []
    for r in by_day:
        d = dict(r)
        for key in ("revenue", "subtotal", "discount", "tax"):
            d[key] = round(d[key] or 0, 2)
        daily.append(d)

    return {
        "report_type":    "Profit Report",
        "start_date":     start_date,
        "end_date":       end_date,
        "transactions":   totals["transactions"],
        "revenue":        round(totals["revenue"]        or 0, 2),
        "subtotal":       round(totals["subtotal"]       or 0, 2),
        "total_discount": round(totals["total_discount"] or 0, 2),
        "total_tax":      round(totals["total_tax"]      or 0, 2),
        "daily_breakdown": daily,
    }


# ── CSV Export ─────────────────────────────────────────────────────────────────

def export_report_to_csv(report_data: dict) -> tuple[bool, str]:
    """
    Write any report dict to a CSV file in /exports/.
    The 'products', 'cashiers', 'daily_breakdown', or 'top_products' key
    is used as the row data; header is derived from keys.
    Returns (success, filepath_or_error).
    """
    # Determine which list to export
    for key in ("products", "cashiers", "daily_breakdown",
                "top_products", "payment_breakdown"):
        rows = report_data.get(key)
        if rows:
            break
    else:
        rows = None

    if not rows:
        return False, "No tabular data found in report to export."

    ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = report_data.get("report_type", "report").replace(" ", "_").replace("/", "-")
    filename  = f"{safe_name}_{ts}.csv"
    filepath  = os.path.join(EXPORTS_DIR, filename)

    try:
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        return True, filepath
    except OSError as e:
        return False, f"Could not write CSV: {e}"
