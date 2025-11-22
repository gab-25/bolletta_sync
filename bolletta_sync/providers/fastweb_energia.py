import os
from datetime import date

import requests
from playwright.sync_api import Playwright

from bolletta_sync.providers.base_provider import BaseProvider, Invoice


class FastwebEnergia(BaseProvider):
    def __init__(self, google_credentials, playwright: Playwright):
        super().__init__(google_credentials, playwright, "fastweb_energia")

    async def _login_fastweb_energia(self):
        self.page.goto("https://www.fastweb.it/myfastweb-energia/login/")

        self.page.locator("iframe[title=\"Cookie center\"]").content_frame.get_by_role("button",
                                                                                  name="Accetta tutti").click()

        self.page.get_by_placeholder("username").click()
        self.page.get_by_role("textbox", name="username").fill(os.getenv("FASTWEB_ENERGIA_USERNAME"))
        self.page.get_by_placeholder("password").click()
        self.page.get_by_role("textbox", name="password").fill(os.getenv("FASTWEB_ENERGIA_PASSWORD"))
        with self.page.expect_navigation():
            self.page.get_by_role("link", name="Accedi").click()

    async def get_invoices(self, start_date: date, end_date: date) -> list[Invoice]:
        invoices: list[Invoice] = []

        await self._login_fastweb_energia()

        payload = {"action": "loadInvoiceList"}
        response = requests.post(
            "https://www.fastweb.it/myfastweb-energia/services/invoices/",
            payload,
            cookies=self.get_cookies(),
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
        response = requests.get(
            f"https://www.fastweb.it/myfastweb-energia/bollette/download/{invoice.id}-{invoice.doc_date}.pdf",
            cookies=self.get_cookies(),
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
