from flask import Flask, request, jsonify


app = Flask(__name__)


@app.route("/chat", methods=["GET"])
def chat():
    from .agent import execute

    input_user = request.args.get("input")
    output_agent = execute(input_user)
    return jsonify({"user": input_user, "agent": output_agent}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0")
