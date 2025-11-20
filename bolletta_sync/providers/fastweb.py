import os
from datetime import date

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import Playwright

from bolletta_sync.providers.base_provider import BaseProvider, Invoice


class Fastweb(BaseProvider):
    def __init__(self, google_credentials, playwright: Playwright):
        super().__init__(google_credentials, playwright, "fastweb")
        if os.getenv("FASTWEB_CLIENT_CODE") is None:
            raise Exception("FASTWEB_CLIENT_CODE not set")
        self.client_codes = os.getenv("FASTWEB_CLIENT_CODE").split(",")

    def _login_fastweb(self):
        page = self.browser.new_page()
        page.goto("https://fastweb.it/myfastweb/accesso/login/")

        page.locator("iframe[title=\"Cookie center\"]").content_frame.get_by_role("button",
                                                                                  name="Accetta tutti").click()

        page.get_by_placeholder("username").click()
        page.get_by_role("textbox", name="username").fill(os.getenv("FASTWEB_USERNAME"))
        page.get_by_placeholder("password").click()
        page.get_by_role("textbox", name="password").fill(os.getenv("FASTWEB_PASSWORD"))
        with page.expect_navigation():
            page.get_by_role("link", name="Accedi").click()

    def _select_profile(self, client_code: str):
        page = self.browser.pages[0]
        page.goto("https://fastweb.it/myfastweb/accesso/seleziona-codice-cliente/")

        try:
            page.get_by_text(client_code).click()
            with page.expect_navigation():
                page.get_by_role("link", name="Avanti").click()
        except:
            raise Exception("invalid client code")

    def get_invoices(self, start_date: date, end_date: date) -> list[Invoice]:
        invoices: list[Invoice] = []

        self._login_fastweb()

        for client_code in self.client_codes:
            print(f"getting invoices for client {client_code}")
            self._select_profile(client_code)

            response = requests.get("https://fastweb.it/myfastweb/abbonamento/le-mie-fatture/",
                                    cookies=self.get_cookies())
            soup = BeautifulSoup(response.text, "html.parser")

            security_token = soup.find("input", {"name": "securityToken"}).get("value")
            payload = {"action": "loadInvoiceList", "securityToken": security_token}
            response = requests.post(
                "https://fastweb.it/myfastweb/abbonamento/le-mie-fatture/ajax/index.php",
                payload,
                params={"action": "loadInvoiceList"},
                cookies=self.get_cookies(),
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
        response = requests.get(
            f"https://fastweb.it/myfastweb/abbonamento/le-mie-fatture/conto-fastweb/Conto-FASTWEB-{invoice.id}-{invoice.doc_date.strftime('%Y%m%d')}.pdf",
            cookies=self.get_cookies(),
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
