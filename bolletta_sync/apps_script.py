import os
from typing import Any, Dict

import httpx


class AppsScriptError(Exception):
    """Raised when the Apps Script web app can't be reached or returns an error."""


class AppsScriptClient:
    """
    Client for the Apps Script web app (see apps_script/Code.gs) that writes
    invoices to Google Drive and payment tasks to Google Tasks.
    """

    def __init__(self, url: str, secret: str, timeout: float = 60.0) -> None:
        self._url = url
        self._secret = secret
        self._timeout = timeout

    @classmethod
    def from_env(cls) -> "AppsScriptClient | None":
        """Build the client from APPS_SCRIPT_URL / APPS_SCRIPT_SECRET. Returns None if either is missing."""
        url = os.getenv("APPS_SCRIPT_URL")
        secret = os.getenv("APPS_SCRIPT_SECRET")
        if not url or not secret:
            return None
        return cls(url, secret)

    async def call(self, action: str, **payload: Any) -> Dict[str, Any]:
        """
        Call an action of the web app and return its result.
        Apps Script answers a POST with a 302 to script.googleusercontent.com,
        so redirects must be followed.
        """
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=self._timeout) as client:
                response = await client.post(self._url, json={"secret": self._secret, "action": action, **payload})
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise AppsScriptError(f"Apps Script {action} request failed: {e}") from e

        try:
            body = response.json()
        except ValueError:
            # Usually a Google login or error page: the deployment isn't accessible to "Anyone"
            raise AppsScriptError(f"Apps Script {action} returned a non-JSON response (check the deployment access)")

        if not body.get("ok"):
            raise AppsScriptError(f"Apps Script {action} failed: {body.get('error', 'unknown error')}")

        return body
