import logging
import os
from datetime import date
from enum import Enum

from dotenv import load_dotenv
from fastapi import FastAPI, Security, HTTPException, APIRouter
from fastapi.params import Depends
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from starlette import status

from bolletta_sync.providers.fastweb import Fastweb

load_dotenv()

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

app = FastAPI()

api_key_header = APIKeyHeader(name="X-API-Key")


async def validate_api_key(key: str = Security(api_key_header)):
    if key != os.environ.get("API_KEY"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized - API Key is wrong"
        )
    return None


router = APIRouter(dependencies=[Depends(validate_api_key)])


class Provider(Enum):
    FASTWEB = "fastweb"
    FASTEWEB_ENERGIA = "fastweb_energia"
    ENI = "eni"
    UMBRA_ACQUE = "umbra_acque"


class SyncParams(BaseModel):
    providers: list[Provider] = None
    date_start: date = None
    date_end: date = None


@router.post("/sync")
async def sync(sync_params: SyncParams):
    return Fastweb().get_invoices()


app.include_router(router)
