import logging
import os
from datetime import date, datetime

import requests
from playwright.async_api import Page

from bolletta_sync.providers.base_provider import BaseProvider, Invoice

logger = logging.getLogger(__name__)


class UmbraAcque(BaseProvider):
    def __init__(self, google_credentials, page: Page):
        super().__init__(google_credentials, page, "umbra_acque")

    async def _login_umbra_acque(self):
        await self.page.goto("https://self-service.umbraacque.com/umbraacque/login/")

        await self.page.get_by_role("button", name="Accetta tutti i cookie").click()

        await self.page.get_by_role("textbox", name="Indirizzo email").click()
        await self.page.get_by_role("textbox", name="Indirizzo email").fill(os.getenv("UMBRA_ACQUE_USERNAME"))
        await self.page.get_by_role("textbox", name="Password").click()
        await self.page.get_by_role("textbox", name="Password").fill(os.getenv("UMBRA_ACQUE_PASSWORD"))

        async with self.page.expect_navigation():
            await self.page.get_by_role("button", name="ACCEDI").click()

    async def get_invoices(self, start_date: date, end_date: date) -> list[Invoice]:
        invoices: list[Invoice] = []

        await self._login_umbra_acque()

        response = requests.get("https://self-service.umbraacque.com/bin/acea-myacea/utenze/", params={
            "path": "/content/acea-myacea/umbraacque/selfcare/privato"}, cookies=await self.get_cookies())
        response.raise_for_status()
        contract_pk = response.json().get("data")[0]["contractPk"]

        response = requests.get(
            "https://self-service.umbraacque.com/bin/acea-myacea/invoicesAndBalance/",
            params={
                "path": "/content/acea-myacea/umbraacque/selfcare/fatture/jcr:content/content-private-par/invoices_table",
                "contractPk": contract_pk
            },
            cookies=await self.get_cookies()
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
            }, cookies=await self.get_cookies())

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
