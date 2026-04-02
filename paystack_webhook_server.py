"""
Minimal Paystack webhook receiver for local/dev use.

Usage:
  - Set PAYSTACK_SECRET_KEY and MOMO_PROVIDER_MODE=paystack
  - Run: python paystack_webhook_server.py
  - Expose with ngrok/cloudflared and paste URL in Paystack dashboard

Endpoint:
  POST /webhook/paystack
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.momo import handle_paystack_webhook
from modules.payments import log_payment_event


HOST = os.getenv("PAYSTACK_WEBHOOK_HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", os.getenv("PAYSTACK_WEBHOOK_PORT", "8081")))
PATH = os.getenv("PAYSTACK_WEBHOOK_PATH", "/webhook/paystack")
if not PATH.startswith("/"):
    PATH = "/" + PATH


class PaystackWebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != PATH:
            self._respond(404, {"ok": False, "message": "Not Found"})
            return

        content_len = int(self.headers.get("Content-Length", "0") or 0)
        raw_body = self.rfile.read(content_len)
        signature = self.headers.get("x-paystack-signature", "")

        event_name = "unknown"
        reference = ""
        try:
            payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
            event_name = payload.get("event", "unknown")
            data = payload.get("data") or {}
            reference = data.get("reference", "")
        except Exception:
            payload = {}

        ok, message = handle_paystack_webhook(raw_body, signature)

        # Store webhook event for audit/reconciliation (best-effort).
        try:
            log_payment_event(
                payment_ref=reference,
                source="paystack",
                event_type=event_name,
                event_status="processed" if ok else "ignored",
                payload_json=(raw_body.decode("utf-8", errors="ignore")[:5000]),
            )
        except Exception:
            pass

        self._respond(200 if ok else 400, {"ok": ok, "message": message})

    def do_GET(self):
        if self.path in ("/", ""):
            self._respond(
                200,
                {
                    "ok": True,
                    "service": "paystack-webhook",
                    "webhook_path": PATH,
                    "health": "/health",
                },
            )
            return
        if self.path == "/health":
            self._respond(
                200,
                {
                    "ok": True,
                    "service": "paystack-webhook",
                    "path": PATH,
                    "mode": os.getenv("MOMO_PROVIDER_MODE", "mock"),
                },
            )
            return
        self._respond(404, {"ok": False, "message": "Not Found"})

    def log_message(self, format, *args):
        # Keep output clean in POS terminals.
        return

    def _respond(self, code: int, body: dict):
        data = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def run_server():
    server = HTTPServer((HOST, PORT), PaystackWebhookHandler)
    print(f"Paystack webhook server listening on http://{HOST}:{PORT}{PATH}")
    print("Health check: /health")
    print("Root info endpoint: /")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run_server()
