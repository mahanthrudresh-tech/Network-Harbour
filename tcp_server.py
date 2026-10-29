
import socket
import json
import threading
import math
import urllib.request
import urllib.error

HOST = "0.0.0.0"
PORT = 5000

RYU_URL = "http://127.0.0.1:8080/reserve"


def validate_request(data):
    required = [
        "source",
        "destination",
        "bandwidth_mbps",
        "duration_seconds"
    ]

    if not isinstance(data, dict):
        return False, "Request must be a JSON object"

    for field in required:
        if field not in data:
            return False, f"Missing field: {field}"

    source = data["source"]
    destination = data["destination"]
    bandwidth = data["bandwidth_mbps"]
    duration = data["duration_seconds"]

    if not isinstance(source, str) or not source.strip():
        return False, "Invalid source"

    if not isinstance(destination, str) or not destination.strip():
        return False, "Invalid destination"

    if source.strip() == destination.strip():
        return False, "Source and destination must differ"

    if isinstance(bandwidth, bool) or not isinstance(bandwidth, (int, float)):
        return False, "Bandwidth must be numeric"

    if not math.isfinite(bandwidth) or not 0 < bandwidth <= 1000:
        return False, "Bandwidth must be between 0 and 1000 Mbps"

    if isinstance(duration, bool) or not isinstance(duration, int):
        return False, "Duration must be a whole number of seconds"

    if duration <= 0:
        return False, "Duration must be greater than zero"

    data["source"] = source.strip()
    data["destination"] = destination.strip()

    return True, "Valid request"


def contact_controller(data):
    payload = json.dumps(data).encode("utf-8")

    request = urllib.request.Request(
        RYU_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))

            if not isinstance(result, dict):
                return {
                    "status": "error",
                    "message": "Invalid controller response"
                }

            return result

    except urllib.error.HTTPError as error:
        return {
            "status": "error",
            "message": f"Controller HTTP error: {error.code}"
        }

    except (urllib.error.URLError, TimeoutError, OSError,
            json.JSONDecodeError):
        return {
            "status": "error",
            "message": "SDN controller unavailable"
        }


def handle_client(conn, address):
    print(f"Client connected: {address}")

    try:
        with conn:
            reader = conn.makefile("r", encoding="utf-8")

            for line in reader:
                if not line.strip():
                    continue

                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    result = {
                        "status": "rejected",
                        "message": "Invalid JSON"
                    }
                else:
                    valid, message = validate_request(data)

                    if not valid:
                        result = {
                            "status": "rejected",
                            "message": message
                        }
                    else:
                        print(f"Request received: {data}")
                        result = contact_controller(data)

                response = json.dumps(result) + "\n"
                conn.sendall(response.encode("utf-8"))

    except (ConnectionResetError, BrokenPipeError, OSError) as error:
        print(f"Connection error with {address}: {error}")

    finally:
        print(f"Client disconnected: {address}")


def start_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen()

        print(f"TCP server listening on {HOST}:{PORT}")

        try:
            while True:
                conn, address = server.accept()

                thread = threading.Thread(
                    target=handle_client,
                    args=(conn, address),
                    daemon=True
                )
                thread.start()

        except KeyboardInterrupt:
            print("\nTCP server stopped")


if __name__ == "__main__":
    start_server()
