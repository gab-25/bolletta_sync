import asyncio
import logging
import os
from datetime import date
from enum import Enum
from typing import List, Tuple

from google.auth.transport.requests import Request as AuthRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from playwright.async_api import async_playwright, Browser

from bolletta_sync.providers.eni import Eni
from bolletta_sync.providers.fastweb import Fastweb
from bolletta_sync.providers.fastweb_energia import FastwebEnergia
from bolletta_sync.providers.umbra_acque import UmbraAcque

logger = logging.getLogger(__name__)

# Paths and Scopes
google_auth_scopes = ["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/tasks"]
google_credentials_file = "google_credentials.json"
google_token_file = "google_token.json"


class Provider(Enum):
    """Provider enum."""

    FASTWEB = "fastweb"
    FASTEWEB_ENERGIA = "fastweb_energia"
    ENI = "eni"
    UMBRA_ACQUE = "umbra_acque"


async def google_auth() -> Credentials:
    """
    Starts the Google OAuth flow to obtain user credentials.
    """
    if not os.path.exists(google_credentials_file):
        raise FileNotFoundError(f"Google credentials file not found at {google_credentials_file}")

    flow = InstalledAppFlow.from_client_secrets_file(google_credentials_file, google_auth_scopes)
    credentials = flow.run_local_server(port=0)

    with open(google_token_file, "w") as token:
        token.write(credentials.to_json())

    return credentials  # type: ignore[reportReturnType]


async def get_google_credentials() -> Credentials:
    """
    Loads Google credentials from a file or starts the OAuth flow if not found.
    Refreshes the credentials if they are expired.
    """
    google_credentials = None

    if os.path.exists(google_token_file):
        google_credentials = Credentials.from_authorized_user_file(google_token_file, google_auth_scopes)
    else:
        logger.info("Google credentials not found, starting Google OAuth flow")
        google_credentials = await google_auth()

    if google_credentials is None:
        raise Exception("Google credentials not found!")

    if google_credentials.expired:
        logger.info("Google credentials expired, refreshing")
        google_credentials.refresh(AuthRequest())
        with open(google_token_file, "w") as token:
            token.write(google_credentials.to_json())

    return google_credentials


class Sync:
    """
    Syncs invoices for a list of providers over a given date range.
    """

    def __init__(
        self, google_credentials: Credentials, providers: List[Provider], date_range: Tuple[date, date]
    ) -> None:
        self._google_credentials = google_credentials
        self._providers = providers
        self._date_range = date_range

    async def _exec_sync(self, provider: Provider, browser: Browser):
        logger.info(f"{provider.value} - Syncing invoices from {self._date_range[0]} to {self._date_range[1]}")

        page = await browser.new_page(locale="en-EN")
        instance = None

        if provider == Provider.FASTWEB:
            instance = Fastweb(self._google_credentials, page)
        elif provider == Provider.FASTEWEB_ENERGIA:
            instance = FastwebEnergia(self._google_credentials, page)
        elif provider == Provider.ENI:
            instance = Eni(self._google_credentials, page)
        elif provider == Provider.UMBRA_ACQUE:
            instance = UmbraAcque(self._google_credentials, page)

        if instance is None:
            raise Exception("Unknown provider")

        try:
            logger.info(f"{provider.value} - Syncing invoices")
            invoices = await instance.get_invoices(self._date_range[0], self._date_range[1])
            logger.info(f"{provider.value} - Synced {len(invoices)} invoices")
            await instance.check_namespace()
            for invoice in invoices:
                doc = await instance.download_invoice(invoice)
                await instance.save_invoice(invoice, doc)
                await instance.set_expire_invoice(invoice)
        except Exception as e:
            logger.error(f"{provider.value} - Error while syncing cause: {e}")
            raise e

        logger.info(f"{provider.value} - Invoices synced successfully")

    async def run(self, headless: bool = False):
        """Run syncs invoices for the given providers using the provided Google credentials."""

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=headless)
            tasks = []
            for provider in self._providers:
                tasks.append(self._exec_sync(provider, browser))
            await asyncio.gather(*tasks)
