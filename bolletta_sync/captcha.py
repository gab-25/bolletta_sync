import asyncio
import logging
import os
import time
from typing import Any, Optional

from playwright.async_api import Page

logger = logging.getLogger(__name__)

CAPSOLVER_API = "https://api.capsolver.com"

# The widget is injected lazily: it is still missing from the DOM right after the login form
# is filled in and only shows up a few seconds later.
SITE_KEY_TIMEOUT = 30
SOLVE_TIMEOUT = 120
POLL_INTERVAL = 3
REQUEST_TIMEOUT = 30_000


class CapSolverError(Exception):
    pass


_SITE_KEY_SCRIPT = """() => {
    const element = document.querySelector('[data-sitekey]');
    if (element) return element.getAttribute('data-sitekey');

    for (const iframe of document.querySelectorAll('iframe[src*="/recaptcha/"]')) {
        try {
            const key = new URL(iframe.src).searchParams.get('k');
            if (key) return key;
        } catch (e) { }
    }

    return null;
}"""

# The token has to be handed over in three ways because a page can read it back from any of
# them: the form field it is posted from, grecaptcha.getResponse(), and the widget callback.
_APPLY_TOKEN_SCRIPT = """(token) => {
    const result = {textareas: 0, get_response: false, callbacks: 0};

    for (const textarea of document.querySelectorAll(
        'textarea[name="g-recaptcha-response"], #g-recaptcha-response'
    )) {
        textarea.value = token;
        textarea.dispatchEvent(new Event('change', {bubbles: true}));
        result.textareas += 1;
    }

    if (window.grecaptcha) {
        window.grecaptcha.getResponse = () => token;
        result.get_response = true;
    }

    // The callback is nested inside the client object under minified names
    // (clients.0.M.M.callback), so the whole graph has to be walked to find it.
    const seen = new WeakSet();
    const walk = (object, depth) => {
        if (!object || typeof object !== 'object' || depth > 5 || seen.has(object)) return;
        seen.add(object);

        for (const key of Object.keys(object)) {
            let value;
            try { value = object[key]; } catch (e) { continue; }

            if (key === 'callback' && (typeof value === 'function' || typeof value === 'string')) {
                // A widget rendered with grecaptcha.render() keeps the callback as a function,
                // while one declared with data-callback keeps the name of a global.
                const callback = typeof value === 'string'
                    ? value.split('.').reduce((target, part) => (target ? target[part] : undefined), window)
                    : value;

                if (typeof callback === 'function') {
                    try {
                        callback(token);
                        result.callbacks += 1;
                    } catch (e) {
                        result.callback_error = String(e);
                    }
                }
            } else if (value && typeof value === 'object') {
                walk(value, depth + 1);
            }
        }
    };
    walk(window.___grecaptcha_cfg && window.___grecaptcha_cfg.clients, 0);

    return result;
}"""


async def _post(page: Page, path: str, payload: dict) -> dict[str, Any]:
    response = await page.request.post(f"{CAPSOLVER_API}{path}", data=payload, timeout=REQUEST_TIMEOUT)

    try:
        body = await response.json()
    except Exception as e:
        raise CapSolverError(f"{path} returned HTTP {response.status}: {(await response.text())[:200]}") from e

    if body.get("errorId"):
        raise CapSolverError(f"{body.get('errorCode')}: {body.get('errorDescription')}")

    return body


async def _read_site_key(page: Page, timeout: float) -> Optional[str]:
    deadline = time.monotonic() + timeout

    while True:
        site_key = await page.evaluate(_SITE_KEY_SCRIPT)
        if site_key:
            return site_key

        if time.monotonic() >= deadline:
            return None

        await asyncio.sleep(0.5)


async def _wait_for_token(page: Page, api_key: str, task_id: str, timeout: float) -> str:
    deadline = time.monotonic() + timeout

    while True:
        body = await _post(page, "/getTaskResult", {"clientKey": api_key, "taskId": task_id})

        if body.get("status") == "ready":
            return body["solution"]["gRecaptchaResponse"]

        if time.monotonic() >= deadline:
            raise CapSolverError(f"task {task_id} was not solved within {timeout:.0f}s")

        await asyncio.sleep(POLL_INTERVAL)


async def solve_recaptcha_v2(page: Page, *, timeout: float = SOLVE_TIMEOUT) -> Optional[str]:
    """
    Solve the reCAPTCHA v2 widget on the page with CapSolver and return its token.
    Returns None if the page does not show a widget.
    """
    api_key = os.getenv("CAPSOLVER_API_KEY")
    if not api_key:
        raise CapSolverError("CAPSOLVER_API_KEY is not set")

    site_key = await _read_site_key(page, SITE_KEY_TIMEOUT)
    if site_key is None:
        return None

    started = time.monotonic()
    body = await _post(
        page,
        "/createTask",
        {
            "clientKey": api_key,
            "task": {
                "type": "ReCaptchaV2TaskProxyLess",
                "websiteURL": page.url,
                "websiteKey": site_key,
                "isInvisible": False,
            },
        },
    )

    token = await _wait_for_token(page, api_key, body["taskId"], timeout)
    logger.info(f"recaptcha solved in {time.monotonic() - started:.0f}s")

    return token


async def apply_recaptcha_token(page: Page, token: str) -> None:
    """
    Hand a solved reCAPTCHA token over to the page.
    """
    result = await page.evaluate(_APPLY_TOKEN_SCRIPT, token)
    logger.info(f"recaptcha token applied: {result}")

    if not result["textareas"] and not result["callbacks"]:
        raise CapSolverError("the page took the reCAPTCHA token in neither its form field nor a callback")
