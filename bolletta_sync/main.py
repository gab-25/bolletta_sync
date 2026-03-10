import logging
import os
import httpx
import importlib.metadata
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Any, List, Optional

from fastapi import FastAPI, Request, HTTPException, Security, Depends, BackgroundTasks
from fastapi.security.api_key import APIKeyHeader
from fastapi.responses import RedirectResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, model_validator
from dotenv import load_dotenv

from bolletta_sync.sync import Provider, Sync, get_google_credentials, get_google_flow, google_token_file

load_dotenv()

DEV_MODE = os.getenv("DEV_MODE") == "true"
API_KEY = os.getenv("API_KEY")
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


async def get_api_key(api_key_header: str = Security(api_key_header)):
    """Validate the API key from the header."""
    if not API_KEY:
        # If API_KEY is not set in environment, security is disabled
        return api_key_header
    if api_key_header == API_KEY:
        return api_key_header
    raise HTTPException(
        status_code=401,
        detail="Could not validate credentials",
    )


# Logging Configuration
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] - %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: D103
    # Perform Google authentication check on startup
    logger.info("Initializing Google credentials...")
    app.state.google_credentials = await get_google_credentials()
    if app.state.google_credentials:
        logger.info("Google credentials initialized successfully")
    else:
        logger.warning("Google credentials not found or expired. Please visit /auth/login")

    if not API_KEY:
        logger.warning("API_KEY not set in environment variables. Security is disabled.")

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
    webhook_url: Optional[str] = Field(
        default=None,
        description="Optional webhook URL to notify when sync completes.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "providers": [p.value for p in Provider],
                    "start_date": (date.today() - timedelta(days=10)).isoformat(),
                    "end_date": date.today().isoformat(),
                    "webhook_url": "https://example.com/webhook",
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
async def root():
    """
    Return the API status and version.
    """
    authenticated = app.state.google_credentials is not None
    return {"message": "Bolletta Sync API is running", "version": app.version, "authenticated": authenticated}


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

    app.state.google_credentials = credentials
    logger.info("Google credentials successfully obtained and saved")

    return {"message": "Authentication successful! You can now use the /sync endpoint."}


@app.get("/providers", dependencies=[Depends(get_api_key)])
async def get_providers():
    """
    Return the list of available providers.
    """
    return {"providers": [p.value for p in Provider]}


async def run_sync_task(
    google_credentials: Any,
    providers: List[Provider],
    start_date: date,
    end_date: date,
    webhook_url: Optional[str] = None,
):
    """Background task to run the sync process."""
    results = None
    status = None
    error_message = None

    try:
        results = await Sync(
            google_credentials=google_credentials,
            providers=providers,
            date_range=(start_date, end_date),
        ).run(headless=not DEV_MODE)
        status = "success" if all(item["status"] == "success" for item in results.values()) else "error"
        print(status)
        logger.info(f"Background sync completed for {len(providers)} providers")
    except Exception as e:
        status = "error"
        error_message = str(e)
        logger.error(f"Background sync failed: {e}")

    if webhook_url:
        try:
            async with httpx.AsyncClient() as client:
                payload = {
                    "status": status,
                    "providers": [p.value for p in providers],
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                }
                if results:
                    payload["results"] = results
                if error_message:
                    payload["error"] = error_message

                await client.post(webhook_url, json=jsonable_encoder(payload))
                logger.info(f"Webhook notification sent to {webhook_url}")
        except Exception as e:
            logger.error(f"Failed to send webhook notification: {e}")


@app.post("/sync", response_model=SyncResponse, dependencies=[Depends(get_api_key)])
async def trigger_sync(request: SyncRequest, background_tasks: BackgroundTasks):
    """
    Triggers the synchronization process in the background.
    """
    # Get credentials from app state
    google_credentials = app.state.google_credentials

    if not google_credentials:
        raise HTTPException(status_code=401, detail="Not authenticated with Google. Please visit /auth/login")

    # Add to background tasks
    background_tasks.add_task(
        run_sync_task,
        google_credentials,
        request.providers,
        request.start_date,
        request.end_date,
        request.webhook_url,
    )

    return SyncResponse(
        message=f"Sync process started for {len(request.providers)} providers from {request.start_date} to {request.end_date}",
        status="accepted",
    )
