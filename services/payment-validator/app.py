import json, uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone

def log(level, message, trace_id=""):
    print(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "level": level,
                       "service": "payment-validator", "trace_id": trace_id, "msg": message}),
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
        if self.path == "/health":
            self._respond(200, {"status": "ok", "service": "payment-validator"})
        else:
            self._respond(404, {"error": "not found"})

    def do_POST(self):
        tid = self.headers.get("X-Trace-ID", "")
        if self.path != "/validate":
            self._respond(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))
        except Exception:
            self._respond(400, {"error": "invalid JSON"})
            return

        token = data.get("token", "")
        amount = data.get("amount", 0)
        auth_code = "AUTH-" + uuid.uuid4().hex[:8].upper()
        log("info", f"Payment validated: token={token[:16]}... amount=${amount:.2f} auth={auth_code}", tid)
        self._respond(200, {"valid": True, "authorization_code": auth_code,
                            "amount": amount, "processor": "internal"})

    def log_message(self, fmt, *args):
        pass

if __name__ == "__main__":
    log("info", "Starting on port 8080")
    HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
