import json, sys, uuid, urllib.request, urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone

def log(level, message, trace_id=""):
    print(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "level": level,
                       "service": "order-service", "trace_id": trace_id, "msg": message}),
          flush=True)

def call_service(url, data=None, trace_id="", timeout=5):
    headers = {"Content-Type": "application/json", "X-Trace-ID": trace_id}
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers,
                                method="POST" if data else "GET")
    resp = urllib.request.urlopen(req, timeout=timeout)
    return json.loads(resp.read())

def check_dep(url, trace_id):
    try:
        call_service(url, trace_id=trace_id, timeout=2)
        return "ok"
    except Exception as e:
        return str(e)

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
        tid = self.headers.get("X-Trace-ID", str(uuid.uuid4()))
        if self.path == "/health":
            deps = {
                "inventory-service": check_dep("http://inventory-service:8080/health", tid),
                "shipping-service": check_dep("http://shipping-service:8080/health", tid),
            }
            self._respond(200, {"status": "ok", "service": "order-service", "dependencies": deps})
        else:
            self._respond(404, {"error": "not found"})

    def do_POST(self):
        tid = self.headers.get("X-Trace-ID", str(uuid.uuid4()))
        if self.path != "/orders":
            self._respond(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            order = json.loads(self.rfile.read(length))
        except Exception:
            self._respond(400, {"error": "invalid JSON"})
            return

        log("info", f"New order received: {len(order.get('items', []))} items", tid)

        items = [{"id": i.get("productId", i.get("id")),
                  "name": i.get("name"), "quantity": i.get("quantity", 1),
                  "price": i.get("unitPrice", i.get("price", 0))} for i in order.get("items", [])]

        try:
            log("info", "Calling inventory-service /check", tid)
            inv = call_service("http://inventory-service:8080/check",
                               {"items": items,
                                "payment_token": "tok_" + uuid.uuid4().hex[:12]}, tid)
            log("info", f"Inventory response: {json.dumps(inv)}", tid)
            if not inv.get("available", True):
                self._respond(400, {"error": "Items unavailable",
                                    "detail": inv.get("reason", "out of stock")})
                return
        except Exception as e:
            log("error", f"Inventory check failed: {e}", tid)
            self._respond(502, {"error": "Inventory check failed",
                                "detail": str(e), "failed_service": "inventory-service"})
            return

        try:
            log("info", "Calling shipping-service /ship", tid)
            ship = call_service("http://shipping-service:8080/ship",
                                order.get("shipping", {}), tid)
            log("info", f"Shipping response: {json.dumps(ship)}", tid)
        except Exception as e:
            log("error", f"Shipping request failed: {e}", tid)
            self._respond(502, {"error": "Shipping request failed",
                                "detail": str(e), "failed_service": "shipping-service"})
            return

        total = sum(i.get("price", 0) * i.get("quantity", 1) for i in order.get("items", []))
        confirmation = {
            "order_id": "ORD-" + uuid.uuid4().hex[:8].upper(),
            "status": "confirmed",
            "items": order.get("items", []),
            "total": round(total, 2),
            "shipping": ship,
        }
        log("info", f"Order confirmed: {confirmation['order_id']}", tid)
        self._respond(200, confirmation)

    def log_message(self, fmt, *args):
        pass

if __name__ == "__main__":
    log("info", "Starting on port 8080")
    HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
