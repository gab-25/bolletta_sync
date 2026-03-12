import asyncio
import json
import logging
import os
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Tuple, Optional

from google.auth.transport.requests import Request as AuthRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from playwright.async_api import async_playwright, Browser

from bolletta_sync.providers.base_provider import Invoice
from bolletta_sync.providers.eni import Eni
from bolletta_sync.providers.fastweb import Fastweb
from bolletta_sync.providers.fastweb_energia import FastwebEnergia
from bolletta_sync.providers.umbra_acque import UmbraAcque

logger = logging.getLogger(__name__)

# Paths and Scopes
google_auth_scopes = ["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/tasks"]
google_credentials_file = "./data/google_credentials.json"
google_token_file = "./data/google_token.json"
last_sync_file = "./data/last_sync.json"


class Provider(Enum):
    """Provider enum."""

    FASTWEB = "fastweb"
    FASTEWEB_ENERGIA = "fastweb_energia"
    ENI = "eni"
    UMBRA_ACQUE = "umbra_acque"


def get_google_flow(redirect_uri: str) -> Flow:
    """
    Creates a Google OAuth flow instance for a Web application.
    """
    if not os.path.exists(google_credentials_file):
        raise FileNotFoundError(f"Google credentials file not found at {google_credentials_file}")

    return Flow.from_client_secrets_file(
        google_credentials_file,
        scopes=google_auth_scopes,
        redirect_uri=redirect_uri,
    )


async def get_google_credentials() -> Optional[Credentials]:
    """
    Loads Google credentials from the token file.
    Refreshes the credentials if they are expired.
    Returns None if no token exists.
    """
    google_credentials = None

    if os.path.exists(google_token_file):
        google_credentials = Credentials.from_authorized_user_file(google_token_file, google_auth_scopes)
    else:
        logger.info("Google token file not found.")
        return None

    if google_credentials.expired:
        logger.info("Google credentials expired, refreshing")
        try:
            await asyncio.to_thread(google_credentials.refresh, AuthRequest())
            with open(google_token_file, "w") as token:
                token.write(google_credentials.to_json())
        except Exception as e:
            logger.error(f"Failed to refresh Google credentials: {e}")
            return None

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

    async def _exec_sync(self, provider: Provider, browser: Browser) -> List[Invoice]:
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

            logger.info(f"{provider.value} - Invoices synced successfully")
            return invoices
        except Exception as e:
            logger.error(f"{provider.value} - Error while syncing cause: {e}")
            raise e
        finally:
            await page.close()

    async def run(self, headless: bool = True) -> Dict[str, Any]:
        """Run syncs invoices for the given providers and returns a summary of the results."""
        results = {}

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=headless)

            for provider in self._providers:
                try:
                    invoices = await self._exec_sync(provider, browser)
                    results[provider.value] = {
                        "status": "success",
                        "count": len(invoices),
                        "invoices": [invoice.model_dump(mode="json") for invoice in invoices],
                    }
                except Exception as e:
                    results[provider.value] = {"status": "error", "error": str(e)}

            await browser.close()

        # Persist result to data folder
        try:
            # Overall status is success only if all individual results are success
            overall_status = "success"
            if not results:
                overall_status = "empty"
            elif any(res.get("status") == "error" for res in results.values()):
                overall_status = "error"

            with open(last_sync_file, "w") as f:
                json.dump(
                    {
                        "date": datetime.now().isoformat(),
                        "status": overall_status,
                        "results": results,
                    },
                    f,
                    indent=4,
                )
        except Exception as e:
            logger.error(f"Failed to save last sync result: {e}")

        return results
