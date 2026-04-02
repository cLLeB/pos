"""
Thermal Receipt Printer Module
================================
Two-layer architecture (as recommended):

  Layer 1 — Receipt Builder  (this module, top half)
    Pure-text, 48-column, fixed-width layout.
    ESC/POS command wrappers for bold, alignment, cut, etc.
    No hardware dependency — can be tested on any A4 printer or console.

  Layer 2 — Print Transport  (this module, bottom half)
    Sends ESC/POS byte stream directly to the default Windows printer
    using win32print (raw mode — bypasses the GDI driver).
    Falls back to os.startfile() if win32print is not installed.

Compatible printers (ESC/POS standard):
  Epson TM-T20 / TM-T88  (most common in Ghana)
  Star TSP100 / TSP650
  Any generic 58mm or 80mm thermal printer

Paper widths:
  58mm paper  → 32 chars per line  (set COLS = 32)
  80mm paper  → 48 chars per line  (set COLS = 48, default)

To adjust for your printer:
  1. Change COLS to match your paper width
  2. Run a test print and check alignment
  3. Enable/disable PAPER_CUT if your printer doesn't auto-cut

Install win32print (one-time setup):
  pip install pywin32
"""

import os
import sys
import platform
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Layout constants (adjust to match your thermal printer) ───────────────────
COLS       = 48    # characters per line (48 for 80mm paper, 32 for 58mm)
PAPER_CUT  = True  # send paper-cut command after receipt

# ── ESC/POS command bytes ─────────────────────────────────────────────────────
ESC = b"\x1b"
GS  = b"\x1d"

CMD_INIT         = ESC + b"\x40"           # initialize printer
CMD_ALIGN_LEFT   = ESC + b"\x61\x00"
CMD_ALIGN_CENTER = ESC + b"\x61\x01"
CMD_ALIGN_RIGHT  = ESC + b"\x61\x02"
CMD_BOLD_ON      = ESC + b"\x45\x01"
CMD_BOLD_OFF     = ESC + b"\x45\x00"
CMD_DOUBLE_HEIGHT_ON  = ESC + b"\x21\x10"
CMD_DOUBLE_HEIGHT_OFF = ESC + b"\x21\x00"
CMD_FULL_CUT     = GS  + b"\x56\x00"      # full paper cut
CMD_PARTIAL_CUT  = GS  + b"\x56\x01"      # partial cut (leaves small strip)
CMD_FEED_LINES   = lambda n: ESC + b"\x64" + bytes([n])  # feed N lines


# ── Layer 1: Receipt builder ──────────────────────────────────────────────────

def _centre(text: str, cols: int = COLS) -> str:
    return text.center(cols)


def _left_right(left: str, right: str, cols: int = COLS) -> str:
    """Left-aligned label, right-aligned value on one line."""
    gap = cols - len(left) - len(right)
    return left + " " * max(1, gap) + right


def _divider(char: str = "-", cols: int = COLS) -> str:
    return char * cols


