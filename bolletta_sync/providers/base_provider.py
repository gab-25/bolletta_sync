import base64
import logging
from abc import ABC
from datetime import date

from playwright.async_api import Page
from pydantic import BaseModel

from bolletta_sync.apps_script import AppsScriptClient


class Invoice(BaseModel):
    id: str
    doc_date: date
    due_date: date
    amount: float
    client_code: str
    metadata: dict | None = None


class BaseProvider(ABC):
    def __init__(self, apps_script: AppsScriptClient, page: Page, namespace: str):
        self._apps_script = apps_script
        self.page = page
        self._namespace = namespace
        self.namespace_folder_id = None
        self.namespace_tasklist_id = None

        self.logger = logging.getLogger(namespace)

    async def get_cookies(self) -> dict:
        cookies = {}
        for cookie in await self.page.context.cookies():
            cookies[cookie["name"]] = cookie["value"]  # pyright: ignore[reportTypedDictNotRequiredAccess]
        return cookies

    async def check_namespace(self) -> bool:
        result = await self._apps_script.call(
            "ensure_namespace",
            namespace=self._namespace,
            year=date.today().year,
            tasklist_name="Bollette",
        )
        self.namespace_folder_id = result["folder_id"]
        self.namespace_tasklist_id = result["tasklist_id"]

        return True

    async def get_invoices(self, start_date: date, end_date: date) -> list[Invoice]:
        """
        return the invoices from the provider
        """
        raise Exception("get invoices not implemented")

    async def download_invoice(self, invoice: Invoice) -> bytes:
        """
        download the invoice from the provider
        """
        raise Exception("download invoice not implemented")

    async def save_invoice(self, invoice: Invoice, invoice_pdf: bytes) -> bool:
        """
        save the invoice to google drive
        """
        file_name = f"{self._namespace}_{invoice.doc_date.strftime('%Y-%m-%d')}_{invoice.id}.pdf"
        result = await self._apps_script.call(
            "save_invoice",
            folder_id=self.namespace_folder_id,
            file_name=file_name,
            content=base64.b64encode(invoice_pdf).decode(),
        )

        if result["created"]:
            self.logger.info(f"create file {file_name} in google drive")
        else:
            self.logger.info(f"file {file_name} already exists in google drive")

        return True

    async def set_expire_invoice(self, invoice: Invoice) -> bool:
        """
        set expire invoice to google tasks
        """
        result = await self._apps_script.call(
            "set_expire_invoice",
            tasklist_id=self.namespace_tasklist_id,
            title=f"Pagare {self._namespace} fattura {invoice.id}",
            due=invoice.due_date.strftime("%Y-%m-%dT00:00:00Z"),
            notes=f"Totale: {invoice.amount}",
        )

        if result["created"]:
            self.logger.info(f"created task for invoice {invoice.id}")
        else:
            self.logger.info(f"task for invoice {invoice.id} already exists")

        return True
