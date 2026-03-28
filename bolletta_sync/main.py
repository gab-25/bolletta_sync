import json
import logging
import os
import importlib.metadata
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Any, List

from fastapi import FastAPI, Request, HTTPException, Security, Depends, BackgroundTasks
from fastapi.security.api_key import APIKeyHeader
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, model_validator
from dotenv import load_dotenv

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from bolletta_sync.sync import (
    Provider,
    Sync,
    get_google_credentials,
    get_google_flow,
    google_token_file,
    last_sync_file,
)

load_dotenv()

DEV_MODE = os.getenv("DEV_MODE") == "true"

# Logging Configuration
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] - %(message)s")
logger = logging.getLogger(__name__)

API_KEY = os.getenv("API_KEY")
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

SYNC_SCHEDULE = os.getenv("SYNC_SCHEDULE")

try:
    SYNC_DAYS_OFFSET = int(os.getenv("SYNC_DAYS_OFFSET", "10"))
except ValueError:
    logger.warning("Invalid SYNC_DAYS_OFFSET environment variable. Defaulting to 10 days.")
    SYNC_DAYS_OFFSET = 10


async def get_api_key(request: Request, api_key_header: str = Security(api_key_header)):
    """Validate the API key from the header."""
    # Allow initial browser requests for the UI to show the password prompt
    if "text/html" in request.headers.get("accept", "") and "hx-request" not in request.headers:
        return api_key_header

    if not API_KEY:
        # If API_KEY is not set in environment, security is disabled
        return api_key_header
    if api_key_header == API_KEY:
        return api_key_header
    raise HTTPException(
        status_code=401,
        detail="Could not validate credentials",
    )


async def scheduled_sync(app: FastAPI):
    """
    Run the sync process for all providers.
    """
    logger.info("Starting scheduled sync...")
    google_credentials = await get_google_credentials()

    if not google_credentials:
        logger.error("Scheduled sync failed: Not authenticated with Google")
        return

    # Use today - SYNC_DAYS_OFFSET as default range
    start_date = date.today() - timedelta(days=SYNC_DAYS_OFFSET)
    end_date = date.today()

    try:
        await Sync(
            google_credentials=google_credentials,
            providers=list(Provider),
            date_range=(start_date, end_date),
        ).run(headless=not DEV_MODE)
        logger.info("Scheduled sync completed successfully")
    except Exception as e:
        logger.error(f"Scheduled sync failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: D103
    # Perform Google authentication check on startup
    logger.info("Initializing Google credentials...")
    google_credentials = await get_google_credentials()
    if google_credentials:
        logger.info("Google credentials initialized successfully")
    else:
        logger.warning("Google credentials not found or expired. Please visit /auth/login")

    if not API_KEY:
        logger.warning("API_KEY not set in environment variables. Security is disabled.")

    # Setup Scheduler
    scheduler = None
    if SYNC_SCHEDULE:
        scheduler = AsyncIOScheduler()
        trigger = CronTrigger.from_crontab(SYNC_SCHEDULE)
        scheduler.add_job(
            scheduled_sync,
            trigger,
            args=[app],
            id="job_sync",
            name=f"Job sync (schedule: {SYNC_SCHEDULE})",
            replace_existing=True,
        )
        scheduler.start()
        logger.info(f"Scheduler started with schedule: {SYNC_SCHEDULE}")
    else:
        logger.warning("SYNC_SCHEDULE not set in environment variables. Scheduler not started.")

    yield

    if scheduler:
        scheduler.shutdown()
        logger.info("Scheduler shut down")


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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


class SyncRequest(BaseModel):
    """Sync request model."""

    providers: List[Provider] = Field(
        default_factory=lambda: list(Provider),
        description="List of providers to sync. Defaults to all providers.",
    )
    start_date: date = Field(
        default_factory=lambda: date.today() - timedelta(days=SYNC_DAYS_OFFSET),
        description=f"Start date for syncing (YYYY-MM-DD). Defaults to {SYNC_DAYS_OFFSET} days ago.",
    )
    end_date: date = Field(
        default_factory=date.today,
        description="End date for syncing (YYYY-MM-DD). Defaults to today.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "providers": [p.value for p in Provider],
                    "start_date": (date.today() - timedelta(days=SYNC_DAYS_OFFSET)).isoformat(),
                    "end_date": date.today().isoformat(),
                }
            ]
        }
    }

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


