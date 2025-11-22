import argparse
import os
from datetime import date, timedelta
from enum import Enum

from dotenv import load_dotenv
from google.auth.transport.requests import Request as AuthRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from playwright.async_api import async_playwright, Browser
from pydantic import BaseModel, model_validator

DEV_MODE = os.getenv("DEV_MODE") == "true"
dotenv_path = os.path.expanduser("~/.bolletta_sync") if not DEV_MODE else ".env"
load_dotenv(dotenv_path=dotenv_path)

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
    providers: list[Provider] = list(Provider)
    start_date: date = date.today() - timedelta(days=10)
    end_date: date = date.today()

    @model_validator(mode="after")
    def validate_year(self):
        if self.start_date.year != self.end_date.year:
            raise ValueError("start_date and end_date must be in the same year")
        return self


async def sync(sync_params: SyncParams, google_credentials: Credentials, brower: Browser):
    if sync_params.providers is None:
        sync_params.providers = list(Provider)
    if sync_params.start_date is None:
        sync_params.start_date = date.today().replace(day=1)
    if sync_params.end_date is None:
        sync_params.end_date = (sync_params.start_date + timedelta(days=31)).replace(day=1)

    print(f"Syncing invoices from {sync_params.start_date} to {sync_params.end_date}, "
          f"providers: {list(map(lambda p: p.value, sync_params.providers))}")

    for provider in sync_params.providers:
        page = await brower.new_page()
        instance = None

        if provider == Provider.FASTWEB:
            instance = Fastweb(google_credentials, page)
        elif provider == Provider.FASTEWEB_ENERGIA:
            instance = FastwebEnergia(google_credentials, page)
        elif provider == Provider.ENI:
            instance = Eni(google_credentials, page)
        elif provider == Provider.UMBRA_ACQUE:
            instance = UmbraAcque(google_credentials, page)

        if instance is None:
            raise Exception("Unknown provider")

        try:
            print(f"Syncing invoices from {provider.value}")
            invoces = await instance.get_invoices(sync_params.start_date, sync_params.end_date)
            print(f"Synced {len(invoces)} invoices from {provider.value}")
            await instance.check_namespace()
            for invoce in invoces:
                doc = await instance.download_invoice(invoce)
                await instance.save_invoice(invoce, doc)
                await instance.set_expire_invoice(invoce)
        except Exception as e:
            print(f"Error while syncing with {provider.value}", e)
            raise e

    return {"message": "invoices synced successfully"}


async def get_google_credentials() -> Credentials:
    google_credentials = None

    if os.path.exists(google_token_file):
        google_credentials = Credentials.from_authorized_user_file(google_token_file, google_auth_scopes)
    else:
        print("Google credentials not found, starting Google OAuth flow")
        await google_auth()

    if google_credentials and google_credentials.expired:
        print("Google credentials expired, refreshing")
        google_credentials.refresh(AuthRequest())

    return google_credentials


async def google_auth():
    flow = InstalledAppFlow.from_client_secrets_file(google_credentials_file, google_auth_scopes)
    credentials = flow.run_local_server(port=0)

    with open(google_token_file, "w") as token:
        token.write(credentials.to_json())


async def main():
    google_credentials = await get_google_credentials()
    params = SyncParams()

    parser = argparse.ArgumentParser(description='Sync invoices from providers')
    parser.add_argument('--start_date', type=str, help='Start date in format YYYY-MM-DD')
    parser.add_argument('--end_date', type=str, help='End date in format YYYY-MM-DD')
    parser.add_argument('--providers', nargs='+', type=Provider, help='List of providers to sync')
    args = parser.parse_args()

    if args.start_date:
        params.start_date = date.fromisoformat(args.start_date)
    if args.end_date:
        params.end_date = date.fromisoformat(args.end_date)
    if args.providers:
        params.providers = args.providers

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=DEV_MODE == False)
        await sync(params, google_credentials, browser)
