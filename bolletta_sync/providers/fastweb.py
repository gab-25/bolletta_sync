import logging
import os

import requests
from bs4 import BeautifulSoup

from bolletta_sync.providers.base_provider import BaseProvider

logger = logging.getLogger(__name__)


class Fastweb(BaseProvider):
    _session = requests.Session()

    def __init__(self):
        if os.getenv("FASTWEB_CLIENT_CODE") is None:
            raise Exception("FASTWEB_CLIENT_CODE not set")
        self.client_codes = os.getenv("FASTWEB_CLIENT_CODE").split(",")

    def _login_fastweb(self):
        response = self._session.get("https://fastweb.it/myfastweb/accesso/login/")
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
        response = self._session.post(
            "https://fastweb.it/myfastweb/accesso/login/ajax/",
            data=payload,
        )
        response_body = dict(response.json())
        if response_body.get("errorCode") != 0:
            raise Exception("login failed")

    def _check_profile(self, client_code: str):
        response = self._session.get("https://fastweb.it/myfastweb/")
        if response.url.startswith(
                "https://fastweb.it/myfastweb/accesso/seleziona-codice-cliente/"
        ):
            response = self._session.post(
                "https://fastweb.it/myfastweb/accesso/profile/", {"account": client_code}
            )
            if response.url != "https://fastweb.it/myfastweb/":
                raise Exception("invalid client code")

    def get_invoices(self) -> dict:
        if self._session.cookies.get("PHPSESSID") is None:
            logger.info("logging in fastweb")
            self._login_fastweb()

        invoices = {}

        for client_code in self.client_codes:
            logger.info(f"getting invoices for client {client_code}")
            self._check_profile(client_code)

            response = self._session.get("https://fastweb.it/myfastweb/abbonamento/le-mie-fatture/")
            soup = BeautifulSoup(response.text, "html.parser")

            security_token = soup.find("input", {"name": "securityToken"}).get("value")
            payload = {"action": "loadInvoiceList", "securityToken": security_token}
            response = self._session.post(
                "https://fastweb.it/myfastweb/abbonamento/le-mie-fatture/ajax/index.php",
                payload,
                params={"action": "loadInvoiceList"},
            )

            invoice_list: list[dict] = response.json().get("invoiceList", [])
            logger.info(f"got {len(invoice_list)} invoices")
            invoices[client_code] = invoice_list

        return invoices
