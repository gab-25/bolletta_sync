import logging
import os
from datetime import date

import requests

from bolletta_sync.providers.base_provider import BaseProvider, Invoice
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


class UmbraAcque(BaseProvider):
    def __init__(self, google_credentials, solver):
        super().__init__(google_credentials, logger, "umbra_acque")
        self._solver = solver
        self._session = requests.Session()

    async def _login_umbra_acque(self):
        self._session.cookies.clear()

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()

            try:
                await page.goto("https://self-service.umbraacque.com/umbraacque/login", wait_until="networkidle")
                result = self._solver.recaptcha(sitekey="6LcO28gqAAAAAATkRJuvOZI41YhfX9u-jwWs_14N",
                                                url="https://self-service.umbraacque.com/umbraacque/login",
                                                version="v3")

                captcha_token = result['code']

                await page.evaluate(
                    f"""
                    (token) => {{
                        const responseField = document.querySelector('[name="g-recaptcha-response"]');
                        if (responseField) {{
                            responseField.value = token;
                            console.log('Token iniettato nel campo nascosto.');

                            // **Azione Aggiuntiva:**
                            // A volte è necessario chiamare grecaptcha.execute() o inviare il form.
                            // Questa parte dipende dalla logica JavaScript del sito specifico.
                            // Se il sito usa la logica automatica, potresti non aver bisogno di altro.
                        }} else {{
                            console.error('Campo g-recaptcha-response non trovato.');
                        }}
                    }}
                    """,
                    captcha_token
                )

                await page.fill("input[name='username']", os.getenv("UMBRA_ACQUE_USERNAME"))
                await page.fill("input[type='password']", os.getenv("UMBRA_ACQUE_PASSWORD"))
                await page.click("input[type='submit']")

                await page.wait_for_url("https://self-service.umbraacque.com/umbraacque/selfcare/privato", timeout=5000)
            except Exception as e:
                logger.error(e)
                raise Exception("login failed")
            finally:
                await browser.close()

    async def get_invoices(self, start_date: date, end_date: date) -> list[Invoice]:
        invoices: list[Invoice] = []

        await self._login_umbra_acque()

        response = self._session.get("https://self-service.umbraacque.com/bin/acea-myacea/utenze", params={
            "path": "/content/acea-myacea/umbraacque/selfcare/privato"})
        response.raise_for_status()
        contract_pk = response.json().get("data")[0]["contractPk"]

        response = self._session.get(
            "https://self-service.umbraacque.com/bin/acea-myacea/invoicesAndBalance",
            params={
                "path": "/content/acea-myacea/umbraacque/selfcare/fatture/jcr:content/content-private-par/invoices_table",
                "contractPk": contract_pk
            }
        )
        response.raise_for_status()
        invoice_list = list(
            map(lambda i: Invoice(id=i["invoiceNumber"], doc_date=i["issueDate"], due_date=i["expiryDate"],
                                  amount=i["total"], client_code=i["contractId"]),
                response.json().get("body")["invoices"]))
        invoice_list_filtered = list(
            filter(lambda invoice: start_date <= invoice.doc_date <= end_date, invoice_list))
        if invoice_list_filtered:
            invoices.extend(invoice_list_filtered)

        return invoices

    async def download_invoice(self, invoice: Invoice) -> bytes:
        return b""

    async def save_invoice(self, invoice: Invoice, invoice_pdf: bytes) -> bool:
        result = await super().save_invoice(invoice, invoice_pdf)
        return result

    async def set_expire_invoice(self, invoice: Invoice) -> bool:
        result = await super().set_expire_invoice(invoice)
        return result
