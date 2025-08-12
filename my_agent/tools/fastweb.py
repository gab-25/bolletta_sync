import requests
import os
from langchain.tools import tool
from bs4 import BeautifulSoup

_session = requests.Session()


def _login_fastweb():
    response = _session.get("https://fastweb.it/myfastweb/accesso/login/")
    soup = BeautifulSoup(response.text, "html.parser")

    security_token = soup.find("input", {"name": "securityToken"}).get("value")
    payload = {
        "securityToken": security_token,
        "request_id": "",
        "PersistentLogin": "",
        "OAM_REQ": "",
        "accountLinking": "",
        "redirect_uri": "",
        "state": "",
        "username": os.getenv("FASTWEB_USERNAME"),
        "password": os.getenv("FASTWEB_PASSWORD"),
        "g-recaptcha-response": "",
        "g-recaptcha-response-unified": "",
    }
    response = _session.post(
        "https://fastweb.it/myfastweb/accesso/login/ajax/",
        data=payload,
    )
    print(response.text)
    response_body = dict(response.json())
    if response_body.get("errorCode") != 0:
        raise Exception("login failed")


# @tool
def get_invoces_fastweb() -> list[str]:
    """
    return a list of invoces from fastweb
    """
    if _session.cookies.get("PHPSESSID") is None:
        _login_fastweb()

    response = _session.get("https://fastweb.it/myfastweb/abbonamento/le-mie-fatture/")
    soup = BeautifulSoup(response.text, "html.parser")

    invoces = []

    return invoces


@tool
def get_invoce_fastweb(id: str) -> str:
    """
    return the invoces with the given id from fastweb
    """
    _login_fastweb()
    invoce = ""

    return invoce


if __name__ == "__main__":
    print(get_invoces_fastweb())
