import logging
import os
from datetime import date

import requests
from bs4 import BeautifulSoup

from bolletta_sync.providers.base_provider import BaseProvider, Invoice

logger = logging.getLogger(__name__)


class FastwebEnergia(BaseProvider):
    def __init__(self, google_credentials):
        super().__init__(google_credentials, logger, "fastweb_energia")
        self._session = requests.Session()

    async def _login_fastweb_energia(self):
        self._session.cookies.clear()
        response = self._session.get("https://www.fastweb.it/myfastweb-energia/login/")
        soup = BeautifulSoup(response.text, "html.parser")

        security_token = soup.find("input", {"name": "securityToken"}).get("value")
        payload = {
            "securityToken": security_token,
            "DirectLink": "/myfastweb-energia/",
            "username": os.getenv("FASTWEB_ENERGIA_USERNAME"),
            "password": os.getenv("FASTWEB_ENERGIA_PASSWORD"),
            "g-recaptcha-response": "",
            "g-recaptcha-response-unified": "",
        }
        response = self._session.post(
            "https://www.fastweb.it/myfastweb-energia/login/ajax/",
            data=payload,
        )
        response_body = dict(response.json())
        if response_body.get("errorCode") != 0:
            raise Exception("login failed")

    async def get_invoices(self, start_date: date, end_date: date) -> list[Invoice]:
        invoices: list[Invoice] = []

        await self._login_fastweb_energia()

        payload = {"action": "loadInvoiceList"}
        response = self._session.post(
            "https://www.fastweb.it/myfastweb-energia/services/invoices/",
            payload
        )

        invoice_list = list(
            map(lambda i: Invoice(id=i["NumDoc"], doc_date=i["DocDateYMD"], due_date=i["DocExpireDateYMD"],
                                  amount=i["DocAmount"], client_code=os.getenv("FASTWEB_ENERGIA_USERNAME")),
                response.json().get("invoiceList", [])))
        invoice_list_filtered = list(
            filter(lambda invoice: start_date <= invoice.doc_date <= end_date, invoice_list))
        if invoice_list_filtered:
            invoices.extend(invoice_list_filtered)

        return invoices

    async def download_invoice(self, invoice: Invoice) -> bytes:
        response = self._session.get(
            f"https://www.fastweb.it/myfastweb-energia/bollette/download/{invoice.id}-{invoice.doc_date}.pdf"
        )

        if response.status_code != 200:
            raise Exception(f"Failed to download invoice PDF: {response.url} HTTP {response.status_code}")

        invoice_pdf = response.content

        return invoice_pdf

    async def save_invoice(self, invoice: Invoice, invoice_pdf: bytes) -> bool:
        result = await super().save_invoice(invoice, invoice_pdf)
        return result

    async def set_expire_invoice(self, invoice: Invoice) -> bool:
        result = await super().set_expire_invoice(invoice)
        return result
