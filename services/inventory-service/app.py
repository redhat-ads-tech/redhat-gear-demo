import json, sys, uuid, urllib.request, urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone

PAYMENT_VALIDATOR_URL = "http://payment-validator.payment-services.svc:8080"

INVENTORY = {
    "fedora-hat": {"name": "Shadowman Fedora", "stock": 50, "price": 34.99},
    "classic-tee": {"name": "Red Hat Classic Tee", "stock": 100, "price": 29.99},
    "hoodie": {"name": "OpenShift Hoodie", "stock": 30, "price": 59.99},
    "enamel-pin": {"name": "Ansible Pin Set", "stock": 200, "price": 12.99},
    "sticker-pack": {"name": "Open Source Stickers", "stock": 150, "price": 8.99},
    "beanie": {"name": "RHEL Knit Beanie", "stock": 75, "price": 24.99},
}

def log(level, message, trace_id=""):
    print(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "level": level,
                       "service": "inventory-service", "trace_id": trace_id, "msg": message}),
          flush=True)

class Handler(BaseHTTPRequestHandler):
    def _respond(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Trace-ID")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def do_OPTIONS(self):
        self._respond(200, {})

    def do_GET(self):
        tid = self.headers.get("X-Trace-ID", "")
        if self.path == "/health":
            pv_status = "unknown"
            try:
                req = urllib.request.Request(f"{PAYMENT_VALIDATOR_URL}/health",
                                            headers={"X-Trace-ID": tid})
                resp = urllib.request.urlopen(req, timeout=3)
                pv_status = "ok"
            except Exception as e:
                pv_status = f"unreachable: {e}"
            self._respond(200, {"status": "ok", "service": "inventory-service",
                                "dependencies": {"payment-validator": pv_status}})
        elif self.path == "/catalog":
            self._respond(200, {"items": [
                {"id": k, **{f: v[f] for f in ("name", "price", "stock")}}
                for k, v in INVENTORY.items()
            ]})
        else:
            self._respond(404, {"error": "not found"})

    def do_POST(self):
        tid = self.headers.get("X-Trace-ID", "")
        if self.path != "/check":
            self._respond(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))
        except Exception:
            self._respond(400, {"error": "invalid JSON"})
            return

        items = data.get("items", [])
        log("info", f"Checking availability for {len(items)} items", tid)

        for item in items:
            inv = INVENTORY.get(item.get("id"))
            if not inv or inv["stock"] < item.get("quantity", 1):
                log("warn", f"Item {item.get('id')} out of stock", tid)
                self._respond(200, {"available": False, "reason": f"{item.get('id')} out of stock"})
                return

        total = sum(i.get("price", 0) * i.get("quantity", 1) for i in items)
        token = data.get("payment_token", "")
        log("info", f"Validating payment via payment-validator (total=${total:.2f})", tid)

        try:
            payload = json.dumps({"token": token, "amount": round(total, 2)}).encode()
            req = urllib.request.Request(f"{PAYMENT_VALIDATOR_URL}/validate",
                                        data=payload,
                                        headers={"Content-Type": "application/json",
                                                 "X-Trace-ID": tid})
            resp = urllib.request.urlopen(req, timeout=3)
            pv_result = json.loads(resp.read())
            log("info", f"Payment validated: {pv_result.get('authorization_code')}", tid)
        except urllib.error.URLError as e:
            log("error", f"Payment validation failed: connection to payment-validator timed out: {e}", tid)
            self._respond(500, {"error": "Payment validation failed",
                                "detail": f"Cannot reach payment-validator: {e}",
                                "failed_service": "payment-validator"})
            return
        except Exception as e:
            log("error", f"Payment validation failed: {e}", tid)
            self._respond(500, {"error": "Payment validation failed",
                                "detail": str(e), "failed_service": "payment-validator"})
            return

        self._respond(200, {"available": True, "reserved": True,
                            "payment_valid": True,
                            "authorization_code": pv_result.get("authorization_code")})

    def log_message(self, fmt, *args):
        pass

if __name__ == "__main__":
    log("info", "Starting on port 8080")
    HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
