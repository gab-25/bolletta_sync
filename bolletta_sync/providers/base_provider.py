import os
from abc import ABC
from datetime import date
from io import BytesIO

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from pydantic import BaseModel


class Invoice(BaseModel):
    id: str
    doc_date: date
    due_date: date
    amount: float


class BaseProvider(ABC):
    def __init__(self, google_credentials, logger):
        self._google_credentials = google_credentials
        self._logger = logger

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
        drive_service = build("drive", "v3", credentials=self._google_credentials)

        file_metadata = {
            "name": f"Fastweb_{invoice.doc_date.strftime('%Y-%m-%d')}_{invoice.id}.pdf",
            "parents": [os.getenv("GOOGLE_DRIVE_FOLDER_ID")]
        }

        media = MediaIoBaseUpload(BytesIO(invoice_pdf), mimetype="application/pdf")

        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id"
        ).execute()

        self._logger.info(f"create file {file.get('name')} in google drive")

        return file.get("id") is not None

    async def set_expire_invoice(self, invoice: Invoice) -> bool:
        """
        set expire invoice to google calendar
        """
        calendar_service = build("calendar", "v3", credentials=self._google_credentials)

        event = {
            'summary': f'Scadenza Fastweb {invoice.id}',
            'description': f'Fattura Fastweb {invoice.id} - {invoice.amount}€',
            'start': {
                'date': invoice.due_date.strftime('%Y-%m-%d'),
            },
            'end': {
                'date': invoice.due_date.strftime('%Y-%m-%d'),
            },
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'email', 'minutes': 24 * 60},
                    {'method': 'popup', 'minutes': 24 * 60},
                ],
            },
        }

        event = calendar_service.events().insert(
            calendarId='primary',
            body=event
        ).execute()

        self._logger.info(f"created calendar event for invoice {invoice.id}")

        return event.get('id') is not None
