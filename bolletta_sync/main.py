import logging
import os
import importlib.metadata
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Any, Dict, List

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, model_validator
from dotenv import load_dotenv

from bolletta_sync.sync import Provider, Sync, get_google_credentials, get_google_flow, google_token_file

load_dotenv()

DEV_MODE = os.getenv("DEV_MODE") == "true"

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

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "providers": [p.value for p in Provider],
                    "start_date": (date.today() - timedelta(days=10)).isoformat(),
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
    results: Dict[str, Any]


@app.get("/")
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

    if not google_credentials:
        raise HTTPException(status_code=401, detail="Not authenticated with Google. Please visit /auth/login")

    # Run the main sync process
    results = await Sync(
        google_credentials=google_credentials,
        providers=request.providers,
        date_range=(request.start_date, request.end_date),
    ).run(headless=not DEV_MODE)

    return SyncResponse(
        message=f"Sync completed for {len(request.providers)} providers from {request.start_date} to {request.end_date}",
        status="success",
        results=results,
    )
