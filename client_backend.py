"""TCP client backend for the Network Resource Reservation System.

Protocol assumed for this starter implementation:
- One JSON request per TCP connection, terminated by a newline (\n).
- One JSON response from the server, also terminated by a newline.

Coordinate these details and the request fields with the TCP-server teammate
before integrating. No third-party packages are required.
"""

from __future__ import annotations

import json
import os
import socket
from typing import Any

# Configure these environment variables when running against the real server.
SERVER_HOST = os.getenv("NRRS_SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(os.getenv("NRRS_SERVER_PORT", "5000"))
SOCKET_TIMEOUT_SECONDS = float(os.getenv("NRRS_TIMEOUT_SECONDS", "5"))


def validate_reservation(
    source: str,
    destination: str,
    bandwidth_mbps: float,
    duration_seconds: int,
) -> str | None:
    """Return an error message if the request fields are invalid; else None."""
    if not isinstance(source, str) or not source.strip():
        return "Source host is required."
    if not isinstance(destination, str) or not destination.strip():
        return "Destination host is required."
    if source.strip() == destination.strip():
        return "Source and destination must be different hosts."

    # bool is a subclass of int in Python, so explicitly reject booleans.
    if isinstance(bandwidth_mbps, bool) or not isinstance(bandwidth_mbps, (int, float)):
        return "Bandwidth must be a number greater than zero."
    if bandwidth_mbps <= 0:
        return "Bandwidth must be greater than zero."

    if isinstance(duration_seconds, bool) or not isinstance(duration_seconds, int):
        return "Duration must be a whole number of seconds."
    if duration_seconds <= 0:
        return "Duration must be greater than zero."

    return None


def send_reservation_request(
    source: str,
    destination: str,
    bandwidth_mbps: float,
    duration_seconds: int,
    *,
    server_host: str = SERVER_HOST,
    server_port: int = SERVER_PORT,
    timeout: float = SOCKET_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Validate and send a reservation request to the TCP server.

    Returns a dictionary suitable for the UI to display. This function does not
    decide whether a reservation is allowed; the server/controller do that.
    """
    error = validate_reservation(source, destination, bandwidth_mbps, duration_seconds)
    if error:
        return {"status": "error", "message": error}

    request = {
        "type": "reserve_bandwidth",
        "source": source.strip(),
        "destination": destination.strip(),
        "bandwidth_mbps": bandwidth_mbps,
        "duration_seconds": duration_seconds,
    }

    try:
        payload = (json.dumps(request) + "\n").encode("utf-8")
        with socket.create_connection((server_host, server_port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(payload)

            # Read until newline. TCP is a byte stream; a single recv() is not
            # guaranteed to contain the entire response.
            response_bytes = bytearray()
            while b"\n" not in response_bytes:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response_bytes.extend(chunk)
                if len(response_bytes) > 1_000_000:
                    return {"status": "error", "message": "Server response was too large."}

        if not response_bytes:
            return {"status": "error", "message": "The server closed the connection without a response."}

        first_line = bytes(response_bytes).split(b"\n", 1)[0].decode("utf-8").strip()
        response = json.loads(first_line)
        if not isinstance(response, dict):
            return {"status": "error", "message": "Invalid response: expected a JSON object."}
        return response

    except (socket.timeout, TimeoutError):
        return {"status": "error", "message": "The server did not respond before the timeout."}
    except ConnectionRefusedError:
        return {"status": "error", "message": f"Connection refused by {server_host}:{server_port}. Is the server running?"}
    except (OSError, UnicodeDecodeError) as exc:
        return {"status": "error", "message": f"Network communication failed: {exc}"}
    except json.JSONDecodeError:
        return {"status": "error", "message": "The server returned invalid JSON."}


if __name__ == "__main__":
    # Simple terminal test. Replace h1/h2 and values as needed.
    result = send_reservation_request(
        source="h1",
        destination="h2",
        bandwidth_mbps=10,
        duration_seconds=60,
    )
    print(json.dumps(result, indent=2))
