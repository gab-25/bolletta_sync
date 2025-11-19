import os
from datetime import date, timedelta
from enum import Enum

from dotenv import load_dotenv
from google.auth.transport.requests import Request as AuthRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from playwright.sync_api import Playwright, sync_playwright
from pydantic import BaseModel, model_validator

DEV_MODE = os.environ.get("DEV_MODE") == "true"
if DEV_MODE:
    load_dotenv()

from bolletta_sync.providers.eni import Eni
from bolletta_sync.providers.fastweb import Fastweb
from bolletta_sync.providers.fastweb_energia import FastwebEnergia
from bolletta_sync.providers.umbra_acque import UmbraAcque

google_auth_scopes = ["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/tasks"]
google_credentials_file = "./google_credentials.json"
google_token_file = "./google_token.json"


class Provider(Enum):
    FASTWEB = "fastweb"
    FASTEWEB_ENERGIA = "fastweb_energia"
    ENI = "eni"
    UMBRA_ACQUE = "umbra_acque"


class SyncParams(BaseModel):
    providers: list[Provider] = [Provider.FASTWEB]
    start_date: date = date.today() - timedelta(days=10)
    end_date: date = date.today()

    @model_validator(mode="after")
    def validate_year(self):
        if self.start_date.year != self.end_date.year:
            raise ValueError("start_date and end_date must be in the same year")
        return self


def sync(sync_params: SyncParams, google_credentials: Credentials, playwright: Playwright):
    if sync_params.providers is None:
        sync_params.providers = list(Provider)
    if sync_params.start_date is None:
        sync_params.start_date = date.today().replace(day=1)
    if sync_params.end_date is None:
        sync_params.end_date = (sync_params.start_date + timedelta(days=31)).replace(day=1)

    print(f"Syncing invoices from {sync_params.start_date} to {sync_params.end_date}")

    for provider in sync_params.providers:
        instance = None

        if provider == Provider.FASTWEB:
            instance = Fastweb(google_credentials, playwright)
        elif provider == Provider.FASTEWEB_ENERGIA:
            instance = FastwebEnergia(google_credentials)
        elif provider == Provider.ENI:
            instance = Eni()
        elif provider == Provider.UMBRA_ACQUE:
            instance = UmbraAcque()

        if instance is None:
            raise Exception("Unknown provider")

        try:
            print(f"Syncing invoices from {provider.value}")
            invoces = instance.get_invoices(sync_params.start_date, sync_params.end_date)
            print(f"Synced {len(invoces)} invoices from {provider.value}")
            instance.check_namespace()
            for invoce in invoces:
                doc = instance.download_invoice(invoce)
                instance.save_invoice(invoce, doc)
                instance.set_expire_invoice(invoce)
        except Exception as e:
            print(f"Error while syncing with {provider.value}", e)
            raise e

    return {"message": "invoices synced successfully"}


def get_google_credentials() -> Credentials:
    google_credentials = None

    if os.path.exists(google_token_file):
        google_credentials = Credentials.from_authorized_user_file(google_token_file, google_auth_scopes)
    else:
        google_auth()

    if google_credentials and google_credentials.expired:
        google_credentials.refresh(AuthRequest())

    return google_credentials


def google_auth():
    flow = InstalledAppFlow.from_client_secrets_file(google_credentials_file, google_auth_scopes)
    credentials = flow.run_local_server(port=0)

    with open(google_token_file, "w") as token:
        token.write(credentials.to_json())

    print("Google OAuth flow completed successfully")


def main():
    google_credentials = get_google_credentials()
    params = SyncParams()

    with sync_playwright() as playwright:
        sync(params, google_credentials, playwright)
