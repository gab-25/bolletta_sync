from abc import ABC
from datetime import date

from pydantic import BaseModel


class Invoice(BaseModel):
    id: str
    doc_date: date
    due_date: date
    amount: float


class BaseProvider(ABC):
    async def get_invoices(self, start_date: date, end_date: date) -> list[Invoice]:
        """
        return the invoices from the provider
        """
        raise Exception("get invoices not implemented")

    async def download_invoice(self, invoice_id: str) -> bytes:
        """
        download the invoice from the provider
        """
        raise Exception("download invoice not implemented")

    async def save_invoice(self, invoice: Invoice, invoice_pdf: bytes) -> bool:
        """
        save the invoice to google drive
        """
        raise Exception("save invoice not implemented")