def _wrap(text: str, cols: int = COLS) -> list[str]:
    """Word-wrap text to cols characters, returning a list of lines."""
    words = text.split()
    lines, current = [], ""
    for word in words:
        if len(current) + len(word) + (1 if current else 0) <= cols:
            current = (current + " " + word) if current else word
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def build_receipt_bytes(data: dict) -> bytes:
    """
    Build a complete ESC/POS byte stream for a sales receipt.

    `data` is the dict returned by modules.receipts.generate_receipt().
    """
    cur = data.get("currency", "₵")
    out = bytearray()

    def emit(b: bytes):
        out.extend(b)

    def text(s: str, encoding: str = "utf-8"):
        emit(s.encode(encoding, errors="replace"))

    def nl(n: int = 1):
        emit(b"\n" * n)

    # ── Initialize ────────────────────────────────────────────────────────
    emit(CMD_INIT)

    # ── Header ─────────────────────────────────────────────────────────────
    emit(CMD_ALIGN_CENTER)
    emit(CMD_DOUBLE_HEIGHT_ON)
    emit(CMD_BOLD_ON)
    text(_centre(data.get("store_name", "POS STORE"))); nl()
    emit(CMD_DOUBLE_HEIGHT_OFF)
    emit(CMD_BOLD_OFF)

    addr = data.get("store_address", "")
    phone_h = data.get("store_phone", "")
    if addr:
        text(_centre(addr)); nl()
    if phone_h:
        text(_centre(phone_h)); nl()

    nl()
    emit(CMD_BOLD_ON)
    text(_centre("SALES RECEIPT")); nl()
    emit(CMD_BOLD_OFF)
    text(_divider("=")); nl()

    # ── Sale info ──────────────────────────────────────────────────────────
    emit(CMD_ALIGN_LEFT)
    text(_left_right("Date:",    data.get("date", "")[:19])); nl()
    text(_left_right("TXN ID:",  data.get("sale_id", ""))); nl()
    text(_left_right("Cashier:", data.get("cashier", ""))); nl()

    customer_name = data.get("customer_name", "")
    if customer_name:
        text(_left_right("Customer:", customer_name)); nl()

    text(_divider()); nl()

    # ── Items ──────────────────────────────────────────────────────────────
    # Header row: Product name takes remaining cols after Qty, Price, Total
    qty_w   = 4
    price_w = 7
    total_w = 8
    name_w  = COLS - qty_w - price_w - total_w - 3

    hdr = (
        f"{'Item':<{name_w}} "
        f"{'Qty':>{qty_w}} "
        f"{'Price':>{price_w}} "
        f"{'Total':>{total_w}}"
    )
    emit(CMD_BOLD_ON)
    text(hdr); nl()
    emit(CMD_BOLD_OFF)
    text(_divider()); nl()

    for item in data.get("items", []):
        name_str = item["name"]
        price_str = f"{cur}{item['unit_price']:.2f}"
        total_str = f"{cur}{item['line_total']:.2f}"

        # First line: name (truncated if needed) + qty + price + total
        name_trunc = name_str[:name_w]
        row = (
            f"{name_trunc:<{name_w}} "
            f"{item['qty']:>{qty_w}} "
            f"{price_str:>{price_w}} "
            f"{total_str:>{total_w}}"
        )
        text(row); nl()

        # If name is longer than name_w, print continuation lines
        if len(name_str) > name_w:
            for extra_line in _wrap(name_str[name_w:], name_w):
                text(f"  {extra_line}"); nl()

    text(_divider()); nl()

    # ── Totals ─────────────────────────────────────────────────────────────
    text(_left_right("Subtotal:", f"{cur}{data['subtotal']:.2f}")); nl()

    if data.get("discount", 0) > 0:
        text(_left_right("Discount:", f"-{cur}{data['discount']:.2f}")); nl()

    tax_rate_pct = round(data.get("tax", 0) / data["subtotal"] * 100) if data.get("subtotal") else 0
    text(_left_right(f"Tax ({tax_rate_pct}%):", f"{cur}{data['tax']:.2f}")); nl()
    text(_divider()); nl()

    emit(CMD_BOLD_ON)
    emit(CMD_DOUBLE_HEIGHT_ON)
    total_label = "TOTAL:"
    total_value = f"{cur}{data['total']:.2f}"
    gap = COLS - len(total_label) - len(total_value)
    text(total_label + " " * max(1, gap) + total_value); nl()
    emit(CMD_DOUBLE_HEIGHT_OFF)
    emit(CMD_BOLD_OFF)

    text(_divider()); nl()

    # ── Payment ────────────────────────────────────────────────────────────
    text(_left_right("Payment:",    data.get("payment_method", ""))); nl()
    text(_left_right("Paid:",       f"{cur}{data.get('amount_paid', 0):.2f}")); nl()

    change = data.get("change_given", 0)
    if change > 0:
        emit(CMD_BOLD_ON)
        text(_left_right("Change:", f"{cur}{change:.2f}")); nl()
        emit(CMD_BOLD_OFF)

    text(_divider()); nl()

    # ── Loyalty points ─────────────────────────────────────────────────────
    if customer_name:
        pts_earned  = data.get("points_earned", 0)
        pts_balance = data.get("customer_points", 0)
        if pts_earned:
            text(_left_right("Points Earned:", str(pts_earned))); nl()
        if pts_balance is not None:
            text(_left_right("Points Balance:", str(pts_balance))); nl()
        text(_divider()); nl()

    # ── Footer ─────────────────────────────────────────────────────────────
    nl()
    emit(CMD_ALIGN_CENTER)
    text(_centre("Thank you for shopping with us!")); nl()
    text(_centre("Please come again.")); nl()
    nl()
    emit(CMD_ALIGN_LEFT)

    # Feed & cut
    emit(CMD_FEED_LINES(4))
    if PAPER_CUT:
        emit(CMD_PARTIAL_CUT)

    return bytes(out)


