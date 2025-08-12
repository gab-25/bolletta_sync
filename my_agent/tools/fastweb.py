import os
import requests
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
    response_body = dict(response.json())
    if response_body.get("errorCode") != 0:
        raise Exception("login failed")


def _check_profile(client_code: str):
    response = _session.get("https://fastweb.it/myfastweb/")
    if response.url.startswith(
        "https://fastweb.it/myfastweb/accesso/seleziona-codice-cliente/"
    ):
        response = _session.post(
            "https://fastweb.it/myfastweb/accesso/profile/", {"account": client_code}
        )
        if response.url != "https://fastweb.it/myfastweb/":
            raise Exception("invalid client code")


# @tool
def get_invoices_fastweb(client_code: str) -> list[dict]:
    """
    return a list of invoices from fastweb
    """
    if _session.cookies.get("PHPSESSID") is None:
        _login_fastweb()

    _check_profile(client_code)

    response = _session.get("https://fastweb.it/myfastweb/abbonamento/le-mie-fatture/")
    soup = BeautifulSoup(response.text, "html.parser")

    security_token = soup.find("input", {"name": "securityToken"}).get("value")
    payload = {"action": "loadInvoiceList", "securityToken": security_token}
    response = _session.post(
        "https://fastweb.it/myfastweb/abbonamento/le-mie-fatture/ajax/index.php",
        payload,
        params={"action": "loadInvoiceList"},
    )

    invoices = dict(response.json()).get("invoiceList", [])

    return invoices


@tool
def get_invoice_fastweb(client_code: str, invoice_id: str) -> dict:
    """
    return the invoices with the given id from fastweb
    """
    invoices = get_invoices_fastweb(client_code)

    try:
        invoice = list(filter(lambda inv: inv.get("id") == invoice_id, invoices))[0]
        return invoice
    except IndexError:
        raise Exception("invoice not found")


if __name__ == "__main__":
    print(get_invoices_fastweb("11477472"))
