import logging
import os
from datetime import date, timedelta
from enum import Enum

from dotenv import load_dotenv
from fastapi import FastAPI, Security, HTTPException, APIRouter
from fastapi.params import Depends
from fastapi.security import APIKeyHeader
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from pydantic import BaseModel
from starlette import status

from bolletta_sync.providers.eni import Eni
from bolletta_sync.providers.fastweb import Fastweb
from bolletta_sync.providers.fastweb_energia import FastwebEnergia
from bolletta_sync.providers.umbra_acque import UmbraAcque

load_dotenv()

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

app = FastAPI()

api_key_header = APIKeyHeader(name="X-API-Key")


async def validate_api_key(key: str = Security(api_key_header)):
    if key != os.environ.get("API_KEY"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized - API Key is wrong"
        )
    return None


def google_login():
    scopes = ["https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/tasks"]
    credentials = None

    if os.path.exists("google_token.json"):
        credentials = Credentials.from_authorized_user_file("google_token.json", scopes)

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "google_credentials.json", scopes
            )
            credentials = flow.run_local_server(port=0)
        with open("google_token.json", "w") as token:
            token.write(credentials.to_json())

    return credentials


router = APIRouter(dependencies=[Depends(validate_api_key)])
google_credentials = google_login()


class Provider(Enum):
    FASTWEB = "fastweb"
    FASTEWEB_ENERGIA = "fastweb_energia"
    ENI = "eni"
    UMBRA_ACQUE = "umbra_acque"


class SyncParams(BaseModel):
    providers: list[Provider] = None
    start_date: date = None
    end_date: date = None


@router.post("/sync")
async def sync(sync_params: SyncParams):
    if sync_params.providers is None:
        sync_params.providers = list(Provider)
    if sync_params.start_date is None:
        sync_params.start_date = date.today().replace(day=1)
    if sync_params.end_date is None:
        sync_params.end_date = (sync_params.start_date + timedelta(days=31)).replace(day=1)

    logger.info(f"Syncing invoices from {sync_params.start_date} to {sync_params.end_date}")

    for provider in sync_params.providers:
        instance = None

        if provider == Provider.FASTWEB:
            instance = Fastweb(google_credentials)
        elif provider == Provider.FASTEWEB_ENERGIA:
            instance = FastwebEnergia()
        elif provider == Provider.ENI:
            instance = Eni()
        elif provider == Provider.UMBRA_ACQUE:
            instance = UmbraAcque()

        if instance is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown provider")

        try:
            logger.info(f"Syncing invoices from {provider.value}")
            invoces = await instance.get_invoices(sync_params.start_date, sync_params.end_date)
            logger.info(f"Synced {len(invoces)} invoices from {provider.value}")
            for invoce in invoces:
                doc = await instance.download_invoice(invoce)
                await instance.save_invoice(invoce, doc)
                await instance.set_expire_invoice(invoce)
        except Exception as e:
            logger.error(f"Error while syncing with {provider.value}", e)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


app.include_router(router)
