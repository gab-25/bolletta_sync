import logging
import os
import importlib.metadata
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from bolletta_sync.sync import Provider, Sync, get_google_credentials

load_dotenv()

DEV_MODE = os.getenv("DEV_MODE") == "true"

# Logging Configuration
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] - %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: D103
    # Perform Google authentication on startup
    logger.info("Initializing Google credentials...")
    try:
        await get_google_credentials()
        logger.info("Google credentials initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Google credentials: {e}")
    yield


try:
    __version__ = importlib.metadata.version("bolletta-sync")
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

app = FastAPI(
    title="Bolletta Sync API",
    description="Web service to sync invoices from various providers to Google Drive/Tasks",
    version=__version__,
    lifespan=lifespan,
)


class SyncRequest(BaseModel):
    """Sync request model."""

    providers: Optional[List[Provider]] = Field(
        default=None, description="List of providers to sync. If null, all providers will be synced."
    )
    start_date: Optional[date] = Field(
        default=None, description="Start date for syncing (YYYY-MM-DD). Defaults to 10 days ago."
    )
    end_date: Optional[date] = Field(default=None, description="End date for syncing (YYYY-MM-DD). Defaults to today.")


class SyncResponse(BaseModel):
    """Sync response model."""

    message: str
    status: str


@app.get("/")
async def root():
    """
    Return the API status and version.
    """
    return {"message": "Bolletta Sync API is running", "version": app.version}


@app.get("/providers")
async def get_providers():
    """
    Return the list of available providers.
    """
    return {"providers": [p.value for p in Provider]}


@app.post("/sync", response_model=SyncResponse)
async def trigger_sync(request: SyncRequest):
    """
    Triggers the synchronization process and waits for it to finish.
    """
    start_date = request.start_date if request.start_date else date.today() - timedelta(days=10)
    end_date = request.end_date if request.end_date else date.today()
    providers = request.providers if request.providers else list(Provider)

    # Basic validation
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date cannot be after end_date")

    # Get credentials for this sync run
    try:
        google_credentials = await get_google_credentials()
    except Exception as e:
        logger.error(f"Authentication error during sync trigger: {e}")
        raise HTTPException(status_code=500, detail="Could not retrieve Google credentials")

    # Run the main sync process synchronously
    await Sync(
        google_credentials=google_credentials,
        providers=providers,
        date_range=(start_date, end_date),
    ).run()

    return SyncResponse(
        message=f"Sync completed for {len(providers)} providers from {start_date} to {end_date}", status="success"
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
