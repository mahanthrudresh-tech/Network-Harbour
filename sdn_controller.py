"""Ryu REST app for the Network Resource Reservation System.

Run: ryu-manager sdn_controller.py
The TCP server calls POST /reserve using the project's JSON request fields.
"""
import json
import math
import os
import threading
import time
import uuid

from ryu.app.wsgi import ControllerBase, WSGIApplication, Response, route
from ryu.base import app_manager
from ryu.lib import hub

APP_NAME = "nrrs_sdn_controller"
MAX_TOTAL_BANDWIDTH_MBPS = float(os.getenv("NRRS_MAX_TOTAL_MBPS", "1000"))
MAX_BANDWIDTH_PER_REQUEST_MBPS = float(os.getenv("NRRS_MAX_REQUEST_MBPS", "1000"))
MAX_DURATION_SECONDS = int(os.getenv("NRRS_MAX_DURATION_SECONDS", "86400"))


class ReservationController(app_manager.RyuApp):
    """Admission control and in-memory reservation/expiry management."""
    _CONTEXTS = {"wsgi": WSGIApplication}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        kwargs["wsgi"].register(ReservationRestController, {APP_NAME: self})
        self.reservations = {}
        self.lock = threading.RLock()
        self.expiry_worker = hub.spawn(self._expiry_loop)
        self.logger.info("NRRS controller ready; capacity %.2f Mbps", MAX_TOTAL_BANDWIDTH_MBPS)

    def reserve(self, data):
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
        if not math.isfinite(bandwidth) or not 0 < bandwidth <= MAX_BANDWIDTH_PER_REQUEST_MBPS:
            return {"status": "rejected", "message": f"Bandwidth must be between 0 and {MAX_BANDWIDTH_PER_REQUEST_MBPS:g} Mbps"}
        if isinstance(duration, bool) or not isinstance(duration, int) or duration <= 0:
            return {"status": "rejected", "message": "Duration must be a positive whole number of seconds"}
        if duration > MAX_DURATION_SECONDS:
            return {"status": "rejected", "message": f"Duration cannot exceed {MAX_DURATION_SECONDS} seconds"}

        now = time.time()
        with self.lock:
            self._remove_expired(now)
            allocated = sum(item["bandwidth_mbps"] for item in self.reservations.values())
            available = MAX_TOTAL_BANDWIDTH_MBPS - allocated
            if bandwidth > available:
                return {"status": "rejected", "message": f"Insufficient capacity: {available:.2f} Mbps available", "available_bandwidth_mbps": round(max(0, available), 2)}
            rid = "RES_" + uuid.uuid4().hex[:8].upper()
            expires = now + duration
            self.reservations[rid] = {
                "reservation_id": rid, "source": source, "destination": destination,
                "bandwidth_mbps": float(bandwidth), "duration_seconds": duration,
                "created_at": now, "expires_at": expires,
            }
            self.logger.info("Accepted %s: %s -> %s, %s Mbps for %s seconds", rid, source, destination, bandwidth, duration)
            return {"status": "accepted", "message": f"Reservation {rid} approved for {bandwidth:g} Mbps",
                    "reservation_id": rid, "source": source, "destination": destination,
                    "bandwidth_mbps": float(bandwidth), "duration_seconds": duration,
                    "expires_at": int(expires), "available_bandwidth_mbps": round(available - bandwidth, 2)}

    def release(self, rid):
        with self.lock:
            item = self.reservations.pop(rid, None)
            if item is None:
                return {"status": "rejected", "message": "Reservation not found or already expired"}
            return {"status": "released", "message": f"Reservation {rid} released"}

    def list_reservations(self):
        now = time.time()
        with self.lock:
            self._remove_expired(now)
            rows = []
            for item in self.reservations.values():
                row = dict(item)
                row["remaining_seconds"] = max(0, int(row["expires_at"] - now))
                rows.append(row)
            return rows

    def _remove_expired(self, now):
        for rid in [key for key, item in self.reservations.items() if item["expires_at"] <= now]:
            del self.reservations[rid]
            self.logger.info("Reservation %s expired", rid)

    def _expiry_loop(self):
        while True:
            hub.sleep(1)
            with self.lock:
                self._remove_expired(time.time())


class ReservationRestController(ControllerBase):
    """REST endpoints consumed by tcp_server.py."""
    def __init__(self, req, link, data, **config):
        super().__init__(req, link, data, **config)
        self.controller = data[APP_NAME]

    @staticmethod
    def _response(value, status=200):
        return Response(status=status, content_type="application/json", body=json.dumps(value) + "\n")

    @route("nrrs_reserve", "/reserve", methods=["POST"])
    def reserve(self, req, **kwargs):
        try:
            data = json.loads(req.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._response({"status": "rejected", "message": "Invalid JSON request"}, 400)
        return self._response(self.controller.reserve(data))

    @route("nrrs_release", "/release/{reservation_id}", methods=["POST"])
    def release(self, req, **kwargs):
        return self._response(self.controller.release(kwargs["reservation_id"]))

    @route("nrrs_reservations", "/reservations", methods=["GET"])
    def reservations(self, req, **kwargs):
        rows = self.controller.list_reservations()
        used = sum(item["bandwidth_mbps"] for item in rows)
        return self._response({"status": "ok", "reservations": rows,
                               "allocated_bandwidth_mbps": round(used, 2),
                               "available_bandwidth_mbps": round(max(0, MAX_TOTAL_BANDWIDTH_MBPS - used), 2)})
