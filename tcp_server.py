
import socket
import json
import threading

HOST = "0.0.0.0"
PORT = 5002


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
    print(f"[CONNECTED] {address}")

    try:
        with client_socket:
            request = receive_json_line(client_socket)
            print("[REQUEST]", json.dumps(request, indent=2))

            response = {
                "request_id": request.get("request_id"),
                "status": "received",
                "message": "TCP server received the request successfully"
            }

            client_socket.sendall(
                json.dumps(response).encode("utf-8") + b"\n"
            )

            print("[RESPONSE]", response)

    except (OSError, ValueError, json.JSONDecodeError) as error:
        print("[ERROR]", error)


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen()

        print(f"TCP server listening on {HOST}:{PORT}")

        while True:
            client_socket, address = server.accept()

            threading.Thread(
                target=handle_client,
                args=(client_socket, address),
                daemon=True
            ).start()


if __name__ == "__main__":
    main()