def build_return_receipt_bytes(ret: dict, store_name: str,
                                store_phone: str, currency: str) -> bytes:
    """Build an ESC/POS return/refund receipt."""
    out = bytearray()

    def emit(b: bytes): out.extend(b)
    def text(s: str):   emit(s.encode("utf-8", errors="replace"))
    def nl(n: int = 1): emit(b"\n" * n)

    emit(CMD_INIT)
    emit(CMD_ALIGN_CENTER)
    emit(CMD_BOLD_ON)
    emit(CMD_DOUBLE_HEIGHT_ON)
    text(_centre(store_name)); nl()
    emit(CMD_DOUBLE_HEIGHT_OFF)
    emit(CMD_BOLD_OFF)
    if store_phone:
        text(_centre(store_phone)); nl()

    text(_divider("=")); nl()
    emit(CMD_BOLD_ON)
    text(_centre("RETURN / REFUND RECEIPT")); nl()
    emit(CMD_BOLD_OFF)
    text(_divider("=")); nl()

    emit(CMD_ALIGN_LEFT)
    text(f"Return ID  : {ret['return_id']}"); nl()
    text(f"Sale Ref   : {ret['sale_id']}"); nl()
    text(f"Date       : {ret['date']}"); nl()
    text(f"Cashier    : {ret['cashier_name']}"); nl()

    for line in _wrap(f"Reason: {ret['reason']}", COLS):
        text(line); nl()

    text(_divider()); nl()

    name_w  = COLS - 4 - 7 - 8 - 3
    emit(CMD_BOLD_ON)
    text(f"{'ITEM':<{name_w}} {'QTY':>4} {'PRICE':>7} {'TOTAL':>8}"); nl()
    emit(CMD_BOLD_OFF)
    text(_divider()); nl()

    for item in ret.get("items", []):
        total = item["quantity"] * item["price"]
        name  = item["product_name"][:name_w]
        text(
            f"{name:<{name_w}} "
            f"{item['quantity']:>4} "
            f"{currency}{item['price']:>6.2f} "
            f"{currency}{total:>7.2f}"
        ); nl()
        if not item.get("restocked"):
            text("  (not restocked - write-off)"); nl()

    text(_divider()); nl()
    emit(CMD_BOLD_ON)
    text(_left_right("TOTAL REFUND:", f"{currency}{ret['total_refund']:.2f}")); nl()
    emit(CMD_BOLD_OFF)
    text(_divider("=")); nl()
    emit(CMD_ALIGN_CENTER)
    text(_centre("Thank you.")); nl()

    emit(CMD_FEED_LINES(4))
    if PAPER_CUT:
        emit(CMD_PARTIAL_CUT)

    return bytes(out)


# ── Layer 2: Print transport ──────────────────────────────────────────────────

def send_to_thermal_printer(raw_bytes: bytes) -> tuple[bool, str]:
    """
    Send raw ESC/POS bytes directly to the default Windows printer.
    Uses win32print in RAW mode — bypasses Windows GDI rendering.

    If win32print is not available, falls back to saving a .txt file
    and opening it with the default print handler (os.startfile).
    """
    if platform.system() != "Windows":
        return _fallback_print(raw_bytes)

    try:
        import win32print  # type: ignore  (pip install pywin32)
        printer_name = win32print.GetDefaultPrinter()
        handle = win32print.OpenPrinter(printer_name)
        try:
            win32print.StartDocPrinter(handle, 1, ("POS Receipt", None, "RAW"))
            win32print.StartPagePrinter(handle)
            win32print.WritePrinter(handle, raw_bytes)
            win32print.EndPagePrinter(handle)
            win32print.EndDocPrinter(handle)
        finally:
            win32print.ClosePrinter(handle)
        return True, f"Printed to: {printer_name}"

    except ImportError:
        return _fallback_print(raw_bytes)
    except Exception as e:
        return False, f"Printer error: {e}"


def _fallback_print(raw_bytes: bytes) -> tuple[bool, str]:
    """
    Fallback: strip ESC/POS commands and send as a plain-text file
    to the OS default printer via os.startfile('print').
    """
    try:
        # Strip ESC/POS bytes — keep only printable ASCII + newlines
        text_only = bytearray()
        i = 0
        while i < len(raw_bytes):
            b = raw_bytes[i]
            if b == 0x1b or b == 0x1d:      # ESC or GS — skip command + args
                i += 3                        # most commands are 3 bytes total
                continue
            if b >= 0x20 or b in (0x0a, 0x0d):
                text_only.append(b)
            i += 1

        tmp = tempfile.NamedTemporaryFile(
            suffix=".txt", delete=False, mode="wb"
        )
        tmp.write(text_only)
        tmp.close()

        if platform.system() == "Windows":
            os.startfile(tmp.name, "print")
        else:
            os.system(f'lpr "{tmp.name}"')

        return True, "Sent to default printer (text mode)."
    except Exception as e:
        return False, f"Fallback print failed: {e}"


# ── Convenience wrappers used by receipt_window.py ───────────────────────────

def print_sale_receipt(data: dict) -> tuple[bool, str]:
    """Build ESC/POS bytes for a sale receipt and send to printer."""
    raw = build_receipt_bytes(data)
    return send_to_thermal_printer(raw)


def print_return_receipt(ret: dict, store_name: str,
                          store_phone: str, currency: str) -> tuple[bool, str]:
    """Build ESC/POS bytes for a return receipt and send to printer."""
    raw = build_return_receipt_bytes(ret, store_name, store_phone, currency)
    return send_to_thermal_printer(raw)
