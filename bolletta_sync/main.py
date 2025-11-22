import asyncio
import logging
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

logger = logging.getLogger()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] - %(message)s")

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
    provider: Provider
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def validate_year(self):
        if self.start_date.year != self.end_date.year:
            raise ValueError("start_date and end_date must be in the same year")
        return self


async def sync(params: SyncParams, google_credentials: Credentials, brower: Browser):
    logger.info(f"{params.provider.value} - Syncing invoices from {params.start_date} to {params.end_date}")

    page = await brower.new_page()
    instance = None

    if params.provider == Provider.FASTWEB:
        instance = Fastweb(google_credentials, page)
    elif params.provider == Provider.FASTEWEB_ENERGIA:
        instance = FastwebEnergia(google_credentials, page)
    elif params.provider == Provider.ENI:
        instance = Eni(google_credentials, page)
    elif params.provider == Provider.UMBRA_ACQUE:
        instance = UmbraAcque(google_credentials, page)

    if instance is None:
        raise Exception("Unknown provider")

    try:
        logger.info(f"{params.provider.value} - Syncing invoices")
        invoces = await instance.get_invoices(params.start_date, params.end_date)
        logger.info(f"{params.provider.value} - Synced {len(invoces)} invoices")
        await instance.check_namespace()
        for invoce in invoces:
            doc = await instance.download_invoice(invoce)
            await instance.save_invoice(invoce, doc)
            await instance.set_expire_invoice(invoce)
    except Exception as e:
        logger.error(f"{params.provider.value} - Error while syncing with {params.provider.value}", e)
        raise e

    logger.info(f"{params.provider.value} - Invoices synced successfully")


async def get_google_credentials() -> Credentials:
    google_credentials = None

    if os.path.exists(google_token_file):
        google_credentials = Credentials.from_authorized_user_file(google_token_file, google_auth_scopes)
    else:
        logger.info("Google credentials not found, starting Google OAuth flow")
        await google_auth()

    if google_credentials and google_credentials.expired:
        logger.info("Google credentials expired, refreshing")
        google_credentials.refresh(AuthRequest())

    return google_credentials


async def google_auth():
    flow = InstalledAppFlow.from_client_secrets_file(google_credentials_file, google_auth_scopes)
    credentials = flow.run_local_server(port=0)

    with open(google_token_file, "w") as token:
        token.write(credentials.to_json())


async def main(providers: list[Provider] = None, start_date: date = None, end_date: date = None):
    google_credentials = await get_google_credentials()

    start_date = start_date if start_date else date.today() - timedelta(days=10)
    end_date = end_date if end_date else date.today()
    providers = providers if providers else list(Provider)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=DEV_MODE == False)
        tasks = []
        for provider in providers:
            params = SyncParams(provider=provider, start_date=start_date, end_date=end_date)
            tasks.append(sync(params, google_credentials, browser))
        await asyncio.gather(*tasks)
