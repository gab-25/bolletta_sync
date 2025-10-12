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
    client_code: str


class BaseProvider(ABC):
    def __init__(self, google_credentials, logger, namespace: str):
        self._google_credentials = google_credentials
        self._logger = logger
        self._namespace = namespace

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
        drive_service = build("drive", "v3", credentials=self._google_credentials, cache_discovery=False)

        namespace_folder_id = None
        folder_metadata = {
            'name': self._namespace,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [os.getenv('GOOGLE_DRIVE_FOLDER_ID')]
        }
        results = drive_service.files().list(
            q=f"name='{self._namespace}' and mimeType='application/vnd.google-apps.folder' and '{os.getenv('GOOGLE_DRIVE_FOLDER_ID')}' in parents",
            spaces='drive'
        ).execute()
        if not results.get('files'):
            folder = drive_service.files().create(
                body=folder_metadata,
                fields='id'
            ).execute()
            namespace_folder_id = folder.get('id')
        else:
            namespace_folder_id = results.get('files')[0].get('id')

        file_name = f"{self._namespace}_{invoice.doc_date.strftime('%Y-%m-%d')}_{invoice.id}.pdf"
        results = drive_service.files().list(
            q=f"name='{file_name}' and '{namespace_folder_id}' in parents",
            spaces='drive'
        ).execute()
        if results.get('files'):
            self._logger.info(f"file {file_name} already exists in google drive")
            return True

        file_metadata = {
            "name": file_name,
            "parents": [namespace_folder_id]
        }
        media = MediaIoBaseUpload(BytesIO(invoice_pdf), mimetype="application/pdf")
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id"
        ).execute()

        self._logger.info(f"create file {file_name} in google drive")

        return True

    async def set_expire_invoice(self, invoice: Invoice) -> bool:
        """
        set expire invoice to google tasks
        """
        tasks_service = build("tasks", "v1", credentials=self._google_credentials, cache_discovery=False)

        tasklist_name = "Bollette"
        tasklists = tasks_service.tasklists().list().execute()
        tasklist_id = None
        for tasklist in tasklists.get('items', []):
            if tasklist['title'] == tasklist_name:
                tasklist_id = tasklist['id']
                break
        if not tasklist_id:
            tasklist = tasks_service.tasklists().insert(body={'title': tasklist_name}).execute()
            tasklist_id = tasklist['id']

        task_title = f"Pagare {self._namespace} fattura {invoice.id}"
        tasks = tasks_service.tasks().list(tasklist=tasklist_id).execute()
        for task in tasks.get('items', []):
            if task['title'] == task_title:
                self._logger.info(f"task for invoice {invoice.id} already exists")
                return True

        task_metadata = {
            'title': task_title,
            'due': invoice.due_date.strftime('%Y-%m-%dT00:00:00Z'),
            'notes': f'Totale: {invoice.amount}'
        }
        task = tasks_service.tasks().insert(tasklist=tasklist_id, body=task_metadata).execute()

        self._logger.info(f"created task for invoice {invoice.id}")

        return True
