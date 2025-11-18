import os
from datetime import date

import requests
from bs4 import BeautifulSoup

from bolletta_sync.providers.base_provider import BaseProvider, Invoice


class Fastweb(BaseProvider):
    def __init__(self, google_credentials):
        super().__init__(google_credentials, "fastweb")
        if os.getenv("FASTWEB_CLIENT_CODE") is None:
            raise Exception("FASTWEB_CLIENT_CODE not set")
        self.client_codes = os.getenv("FASTWEB_CLIENT_CODE").split(",")
        self._session = requests.Session()

    def _login_fastweb(self):
        self._session.cookies.clear()
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

    def _select_profile(self, client_code: str):
        response = self._session.post(
            "https://fastweb.it/myfastweb/accesso/profile/", {"account": client_code}
        )
        if response.url != "https://fastweb.it/myfastweb/":
            raise Exception("invalid client code")

    def get_invoices(self, start_date: date, end_date: date) -> list[Invoice]:
        invoices: list[Invoice] = []

        for client_code in self.client_codes:
            self._login_fastweb()

            print(f"getting invoices for client {client_code}")
            self._select_profile(client_code)

            response = self._session.get("https://fastweb.it/myfastweb/abbonamento/le-mie-fatture/")
            soup = BeautifulSoup(response.text, "html.parser")

            security_token = soup.find("input", {"name": "securityToken"}).get("value")
            payload = {"action": "loadInvoiceList", "securityToken": security_token}
            response = self._session.post(
                "https://fastweb.it/myfastweb/abbonamento/le-mie-fatture/ajax/index.php",
                payload,
                params={"action": "loadInvoiceList"},
            )

            invoice_list = list(
                map(lambda i: Invoice(id=i["NumDoc"], doc_date=i["DocDateYMD"], due_date=i["DocExpireDateYMD"],
                                      amount=i["DocAmount"], client_code=client_code),
                    response.json().get("invoiceList", [])))
            invoice_list_filtered = list(
                filter(lambda invoice: start_date <= invoice.doc_date <= end_date, invoice_list))
            if invoice_list_filtered:
                invoices.extend(invoice_list_filtered)

        return invoices

    def download_invoice(self, invoice: Invoice) -> bytes:
        self._select_profile(invoice.client_code)
        response = self._session.get(
            f"https://fastweb.it/myfastweb/abbonamento/le-mie-fatture/conto-fastweb/Conto-FASTWEB-{invoice.id}-{invoice.doc_date.strftime('%Y%m%d')}.pdf",
        )

        if response.status_code != 200:
            raise Exception(f"Failed to download invoice PDF: {response.url} HTTP {response.status_code}")

        invoice_pdf = response.content

        return invoice_pdf

    def save_invoice(self, invoice: Invoice, invoice_pdf: bytes) -> bool:
        result = super().save_invoice(invoice, invoice_pdf)
        return result

    def set_expire_invoice(self, invoice: Invoice) -> bool:
        result = super().set_expire_invoice(invoice)
        return result
