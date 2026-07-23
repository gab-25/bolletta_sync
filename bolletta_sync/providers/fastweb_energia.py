import os
from datetime import date

import requests
from playwright.async_api import Page

from bolletta_sync.providers.base_provider import BaseProvider, Invoice


class FastwebEnergia(BaseProvider):
    def __init__(self, google_credentials, page: Page):
        super().__init__(google_credentials, page, "fastweb_energia")
        # Optional comma-separated supply codes (e.g. luce and gas). When not set
        # we fall back to [None], which keeps the previous single-supply behaviour.
        supply_env = os.getenv("FASTWEB_ENERGIA_SUPPLY_CODE")
        self.supply_codes = supply_env.split(",") if supply_env else [None]

    async def _login_fastweb_energia(self):
        await self.page.goto("https://www.fastweb.it/myfastweb-energia/login/")

        await (
            self.page.locator('iframe[title="Cookie center"]')
            .content_frame.get_by_role("button", name="Accetta tutti")
            .click()
        )

        await self.page.get_by_placeholder("username").click()
        await self.page.get_by_role("textbox", name="username").fill(os.getenv("FASTWEB_ENERGIA_USERNAME"))  # pyright: ignore[reportArgumentType]
        await self.page.get_by_placeholder("password").click()
        await self.page.get_by_role("textbox", name="password").fill(os.getenv("FASTWEB_ENERGIA_PASSWORD"))  # pyright: ignore[reportArgumentType]
        async with self.page.expect_navigation():
            await self.page.get_by_role("link", name="Accedi").click()

    async def _select_supply(self, supply_code: str | None):
        # When no supply code is configured, keep the currently active supply.
        if supply_code is None:
            return

        await self.page.goto(
            "https://www.fastweb.it/myfastweb-energia/scelta-fornitura/?from=profile&DirectLink=/myfastweb-energia/"
        )

        try:
            await self.page.get_by_text(supply_code, exact=True).click()
            avanti = self.page.get_by_role("link", name="Avanti")
            async with self.page.expect_navigation():
                await avanti.click()
        except Exception:
            raise Exception(f"invalid supply code: {supply_code}")

    async def get_invoices(self, start_date: date, end_date: date) -> list[Invoice]:
        invoices: list[Invoice] = []

        await self._login_fastweb_energia()

        for supply_code in self.supply_codes:
            if supply_code is not None:
                self.logger.info(f"fastweb_energia - getting invoices for supply {supply_code}")
            await self._select_supply(supply_code)

            payload = {"action": "loadInvoiceList"}
            response = requests.post(
                "https://www.fastweb.it/myfastweb-energia/services/invoices/",
                payload,
                cookies=await self.get_cookies(),
            )

            client_code = supply_code or os.getenv("FASTWEB_ENERGIA_USERNAME")
            invoice_list = list(
                map(
                    lambda i: Invoice(
                        id=i["NumDoc"],
                        doc_date=i["DocDateYMD"],
                        due_date=i["DocExpireDateYMD"],
                        amount=i["DocAmount"],
                        client_code=client_code,  # pyright: ignore[reportArgumentType]
                    ),
                    response.json().get("invoiceList", []),
                )
            )
            invoice_list_filtered = list(
                filter(
                    lambda invoice: start_date <= invoice.doc_date <= end_date,
                    invoice_list,
                )
            )
            if invoice_list_filtered:
                invoices.extend(invoice_list_filtered)

        return invoices

    async def download_invoice(self, invoice: Invoice) -> bytes:
        # Re-select the supply the invoice belongs to, since the download depends
        # on the supply active in the session. The username fallback means no
        # supply selection is needed (single-supply mode).
        if invoice.client_code != os.getenv("FASTWEB_ENERGIA_USERNAME"):
            await self._select_supply(invoice.client_code)

        response = requests.get(
            f"https://www.fastweb.it/myfastweb-energia/bollette/download/{invoice.id}-{invoice.doc_date}.pdf",
            cookies=await self.get_cookies(),
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
