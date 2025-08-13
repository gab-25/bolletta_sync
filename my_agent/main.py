import os
import json
from flask import Flask, request
from google.auth import jwt
from google.cloud import pubsub_v1


app = Flask(__name__)

service_account_info = json.load(open("service-account.json"))
audience = "https://pubsub.googleapis.com/google.pubsub.v1.Subscriber"
credentials = jwt.Credentials.from_service_account_info(
    service_account_info, audience=audience
)
publisher = pubsub_v1.PublisherClient(credentials=credentials)
topic_chat = publisher.topic_path(os.getenv("PROJECT_ID"), "my_agent_chat")


@app.route("/llm_execute", methods=["GET", "POST"])
def llm_request():
    from .agent import execute

    if request.method == "POST":
        input_str = dict(request.json).get("input")
        message = execute(input_str)
        publisher.publish(
            topic_chat,
            json.dumps({"input": input_str, "message": message}).encode("utf-8"),
        )
        return ""

    input_str = request.args.get("input")
    return execute(input_str)


if __name__ == "__main__":
    app.run(host="0.0.0.0")
