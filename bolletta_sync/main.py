import logging
import os
import importlib.metadata
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator
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
    app.state.google_credentials = await get_google_credentials()
    logger.info("Google credentials initialized successfully")
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

    providers: List[Provider] = Field(
        default_factory=lambda: list(Provider),
        description="List of providers to sync. Defaults to all providers.",
    )
    start_date: date = Field(
        default_factory=lambda: date.today() - timedelta(days=10),
        description="Start date for syncing (YYYY-MM-DD). Defaults to 10 days ago.",
    )
    end_date: date = Field(
        default_factory=date.today,
        description="End date for syncing (YYYY-MM-DD). Defaults to today.",
    )

    @model_validator(mode="after")
    def validate_dates(self) -> "SyncRequest":
        """Validate that start_date is before end_date."""
        if self.start_date > self.end_date:
            raise ValueError("start_date cannot be after end_date")
        return self


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
    # Get credentials from app state
    google_credentials = app.state.google_credentials

    # Run the main sync process synchronously
    await Sync(
        google_credentials=google_credentials,
        providers=request.providers,
        date_range=(request.start_date, request.end_date),
    ).run()

    return SyncResponse(
        message=f"Sync completed for {len(request.providers)} providers from {request.start_date} to {request.end_date}",
        status="success",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
