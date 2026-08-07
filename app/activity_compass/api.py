from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .db import Database

API_SCHEMA_VERSION = 4


class ActivityApiHandler(BaseHTTPRequestHandler):
    db: Database

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(self, status: int, body: object) -> None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict:
        size = int(self.headers.get("Content-Length", "0"))
        if size > 1_000_000:
            raise ValueError("request too large")
        return json.loads(self.rfile.read(size) or b"{}")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._json(
                200,
                {
                    "status": "ok",
                    "service": "activity-compass",
                    "api_schema_version": API_SCHEMA_VERSION,
                },
            )
            return
        if parsed.path == "/v1/items":
            params = parse_qs(parsed.query)
            view = params.get("view", ["all"])[0]
            query = params.get("q", [""])[0]
            items = self.db.search_items(query) if query else self.db.list_items(view)
            self._json(200, {"items": items, "counts": self.db.counts()})
            return
        if parsed.path == "/v1/history":
            self._json(200, {"events": self.db.list_history()})
            return
        if parsed.path == "/v1/changes":
            self._json(200, {"token": self.db.change_token()})
            return
        self._json(404, {"error": "not_found"})

    def do_OPTIONS(self) -> None:
        self._json(204, {})

    def do_POST(self) -> None:
        try:
            body = self._body()
            if self.path == "/v1/sync":
                self._json(200, self.db.sync(body))
                return
            if self.path == "/v1/items":
                self._json(201, self.db.create_item(body))
                return
            if self.path == "/v1/export":
                destination = (
                    Path.home()
                    / "Documents"
                    / "Activity Compass Exports"
                    / f"activity-compass-{datetime.now():%Y-%m-%d-%H%M%S}.json"
                )
                exported = self.db.export_json(destination)
                self._json(200, {"path": str(exported)})
                return
            match = re.fullmatch(r"/v1/items/([^/]+)/status", self.path)
            if match:
                self._json(200, self.db.update_status(match.group(1), body["status"]))
                return
            match = re.fullmatch(r"/v1/items/([^/]+)/delete", self.path)
            if match:
                self._json(200, self.db.delete_item(match.group(1)))
                return
            match = re.fullmatch(r"/v1/items/([^/]+)", self.path)
            if match:
                self._json(200, self.db.update_item(match.group(1), body))
                return
            match = re.fullmatch(r"/v1/reviews/([^/]+)/(approve|reject)", self.path)
            if match:
                self._json(200, self.db.resolve_review(match.group(1), match.group(2) == "approve"))
                return
            self._json(404, {"error": "not_found"})
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:
            self._json(500, {"error": str(exc)})


def start_api(db: Database, port: int = 8765) -> tuple[ThreadingHTTPServer, threading.Thread]:
    handler = type("BoundActivityApiHandler", (ActivityApiHandler,), {"db": db})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="activity-api")
    thread.start()
    return server, thread
