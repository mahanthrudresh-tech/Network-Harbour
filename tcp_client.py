
import socket
import json
import os
import uuid

SERVER_HOST = os.getenv("INTERMEDIATE_HOST", "127.0.0.1")
SERVER_PORT = 5001


def send_request(request):
    message = json.dumps(request).encode("utf-8") + b"\n"

    with socket.create_connection(
        (SERVER_HOST, SERVER_PORT), timeout=10
    ) as sock:
        sock.settimeout(30)
        sock.sendall(message)

        buffer = b""

        while b"\n" not in buffer:
            chunk = sock.recv(4096)

            if not chunk:
                raise ConnectionError("Server disconnected before responding")

            buffer += chunk

            if len(buffer) > 1_000_000:
                raise ValueError("Response too large")

        line, _, _ = buffer.partition(b"\n")
        return json.loads(line.decode("utf-8"))


if __name__ == "__main__":
    request = {
        "request_id": str(uuid.uuid4()),
        "client_id": "CLIENT01",
        "source": {"host": "h1", "ip": "10.0.0.1"},
        "destination": {"host": "h2", "ip": "10.0.0.2"},
        "resource": {
            "bandwidth_mbps": 10,
            "duration_seconds": 60
        },
        "priority": 2
    }

    try:
        response = send_request(request)
        print("Response from TCP server:")
        print(json.dumps(response, indent=2))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print("Communication failed:", error)
