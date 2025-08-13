import os
from flask import Flask, request, jsonify
from .agent import execute

app = Flask(__name__)


def api_key_required(f):
    def wrapper(*args, **kwargs):
        api_key = request.headers.get("x-api-key")
        if not api_key or api_key != os.environ.get("API_KEY"):
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)

    return wrapper


@app.route("/invoke", methods=["POST"])
@api_key_required
def invoke():
    input_user = dict(request.json).get("message")
    if input_user is None:
        return "No message provided", 400

    output_agent = execute(input_user)
    return jsonify({"user": input_user, "agent": output_agent}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0")
