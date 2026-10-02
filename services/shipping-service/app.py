import json, random, string
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone

def log(level, message, trace_id=""):
    print(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "level": level,
                       "service": "shipping-service", "trace_id": trace_id, "msg": message}),
          flush=True)

def ups_tracking():
    alpha = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    digits = "".join(random.choices(string.digits, k=10))
    return f"1Z{alpha}{digits}"

SERVICE_LEVELS = [
    {"service_level": "UPS Ground", "estimated_delivery": "3-5 business days", "cost": 8.99},
    {"service_level": "UPS 3 Day Select", "estimated_delivery": "3 business days", "cost": 14.99},
    {"service_level": "UPS 2nd Day Air", "estimated_delivery": "2 business days", "cost": 22.99},
]

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
        if self.path == "/health":
            self._respond(200, {"status": "ok", "service": "shipping-service", "carrier": "UPS"})
        else:
            self._respond(404, {"error": "not found"})

    def do_POST(self):
        tid = self.headers.get("X-Trace-ID", "")
        if self.path != "/ship":
            self._respond(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))
        except Exception:
            self._respond(400, {"error": "invalid JSON"})
            return

        name = data.get("name", "Customer")
        tracking = ups_tracking()
        level = random.choice(SERVICE_LEVELS)
        log("info", f"Shipment created for {name}: {tracking} via {level['service_level']}", tid)
        self._respond(200, {
            "carrier": "UPS",
            "tracking_number": tracking,
            "estimated_delivery": level["estimated_delivery"],
            "service_level": level["service_level"],
            "shipping_cost": level["cost"],
            "label_url": f"https://www.ups.com/track?tracknum={tracking}",
        })

    def log_message(self, fmt, *args):
        pass

if __name__ == "__main__":
    log("info", "Starting on port 8080")
    HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