@app.get("/", dependencies=[Depends(get_api_key)])
async def root(request: Request):
    """
    Return the API status and version.
    """
    google_credentials = await get_google_credentials()
    authenticated = google_credentials is not None

    last_sync = None
    if os.path.exists(last_sync_file):
        try:
            with open(last_sync_file, "r") as f:
                last_sync = json.load(f)
        except Exception as e:
            logger.error(f"Failed to read last sync file: {e}")

    # Handle HTML requests for the UI
    accept = request.headers.get("accept", "")
    security_enabled = bool(API_KEY)

    if "text/html" in accept and "hx-request" not in request.headers:
        return templates.TemplateResponse(
            request,
            "index.html",
            {"version": app.version, "security_enabled": security_enabled},
        )

    # Handle HTMX fragment requests
    if "hx-request" in request.headers:
        return templates.TemplateResponse(
            request,
            "status_fragment.html",
            {
                "authenticated": authenticated,
                "last_sync": last_sync,
                "version": app.version,
                "security_enabled": security_enabled,
            },
        )

    return {
        "message": "Bolletta Sync API is running",
        "version": app.version,
        "authenticated": authenticated,
        "last_sync": last_sync,
    }


@app.get("/auth/login")
async def auth_login(request: Request):
    """
    Initializes the Google OAuth2 flow and redirects to Google's authorization page.
    """
    redirect_uri = str(request.url_for("auth_callback"))

    if "localhost" in redirect_uri:
        redirect_uri = redirect_uri.replace("https://", "http://")

    if not DEV_MODE and "localhost" not in redirect_uri and redirect_uri.startswith("http://"):
        redirect_uri = redirect_uri.replace("http://", "https://", 1)

    flow = get_google_flow(redirect_uri)
    authorization_url, state = flow.authorization_url(
        access_type="offline", include_granted_scopes="true", prompt="consent"
    )
    return RedirectResponse(authorization_url)


@app.get("/auth/callback")
async def auth_callback(request: Request, code: str):
    """
    Callback for Google OAuth2. Exchanges the code for tokens.
    """
    redirect_uri = str(request.url_for("auth_callback"))

    if "localhost" in redirect_uri:
        redirect_uri = redirect_uri.replace("https://", "http://")

    if not DEV_MODE and "localhost" not in redirect_uri and redirect_uri.startswith("http://"):
        redirect_uri = redirect_uri.replace("http://", "https://", 1)

    flow = get_google_flow(redirect_uri)
    flow.fetch_token(code=code)

    credentials = flow.credentials
    with open(google_token_file, "w") as token:
        token.write(credentials.to_json())

    logger.info("Google credentials successfully obtained and saved")

    return {"message": "Authentication successful! You can now use the /sync endpoint."}


@app.get("/providers", dependencies=[Depends(get_api_key)])
async def get_providers():
    """
    Return the list of available providers.
    """
    return {"providers": [p.value for p in Provider]}


async def run_sync_task(
    providers: List[Provider],
    start_date: date,
    end_date: date,
):
    """Background task to run the sync process."""
    google_credentials = await get_google_credentials()
    if not google_credentials:
        logger.error("Background sync failed: Not authenticated with Google")
        return

    try:
        await Sync(
            google_credentials=google_credentials,
            providers=providers,
            date_range=(start_date, end_date),
        ).run(headless=not DEV_MODE)
        logger.info(f"Background sync completed for {len(providers)} providers")
    except Exception as e:
        logger.error(f"Background sync failed: {e}")


@app.post("/sync", response_model=SyncResponse, dependencies=[Depends(get_api_key)])
async def trigger_sync(request: SyncRequest, background_tasks: BackgroundTasks):
    """
    Triggers the synchronization process in the background.
    """
    # Refresh and get credentials
    google_credentials = await get_google_credentials()

    if not google_credentials:
        raise HTTPException(status_code=401, detail="Not authenticated with Google. Please visit /auth/login")

    # Add to background tasks
    background_tasks.add_task(
        run_sync_task,
        request.providers,
        request.start_date,
        request.end_date,
    )

    return SyncResponse(
        message=f"Sync process started for {len(request.providers)} providers from {request.start_date} to {request.end_date}",
        status="accepted",
    )
