
from flask import Flask, jsonify, render_template
from collections import deque
from threading import Lock
from datetime import datetime, timezone

app = Flask(__name__)

requests_history = deque(maxlen=200)
history_lock = Lock()


def record_request(request, response):
    item = {
        "request": request,
        "response": response,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    with history_lock:
        requests_history.appendleft(item)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/requests")
def get_requests():
    with history_lock:
        items = list(requests_history)

    return jsonify({
        "count": len(items),
        "requests": items
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
