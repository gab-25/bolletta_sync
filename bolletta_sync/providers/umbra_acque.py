import logging
import os
from datetime import date, datetime

import requests
from playwright.sync_api import Playwright

from bolletta_sync.providers.base_provider import BaseProvider, Invoice

logger = logging.getLogger(__name__)


class UmbraAcque(BaseProvider):
    def __init__(self, google_credentials, playwright: Playwright):
        super().__init__(google_credentials, playwright, "umbra_acque")

    async def _login_umbra_acque(self):
        self.page.goto("https://self-service.umbraacque.com/umbraacque/login/")

        self.page.get_by_role("button", name="Accetta tutti i cookie").click()

        self.page.get_by_role("textbox", name="Indirizzo email").click()
        self.page.get_by_role("textbox", name="Indirizzo email").fill(os.getenv("UMBRA_ACQUE_USERNAME"))
        self.page.get_by_role("textbox", name="Password").click()
        self.page.get_by_role("textbox", name="Password").fill(os.getenv("UMBRA_ACQUE_PASSWORD"))

        with self.page.expect_navigation():
            self.page.get_by_role("button", name="ACCEDI").click()

    async def get_invoices(self, start_date: date, end_date: date) -> list[Invoice]:
        invoices: list[Invoice] = []

        await self._login_umbra_acque()

        response = requests.get("https://self-service.umbraacque.com/bin/acea-myacea/utenze/", params={
            "path": "/content/acea-myacea/umbraacque/selfcare/privato"}, cookies=self.get_cookies())
        response.raise_for_status()
        contract_pk = response.json().get("data")[0]["contractPk"]

        response = requests.get(
            "https://self-service.umbraacque.com/bin/acea-myacea/invoicesAndBalance/",
            params={
                "path": "/content/acea-myacea/umbraacque/selfcare/fatture/jcr:content/content-private-par/invoices_table",
                "contractPk": contract_pk
            },
            cookies=self.get_cookies()
        )
        response.raise_for_status()
        invoice_list = list(
            map(lambda i: Invoice(id=i["invoiceNumber"],
                                  doc_date=datetime.strptime(i["issueDate"], "%d/%m/%Y"),
                                  due_date=datetime.strptime(i["expiryDate"], "%d/%m/%Y"),
                                  amount=i["total"],
                                  client_code=i["contractId"]),
                response.json().get("body")["invoices"]))
        invoice_list_filtered = list(
            filter(lambda invoice: start_date <= invoice.doc_date <= end_date, invoice_list))
        if invoice_list_filtered:
            invoices.extend(invoice_list_filtered)

        return invoices

    async def download_invoice(self, invoice: Invoice) -> bytes:
        response = requests.get(
            "https://self-service.umbraacque.com/bin/acea-myacea/download/",
            params={
                "code": f"/download/invoice?contr={invoice.client_code}&code=42010AF32D161FE0A5B135871D859FC0&nbr={invoice.id}",
                "path": "/content/acea-myacea/umbraacque/selfcare/fatture/jcr:content/content-private-par/invoices_table"
            }, cookies=self.get_cookies())

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
