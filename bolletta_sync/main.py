import os
from flask import Flask, request, jsonify

app = Flask(__name__)


def api_key_required(f):
    def wrapper(*args, **kwargs):
        api_key = request.headers.get("x-api-key")
        if not api_key or api_key != os.environ.get("API_KEY"):
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)

    return wrapper


@app.route("/sync", methods=["GET"])
@api_key_required
def sync():
    pass


if __name__ == "__main__":
    app.run(host="0.0.0.0")
