import os
from datetime import date, datetime

import requests
from playwright.sync_api import Playwright
from playwright_recaptcha import recaptchav2

from bolletta_sync.providers.base_provider import BaseProvider, Invoice


class Eni(BaseProvider):
    def __init__(self, google_credentials, playwright: Playwright):
        super().__init__(google_credentials, playwright, "eni")

    def _login_eni(self):
        self.page.goto("https://eniplenitude.com/my-eni/")

        with recaptchav2.SyncSolver(self.page) as solver:
            self.page.get_by_role("listitem", name="Accept proposed privacy").click()
            self.page.get_by_role("textbox", name="email").fill(os.getenv("ENI_USERNAME"))
            solver.solve_recaptcha(wait=True)
            self.page.get_by_role("button", name="Prosegui", exact=True).click()

            self.page.get_by_role("textbox", name="password").fill(os.getenv("ENI_PASSWORD"))
            self.page.get_by_role("button", name="Accedi").click()
            self.page.wait_for_timeout(1000)
            solver.solve_recaptcha(wait=True)

        with self.page.expect_navigation():
            self.page.get_by_role("button", name="Accedi").click()

    def get_invoices(self, start_date: date, end_date: date) -> list[Invoice]:
        invoices: list[Invoice] = []

        self._login_eni()

        response = requests.get(
            "https://api.eniplenitude.com/v1/contracts",
            cookies=self.get_cookies()
        )
        response.raise_for_status()
        contract_id = response.json()["contracts"][0]["id"]

        response = requests.get(
            f"https://api.eniplenitude.com/v1/invoices/{contract_id}",
            params={
                "from": start_date.strftime("%Y-%m-%d"),
                "to": end_date.strftime("%Y-%m-%d")
            },
            cookies=self.get_cookies()
        )
        response.raise_for_status()

        for inv in response.json()["invoices"]:
            invoice = Invoice(
                id=inv["number"],
                doc_date=datetime.strptime(inv["date"], "%Y-%m-%d"),
                due_date=datetime.strptime(inv["dueDate"], "%Y-%m-%d"),
                amount=float(inv["amount"]),
                client_code=contract_id
            )
            invoices.append(invoice)

        return invoices

    def download_invoice(self, invoice: Invoice) -> bytes:
        response = requests.get(
            f"https://api.eniplenitude.com/v1/invoices/{invoice.client_code}/{invoice.id}/pdf",
            cookies=self.get_cookies()
        )

        if response.status_code != 200:
            raise Exception(f"Failed to download invoice PDF: {response.url} HTTP {response.status_code}")

        return response.content

    def save_invoice(self, invoice: Invoice, invoice_pdf: bytes) -> bool:
        result = super().save_invoice(invoice, invoice_pdf)
        return result

    def set_expire_invoice(self, invoice: Invoice) -> bool:
        result = super().set_expire_invoice(invoice)
        return result
