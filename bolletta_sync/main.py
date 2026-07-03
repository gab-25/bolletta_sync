import hashlib
import hmac
import json
import logging
import os
import secrets
import importlib.metadata
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Any, List, Optional

from fastapi import FastAPI, Form, Request, HTTPException, Depends, BackgroundTasks
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, model_validator
from dotenv import load_dotenv

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

BASIC_AUTH_USERNAME = os.getenv("BASIC_AUTH_USERNAME")
BASIC_AUTH_PASSWORD = os.getenv("BASIC_AUTH_PASSWORD")

SESSION_TOKEN: Optional[str] = None
if BASIC_AUTH_USERNAME and BASIC_AUTH_PASSWORD:
    SESSION_TOKEN = hmac.new(
        BASIC_AUTH_PASSWORD.encode(),
        BASIC_AUTH_USERNAME.encode(),
        hashlib.sha256,
    ).hexdigest()

http_basic = HTTPBasic(auto_error=False)

try:
    SYNC_DAYS_OFFSET = int(os.getenv("SYNC_DAYS_OFFSET", "10"))
except ValueError:
    logger.warning("Invalid SYNC_DAYS_OFFSET environment variable. Defaulting to 10 days.")
    SYNC_DAYS_OFFSET = 10


async def get_basic_auth(
    request: Request,
    credentials: Optional[HTTPBasicCredentials] = Depends(http_basic),
):
    """Validate session cookie (browser) or Basic Auth (API/Swagger)."""
    if not BASIC_AUTH_USERNAME or not BASIC_AUTH_PASSWORD:
        return True

    # Cookie auth (browser / web UI)
    cookie_token = request.cookies.get("session")
    if cookie_token and secrets.compare_digest(cookie_token, SESSION_TOKEN):
        return True

    # Basic auth fallback (Swagger / API clients)
    if (
        credentials
        and secrets.compare_digest(credentials.username, BASIC_AUTH_USERNAME)
        and secrets.compare_digest(credentials.password, BASIC_AUTH_PASSWORD)
    ):
        return True

    raise HTTPException(status_code=401, detail="Not authenticated")


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: D103
    # Perform Google authentication check on startup
    logger.info("Initializing Google credentials...")
    google_credentials = await get_google_credentials()
    if google_credentials:
        logger.info("Google credentials initialized successfully")
    else:
        logger.warning("Google credentials not found or expired. Please visit /auth/login")

    if not BASIC_AUTH_USERNAME or not BASIC_AUTH_PASSWORD:
        logger.warning("BASIC_AUTH_USERNAME/BASIC_AUTH_PASSWORD not set. Security is disabled.")

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


@app.exception_handler(401)
async def auth_exception_handler(request: Request, exc: HTTPException):
    is_html = "text/html" in request.headers.get("accept", "")
    if is_html:
        return RedirectResponse(url="/login")
    return JSONResponse(status_code=401, content={"detail": exc.detail})


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


@app.get("/", dependencies=[Depends(get_basic_auth)])
async def root(request: Request):
    """
    Return the API status and version.
    """
    google_credentials = await get_google_credentials()
    authenticated = google_credentials is not None

    auth_url = None
    if not authenticated:
        try:
            flow = get_google_flow()
            auth_url, _ = flow.authorization_url(
                access_type="offline", include_granted_scopes="true", prompt="consent"
            )
        except Exception as e:
            logger.warning(f"Could not generate auth URL: {e}")

    last_sync = None
    if os.path.exists(last_sync_file):
        try:
            with open(last_sync_file, "r") as f:
                last_sync = json.load(f)
        except Exception as e:
            logger.error(f"Failed to read last sync file: {e}")

    # Handle HTML requests for the UI
    accept = request.headers.get("accept", "")
    security_enabled = bool(BASIC_AUTH_USERNAME and BASIC_AUTH_PASSWORD)

    if "text/html" in accept:
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "authenticated": authenticated,
                "auth_url": auth_url,
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


@app.get("/login", include_in_schema=False)
async def login_page(request: Request, error: bool = False):
    """Serve the login page. Redirect to / if already authenticated."""
    if BASIC_AUTH_USERNAME and BASIC_AUTH_PASSWORD:
        cookie_token = request.cookies.get("session")
        if cookie_token and secrets.compare_digest(cookie_token, SESSION_TOKEN):
            return RedirectResponse(url="/")
    return templates.TemplateResponse(request, "login.html", {"error": error})


@app.post("/login", include_in_schema=False)
async def login(
    username: str = Form(...),
    password: str = Form(...),
):
    """Validate credentials and set session cookie."""
    if (
        BASIC_AUTH_USERNAME
        and BASIC_AUTH_PASSWORD
        and secrets.compare_digest(username, BASIC_AUTH_USERNAME)
        and secrets.compare_digest(password, BASIC_AUTH_PASSWORD)
    ):
        resp = RedirectResponse(url="/", status_code=303)
        resp.set_cookie("session", SESSION_TOKEN, httponly=True, samesite="lax")
        return resp
    return RedirectResponse(url="/login?error=1", status_code=303)


@app.post("/logout", include_in_schema=False)
async def logout():
    """Clear session cookie and redirect to login."""
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie("session")
    return resp



class TokenRequest(BaseModel):
    code: str


@app.post("/auth/token", dependencies=[Depends(get_basic_auth)])
async def auth_token(body: TokenRequest):
    """
    Exchanges the authorization code for tokens and saves them.
    The code is the value of the 'code' query parameter from the redirect URL
    (http://localhost/?code=...) after authorizing on Google.
    """
    try:
        flow = get_google_flow()
        flow.fetch_token(code=body.code)
    except Exception as e:
        logger.error(f"Failed to exchange auth code: {e}")
        raise HTTPException(status_code=400, detail="Invalid or expired authorization code")

    credentials = flow.credentials
    with open(google_token_file, "w") as token:
        token.write(credentials.to_json())

    logger.info("Google credentials successfully obtained and saved")

    return {"message": "Authentication successful! You can now use the /sync endpoint."}


@app.get("/providers", dependencies=[Depends(get_basic_auth)])
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


@app.post("/sync", response_model=SyncResponse, dependencies=[Depends(get_basic_auth)])
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
