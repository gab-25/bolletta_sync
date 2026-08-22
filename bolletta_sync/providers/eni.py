import os
from datetime import date, datetime

import requests
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from bolletta_sync.captcha import apply_recaptcha_token, solve_recaptcha_v2
from bolletta_sync.providers.base_provider import BaseProvider, Invoice

# The page keeps loading trackers well past the point where the login form is usable, so the
# "load" event is unreliable and the default 30s timeout is too tight for it.
NAVIGATION_TIMEOUT = 60_000


class Eni(BaseProvider):
    def __init__(self, google_credentials, page: Page):
        super().__init__(google_credentials, page, "eni")
        self.account_code = None

    async def _login_eni(self):
        self.page.set_default_timeout(NAVIGATION_TIMEOUT)
        await self.page.goto(
            "https://eniplenitude.com/my-eni", wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT
        )

        # The privacy banner is only shown until the consent cookie is set.
        try:
            await self.page.get_by_role("button", name="Accept proposed privacy").click(timeout=10_000)
        except PlaywrightTimeoutError:
            self.logger.info("privacy banner not shown, skipping")

        email = self.page.get_by_role("textbox", name="email")
        await email.wait_for(state="visible")
        await email.fill(os.getenv("ENI_USERNAME"))  # pyright: ignore[reportArgumentType]

        # Eni serves the widget based on risk, so it is not always there.
        token = await solve_recaptcha_v2(self.page)
        if token is None:
            self.logger.info("no recaptcha widget, skipping")
        else:
            await apply_recaptcha_token(self.page, token)

        await self.page.get_by_role("button", name="Prosegui", exact=True).click()

        await self.page.get_by_role("textbox", name="password").fill(os.getenv("ENI_PASSWORD"))  # pyright: ignore[reportArgumentType]

        async with self.page.expect_navigation(wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT):
            await self.page.get_by_role("button", name="Accedi").click()

    async def get_invoices(self, start_date: date, end_date: date) -> list[Invoice]:
        invoices: list[Invoice] = []

        await self._login_eni()

        response = requests.get(
            "https://eniplenitude.com/serviceDAp/api/c360/init?logHash=wv5y2LVrjgcVRvW82WLEw3&channel=PORTAL",
            cookies=await self.get_cookies(),
        )
        response.raise_for_status()
        self.account_code = response.json()["codiceContoDefault"]
        client_code = response.json()["codiceCliente"]

        response = requests.get(
            f"https://eniplenitude.com/serviceDAp/c360/api/conti/{self.account_code}/bollette?logHash=8yVXbTfuaHIvAS5PvRHgnp&channel=PORTAL",
            cookies=await self.get_cookies(),
        )
        response.raise_for_status()
        invoice_list = list(
            map(
                lambda i: Invoice(
                    id=i["numeroBolletta"],
                    doc_date=datetime.strptime(i["emissione"], "%d/%m/%Y"),
                    due_date=datetime.strptime(i["scadenza"], "%d/%m/%Y"),
                    amount=i["importo"],
                    client_code=client_code,
                ),
                response.json()["bollette"],
            )
        )
        invoice_list_filtered = list(filter(lambda invoice: start_date <= invoice.doc_date <= end_date, invoice_list))
        if invoice_list_filtered:
            invoices.extend(invoice_list_filtered)

        return invoices

    async def download_invoice(self, invoice: Invoice) -> bytes:
        response = requests.get(
            f"https://eniplenitude.com/serviceDAp/c360/api/conti/{self.account_code}/download-doc-pdf?numeroFattura={invoice.id}&logHash=0golQ74cfqlmjhg1O5pHyn&channel=PORTAL",
            cookies=await self.get_cookies(),
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
