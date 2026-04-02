"""
Receipt Generation module.
Builds receipt data from the DB, formats it as text, saves to file,
and optionally sends to a system printer.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_setup import get_connection, get_setting

# Folder where .txt receipts are saved
RECEIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "receipts"
)
os.makedirs(RECEIPTS_DIR, exist_ok=True)

RECEIPT_WIDTH = 42   # characters wide (fits 80mm thermal paper)


# ── Public API ────────────────────────────────────────────────────────────────

def generate_receipt(sale_id: str) -> dict:
    """
    Build and return a receipt dict from the database.
    The dict contains everything needed to render the receipt.
    Returns None if sale_id is not found.
    """
    conn = get_connection()

    sale = conn.execute(
        """SELECT s.*, u.username AS cashier_name,
                  c.name         AS customer_name,
                  c.loyalty_points AS customer_points
           FROM Sales s
           LEFT JOIN Users     u ON s.user_id     = u.user_id
           LEFT JOIN Customers c ON s.customer_id = c.customer_id
           WHERE s.sale_id = ?""",
        (sale_id,)
    ).fetchone()

    if not sale:
        conn.close()
        return None

    items = conn.execute(
        """SELECT si.quantity, si.price,
                  (si.quantity * si.price) AS line_total,
                  p.product_name
           FROM Sales_Items si
           JOIN Products p ON si.product_id = p.product_id
           WHERE si.sale_id = ?""",
        (sale_id,)
    ).fetchall()

    payment = conn.execute(
        "SELECT * FROM Payments WHERE sale_id = ?", (sale_id,)
    ).fetchone()

    conn.close()

    # Loyalty points earned this sale (1 per $10)
    points_earned = int(sale["total_amount"] // 10) if sale["customer_id"] else 0

    return {
        # Store info (from Settings)
        "store_name":    get_setting("store_name"),
        "store_address": get_setting("store_address"),
        "store_phone":   get_setting("store_phone"),
        "currency":      get_setting("currency_symbol") or "₵",

        # Sale header
        "sale_id":       sale["sale_id"],
        "date":          sale["date"],
        "cashier":       sale["cashier_name"] or "—",

        # Customer
        "customer_name":   sale["customer_name"],
        "customer_points": sale["customer_points"],
        "points_earned":   points_earned,

        # Items
        "items": [
            {
                "name":       i["product_name"],
                "qty":        i["quantity"],
                "unit_price": i["price"],
                "line_total": round(i["line_total"], 2),
            }
            for i in items
        ],

        # Totals
        "subtotal":     sale["subtotal"],
        "discount":     sale["discount"],
        "tax":          sale["tax"],
        "total":        sale["total_amount"],

        # Payment
        "payment_method": sale["payment_method"],
        "amount_paid":    payment["amount_paid"]  if payment else sale["total_amount"],
        "change_given":   payment["change_given"] if payment else 0.0,
    }


def format_receipt_text(data: dict) -> str:
    """
    Convert a receipt dict into a formatted plain-text string
    ready for display or printing.
    """
    W   = RECEIPT_WIDTH
    cur = data["currency"]

    def centre(text: str) -> str:
        return text.center(W)

    def divider(char: str = "-") -> str:
        return char * W

    def money(amount: float) -> str:
        return f"{cur}{amount:.2f}"

    def line_lr(left: str, right: str) -> str:
        """Left-aligned label, right-aligned value on the same line."""
        space = W - len(left) - len(right)
        return left + " " * max(1, space) + right

    lines = []

    # ── Header ────────────────────────────────────────────────────────────
    lines += [
        divider("="),
        centre(data["store_name"]),
        centre(data["store_address"]),
        centre(data["store_phone"]),
        divider("="),
        "",
        centre("SALES RECEIPT"),
        "",
        line_lr("Date:",    data["date"]),
        line_lr("TXN ID:",  data["sale_id"]),
        line_lr("Cashier:", data["cashier"]),
    ]

    if data["customer_name"]:
        lines.append(line_lr("Customer:", data["customer_name"]))

    lines += ["", divider()]

    # ── Items ──────────────────────────────────────────────────────────────
    lines.append(
        f"{'Item':<22} {'Qty':>4} {'Price':>6} {'Total':>7}"
    )
    lines.append(divider())

    for item in data["items"]:
        # Truncate long names to keep columns aligned
        name = item["name"][:21]
        lines.append(
            f"{name:<22} {item['qty']:>4} "
            f"{cur}{item['unit_price']:>5.2f} "
            f"{cur}{item['line_total']:>6.2f}"
        )

    lines += ["", divider()]

    # ── Totals ─────────────────────────────────────────────────────────────
    lines.append(line_lr("Subtotal:", money(data["subtotal"])))

    if data["discount"] > 0:
        lines.append(line_lr("Discount:", f"-{money(data['discount'])}"))

    lines.append(line_lr("Tax (16%):", money(data["tax"])))
    lines.append(divider())

    total_label = "TOTAL:"
    total_value = money(data["total"])
    pad = W - len(total_label) - len(total_value)
    lines.append(total_label + " " * max(1, pad) + total_value)

    lines += ["", divider()]

    # ── Payment ────────────────────────────────────────────────────────────
    lines.append(line_lr("Payment:", data["payment_method"]))
    lines.append(line_lr("Amount Paid:", money(data["amount_paid"])))

    if data["change_given"] > 0:
        lines.append(line_lr("Change:", money(data["change_given"])))

    lines += ["", divider()]

    # ── Loyalty points ─────────────────────────────────────────────────────
    if data["customer_name"]:
        lines.append(line_lr("Points Earned:", str(data["points_earned"])))
        if data["customer_points"] is not None:
            new_balance = data["customer_points"]   # already updated in DB
            lines.append(line_lr("Points Balance:", str(new_balance)))
        lines.append(divider())

    # ── Footer ─────────────────────────────────────────────────────────────
    lines += [
        "",
        centre("Thank you for shopping with us!"),
        centre("Please come again."),
        "",
        divider("="),
    ]

    return "\n".join(lines)


def save_receipt_to_file(sale_id: str) -> tuple[bool, str]:
    """
    Generate and save the receipt as a .txt file in /receipts/.
    Returns (success, file_path_or_error_message).
    """
    data = generate_receipt(sale_id)
    if not data:
        return False, f"Sale '{sale_id}' not found."

    text     = format_receipt_text(data)
    filename = f"receipt_{sale_id}.txt"
    filepath = os.path.join(RECEIPTS_DIR, filename)

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(text)
        return True, filepath
    except OSError as e:
        return False, f"Could not save receipt: {e}"


def print_receipt(sale_id: str) -> tuple[bool, str]:
    """
    Save receipt to a temp file then send to the default system printer.
    Works on Windows (notepad /p), macOS (lpr), and Linux (lpr).
    Returns (success, message).
    """
    ok, result = save_receipt_to_file(sale_id)
    if not ok:
        return False, result

    filepath = result
    import platform
    system = platform.system()

    try:
        if system == "Windows":
            os.startfile(filepath, "print")
        elif system in ("Darwin", "Linux"):
            os.system(f'lpr "{filepath}"')
        else:
            return False, f"Printing not supported on {system}."
        return True, "Receipt sent to printer."
    except Exception as e:
        return False, f"Print failed: {e}"


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
    currency    = get_setting("currency_symbol") or "₵"
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
