
import socket
import json
import os
import threading

LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 5001

TCP_SERVER_HOST = os.getenv("TCP_SERVER_HOST", "127.0.0.1")
TCP_SERVER_PORT = 5002


def receive_json_line(sock):
    buffer = b""

    while b"\n" not in buffer:
        chunk = sock.recv(4096)

        if not chunk:
            if buffer:
                raise ConnectionError("Incomplete JSON message")
            raise ConnectionError("Connection closed")

        buffer += chunk

        if len(buffer) > 1_000_000:
            raise ValueError("Message too large")

    line, _, _ = buffer.partition(b"\n")
    return json.loads(line.decode("utf-8"))


def handle_client(client_socket, address):
    print(f"[CLIENT] Connected: {address}")

    try:
        with client_socket:
            request = receive_json_line(client_socket)
            print("[CLIENT] Request received:", request)

            message = json.dumps(request).encode("utf-8") + b"\n"

            with socket.create_connection(
                (TCP_SERVER_HOST, TCP_SERVER_PORT), timeout=10
            ) as server_socket:
                server_socket.settimeout(30)
                server_socket.sendall(message)

                response = receive_json_line(server_socket)

            print("[SERVER] Response received:", response)

            reply = json.dumps(response).encode("utf-8") + b"\n"
            client_socket.sendall(reply)

            print(f"[CLIENT] Response returned to {address}")

    except (OSError, ValueError, json.JSONDecodeError) as error:
        print("[ERROR]", error)

        try:
            error_response = {
                "status": "error",
                "message": str(error)
            }
            client_socket.sendall(
                json.dumps(error_response).encode("utf-8") + b"\n"
            )
        except OSError:
            pass


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((LISTEN_HOST, LISTEN_PORT))
        server.listen()

        print(f"Intermediate server listening on port {LISTEN_PORT}")
        print(f"Forwarding to {TCP_SERVER_HOST}:{TCP_SERVER_PORT}")

        while True:
            client_socket, address = server.accept()

            threading.Thread(
                target=handle_client,
                args=(client_socket, address),
                daemon=True
            ).start()


if __name__ == "__main__":
    main()
