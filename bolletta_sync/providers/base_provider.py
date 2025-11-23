from abc import ABC
from datetime import date
from io import BytesIO

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from playwright.async_api import Page
from pydantic import BaseModel

from bolletta_sync.main import logger


class Invoice(BaseModel):
    id: str
    doc_date: date
    due_date: date
    amount: float
    client_code: str
    metadata: dict = None


class BaseProvider(ABC):
    def __init__(self, google_credentials, page: Page, namespace: str):
        self._google_credentials = google_credentials
        self.page = page
        self._namespace = namespace
        self.namespace_folder_id = None
        self.namespace_tasklist_id = None

        self.drive_service = build("drive", "v3", credentials=self._google_credentials, cache_discovery=False)
        self.tasks_service = build("tasks", "v1", credentials=self._google_credentials, cache_discovery=False)

    async def get_cookies(self) -> dict:
        cookies = {}
        for cookie in await self.page.context.cookies():
            cookies[cookie['name']] = cookie['value']
        return cookies

    def _create_folder(self, folder_name: str, parent_folder_id: str = None) -> str:
        query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        if parent_folder_id:
            query += f" and '{parent_folder_id}' in parents"
        results = self.drive_service.files().list(
            q=query,
            spaces='drive'
        ).execute()

        if results.get('files'):
            return results.get('files')[0].get('id')

        folder_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        folder = self.drive_service.files().create(
            body=folder_metadata,
            fields='id'
        ).execute()

        return folder.get('id')

    async def check_namespace(self) -> bool:
        # google drive
        bollette_folder_id = self._create_folder("bollette")
        year_folder_id = self._create_folder(str(date.today().year), bollette_folder_id)
        self.namespace_folder_id = self._create_folder(self._namespace, year_folder_id)

        # google tasks
        tasklist_name = "Bollette"
        tasklists = self.tasks_service.tasklists().list().execute()
        self.namespace_tasklist_id = None
        for tasklist in tasklists.get('items', []):
            if tasklist['title'] == tasklist_name:
                self.namespace_tasklist_id = tasklist['id']
                break
        if not self.namespace_tasklist_id:
            tasklist = self.tasks_service.tasklists().insert(body={'title': tasklist_name}).execute()
            self.namespace_tasklist_id = tasklist['id']

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
        results = self.drive_service.files().list(
            q=f"name='{file_name}' and '{self.namespace_folder_id}' in parents and trashed=false",
            spaces='drive'
        ).execute()
        if results.get('files'):
            logger.info(f"file {file_name} already exists in google drive")
            return True

        file_metadata = {
            "name": file_name,
            "parents": [self.namespace_folder_id]
        }
        media = MediaIoBaseUpload(BytesIO(invoice_pdf), mimetype="application/pdf")
        file = self.drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id"
        ).execute()

        logger.info(f"create file {file_name} in google drive")

        return True

    async def set_expire_invoice(self, invoice: Invoice) -> bool:
        """
        set expire invoice to google tasks
        """
        task_title = f"Pagare {self._namespace} fattura {invoice.id}"
        tasks = self.tasks_service.tasks().list(tasklist=self.namespace_tasklist_id).execute()
        for task in tasks.get('items', []):
            if task['title'] == task_title:
                logger.info(f"task for invoice {invoice.id} already exists")
                return True

        task_metadata = {
            'title': task_title,
            'due': invoice.due_date.strftime('%Y-%m-%dT00:00:00Z'),
            'notes': f'Totale: {invoice.amount}'
        }
        task = self.tasks_service.tasks().insert(tasklist=self.namespace_tasklist_id, body=task_metadata).execute()

        logger.info(f"created task for invoice {invoice.id}")

        return True
