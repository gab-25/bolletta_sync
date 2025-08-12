from flask import Flask, request


app = Flask(__name__)


@app.route("/request", methods=["POST"])
def llm_request():
    from .agent import execute

    data = dict(request.json)
    response = execute(data.get("request"))
    return {"request": data.get("request"), "response": response}


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", load_dotenv=True)
