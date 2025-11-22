import os
from datetime import date, datetime

import requests
from playwright.async_api import Page
from playwright_recaptcha import recaptchav2

from bolletta_sync.providers.base_provider import BaseProvider, Invoice


class Eni(BaseProvider):
    def __init__(self, google_credentials, page: Page):
        super().__init__(google_credentials, page, "eni")
        self.account_code = None

    async def _login_eni(self):
        await self.page.goto("https://eniplenitude.com/my-eni/")

        async with recaptchav2.AsyncSolver(self.page) as solver:
            await self.page.get_by_role("listitem", name="Accept proposed privacy").click()
            await self.page.get_by_role("textbox", name="email").fill(os.getenv("ENI_USERNAME"))
            await solver.solve_recaptcha(wait=True)
            await self.page.get_by_role("button", name="Prosegui", exact=True).click()

            await self.page.get_by_role("textbox", name="password").fill(os.getenv("ENI_PASSWORD"))
            await self.page.get_by_role("button", name="Accedi").click()
            await self.page.wait_for_timeout(1000)
            await solver.solve_recaptcha(wait=True)

        async with self.page.expect_navigation():
            await self.page.get_by_role("button", name="Accedi").click()

    async def get_invoices(self, start_date: date, end_date: date) -> list[Invoice]:
        invoices: list[Invoice] = []

        await self._login_eni()

        response = requests.get(
            "https://eniplenitude.com/serviceDAp/api/c360/init?logHash=wv5y2LVrjgcVRvW82WLEw3&channel=PORTAL",
            cookies=await self.get_cookies())
        response.raise_for_status()
        self.account_code = response.json()["codiceContoDefault"]
        client_code = response.json()["codiceCliente"]

        response = requests.get(
            f"https://eniplenitude.com/serviceDAp/c360/api/conti/{self.account_code}/bollette?logHash=8yVXbTfuaHIvAS5PvRHgnp&channel=PORTAL",
            cookies=await self.get_cookies()
        )
        response.raise_for_status()
        invoice_list = list(
            map(lambda i: Invoice(id=i["numeroBolletta"],
                                  doc_date=datetime.strptime(i["emissione"], "%d/%m/%Y"),
                                  due_date=datetime.strptime(i["scadenza"], "%d/%m/%Y"),
                                  amount=i["importo"],
                                  client_code=client_code),
                response.json()["bollette"]))
        invoice_list_filtered = list(
            filter(lambda invoice: start_date <= invoice.doc_date <= end_date, invoice_list))
        if invoice_list_filtered:
            invoices.extend(invoice_list_filtered)

        return invoices

    async def download_invoice(self, invoice: Invoice) -> bytes:
        response = requests.get(
            f"https://eniplenitude.com/serviceDAp/c360/api/conti/{self.account_code}/download-doc-pdf?numeroFattura={invoice.id}&logHash=0golQ74cfqlmjhg1O5pHyn&channel=PORTAL",
            cookies=await self.get_cookies()
        )

        if response.status_code != 200:
            raise Exception(f"Failed to download invoice PDF: {response.url} HTTP {response.status_code}")

        return response.content

    async def save_invoice(self, invoice: Invoice, invoice_pdf: bytes) -> bool:
        result = await super().save_invoice(invoice, invoice_pdf)
        return result

    async def set_expire_invoice(self, invoice: Invoice) -> bool:
        result = await super().set_expire_invoice(invoice)
        return result
