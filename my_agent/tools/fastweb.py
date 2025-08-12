import requests
import os
from langchain.tools import tool
from bs4 import BeautifulSoup

_session = requests.Session()
_security_token = None


def _login_fastweb():
    global _session, _security_token

    response = _session.get("https://fastweb.it/myfastweb/accesso/login/")
    soap = BeautifulSoup(response.text)

    _security_token = soap.find("input", {"name": "securityToken"}).get("value")
    payload = {
        "securityToken": _security_token,
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
    response_body = dict(response.json())
    if response_body.get("errorCode") != 0:
        raise Exception("login failed")


# @tool
def get_invoces_fastweb() -> list[str]:
    """
    return a list of invoces from fastweb
    """
    global _session, _security_token
    if _session.cookies.get("PHPSESSID") is None:
        _login_fastweb()

    payload = {"action": "loadInvoiceList", "securityToken": _security_token}
    response = _session.post(
        "https://fastweb.it/myfastweb/abbonamento/le-mie-fatture/ajax/index.php",
        params={"action": "loadInvoiceList"},
    )
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
