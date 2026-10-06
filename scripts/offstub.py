"""A stand-in for Open Food Facts in end-to-end tests (compose profile "e2e").

Serves every product JSON in /fixtures (one OFF API v3 response per file) at
/api/v3/product/<code>.json and as hits of /search. Standard library only.
"""

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PRODUCTS = {
    data["code"]: data
    for data in (json.loads(p.read_text()) for p in Path("/fixtures").glob("off_product_*.json"))
}
PRODUCT_PATH = re.compile(r"^/api/v3/product/(\d+)\.json$")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if match := PRODUCT_PATH.match(path):
            found = PRODUCTS.get(match.group(1))
            body = found or {"status": "failure", "result": {"id": "product_not_found"}}
            self._send(200 if found else 404, body)
        elif path == "/search":
            hits = [p["product"] | {"code": code} for code, p in PRODUCTS.items()]
            self._send(200, {"hits": hits})
        elif path == "/health":
            self._send(200, {"ok": True})
        else:
            self._send(404, {})

    def _send(self, status: int, body: object) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
