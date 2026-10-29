"""Windows-friendly reservation controller for Network Harbour.

Run with: py sdn_controller_windows.py
It exposes the same POST /reserve API expected by tcp_server.py. This version
handles reservation decisions and expiry, but does not program OpenFlow switches.
"""
import json
import math
import os
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = os.getenv("NRRS_CONTROLLER_HOST", "127.0.0.1")
PORT = int(os.getenv("NRRS_CONTROLLER_PORT", "8080"))
MAX_TOTAL_BANDWIDTH_MBPS = float(os.getenv("NRRS_MAX_TOTAL_MBPS", "1000"))
MAX_REQUEST_BANDWIDTH_MBPS = float(os.getenv("NRRS_MAX_REQUEST_MBPS", "1000"))
MAX_DURATION_SECONDS = int(os.getenv("NRRS_MAX_DURATION_SECONDS", "86400"))
reservations = {}
lock = threading.RLock()


def remove_expired(now=None):
    now = now or time.time()
    expired = [rid for rid, item in reservations.items() if item["expires_at"] <= now]
    for rid in expired:
        del reservations[rid]


def reserve(data):
    if not isinstance(data, dict):
        return {"status": "rejected", "message": "Request must be a JSON object"}
    source, destination = data.get("source"), data.get("destination")
    bandwidth, duration = data.get("bandwidth_mbps"), data.get("duration_seconds")
    if not isinstance(source, str) or not source.strip():
        return {"status": "rejected", "message": "Invalid source"}
    if not isinstance(destination, str) or not destination.strip():
        return {"status": "rejected", "message": "Invalid destination"}
    source, destination = source.strip(), destination.strip()
    if source == destination:
        return {"status": "rejected", "message": "Source and destination must differ"}
    if isinstance(bandwidth, bool) or not isinstance(bandwidth, (int, float)):
        return {"status": "rejected", "message": "Bandwidth must be numeric"}
    if not math.isfinite(bandwidth) or not 0 < bandwidth <= MAX_REQUEST_BANDWIDTH_MBPS:
        return {"status": "rejected", "message": f"Bandwidth must be between 0 and {MAX_REQUEST_BANDWIDTH_MBPS:g} Mbps"}
    if isinstance(duration, bool) or not isinstance(duration, int) or duration <= 0:
        return {"status": "rejected", "message": "Duration must be a positive whole number of seconds"}
    if duration > MAX_DURATION_SECONDS:
        return {"status": "rejected", "message": f"Duration cannot exceed {MAX_DURATION_SECONDS} seconds"}

    now = time.time()
    with lock:
        remove_expired(now)
        used = sum(item["bandwidth_mbps"] for item in reservations.values())
        available = MAX_TOTAL_BANDWIDTH_MBPS - used
        if bandwidth > available:
            return {"status": "rejected", "message": f"Insufficient capacity: {available:.2f} Mbps available",
                    "available_bandwidth_mbps": round(max(0, available), 2)}
        rid = "RES_" + uuid.uuid4().hex[:8].upper()
        expires = now + duration
        reservations[rid] = {"reservation_id": rid, "source": source, "destination": destination,
                             "bandwidth_mbps": float(bandwidth), "duration_seconds": duration,
                             "created_at": now, "expires_at": expires}
        return {"status": "accepted", "message": f"Reservation {rid} approved for {bandwidth:g} Mbps",
                "reservation_id": rid, "source": source, "destination": destination,
                "bandwidth_mbps": float(bandwidth), "duration_seconds": duration,
                "expires_at": int(expires), "available_bandwidth_mbps": round(available - bandwidth, 2)}


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, data):
        payload = (json.dumps(data) + "\n").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        if self.path == "/reserve":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 1_000_000:
                    raise ValueError("Invalid request size")
                data = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
                self.send_json(400, {"status": "rejected", "message": "Invalid JSON request"})
                return
            self.send_json(200, reserve(data))
            return
        if self.path.startswith("/release/"):
            rid = self.path.removeprefix("/release/")
            with lock:
                item = reservations.pop(rid, None)
            if item is None:
                self.send_json(404, {"status": "rejected", "message": "Reservation not found or expired"})
            else:
                self.send_json(200, {"status": "released", "message": f"Reservation {rid} released"})
            return
        self.send_json(404, {"status": "error", "message": "Not found"})

    def do_GET(self):
        if self.path != "/reservations":
            self.send_json(404, {"status": "error", "message": "Not found"})
            return
        with lock:
            remove_expired()
            rows = []
            for item in reservations.values():
                row = dict(item)
                row["remaining_seconds"] = max(0, int(row["expires_at"] - time.time()))
                rows.append(row)
        used = sum(item["bandwidth_mbps"] for item in rows)
        self.send_json(200, {"status": "ok", "reservations": rows,
                             "allocated_bandwidth_mbps": round(used, 2),
                             "available_bandwidth_mbps": round(max(0, MAX_TOTAL_BANDWIDTH_MBPS - used), 2)})

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {self.address_string()} {fmt % args}")


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Network Harbour reservation controller listening on http://{HOST}:{PORT}")
    print("POST /reserve | GET /reservations | POST /release/<reservation_id>")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nController stopping")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
