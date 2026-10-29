
import socket
import json

HOST = "127.0.0.1"
PORT = 5000


def handle_client(conn, addr):
    print(f"\n[CONNECTED] Client connected from {addr}")

    try:
        # Receive the request, which must end with a newline
        file = conn.makefile("r", encoding="utf-8")
        line = file.readline()

        if not line:
            print("[ERROR] Client sent an empty request")
            return

        # Convert JSON text into a Python dictionary
        request = json.loads(line)

        print("[REQUEST RECEIVED]")
        print(json.dumps(request, indent=4))

        # Extract request details
        source = request.get("source")
        destination = request.get("destination")
        bandwidth = request.get("bandwidth_mbps")
        duration = request.get("duration_seconds")

        # Validate the request
        if (
            not source
            or not destination
            or source == destination
            or not isinstance(bandwidth, (int, float))
            or isinstance(bandwidth, bool)
            or bandwidth <= 0
            or not isinstance(duration, (int, float))
            or isinstance(duration, bool)
            or duration <= 0
        ):
            response = {
                "status": "rejected",
                "message": "Invalid reservation parameters"
            }
        else:
            # This is a MOCK response, not a real bandwidth reservation
            response = {
                "status": "accepted",
                "message": (
                    f"Mock server received {bandwidth} Mbps "
                    f"from {source} to {destination} "
                    f"for {duration} seconds."
                )
            }

        # Send the response as newline-terminated JSON
        response_json = json.dumps(response) + "\n"
        conn.sendall(response_json.encode("utf-8"))

        print("[RESPONSE SENT]")
        print(json.dumps(response, indent=4))

    except json.JSONDecodeError:
        response = {
            "status": "error",
            "message": "Invalid JSON request"
        }
        try:
            conn.sendall((json.dumps(response) + "\n").encode("utf-8"))
        except OSError:
            pass

    except (ConnectionError, OSError) as error:
        print(f"[CONNECTION ERROR] {error}")

    finally:
        conn.close()
        print("[DISCONNECTED] Client connection closed")


def start_server():
    # Create a TCP socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # Bind the socket to the local IP and port
        server.bind((HOST, PORT))

        # Listen for incoming connections
        server.listen()

        print("=" * 45)
        print(" MOCK TCP SERVER STARTED")
        print(f" Listening on {HOST}:{PORT}")
        print(" Waiting for client requests...")
        print("=" * 45)

        try:
            while True:
                conn, addr = server.accept()
                handle_client(conn, addr)

        except KeyboardInterrupt:
            print("\n[SERVER STOPPED]")


if __name__ == "__main__":
    start_server()
