import asyncio
import copy
import logging
import sys
import time

import requests

from src.utils.log_setup import logger


class DummyResponse:
    def __init__(self, text="", status_code=200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"Status code: {self.status_code}")


def sanitize_kwargs(data):
    """Recursively redact sensitive values in kwargs for safe logging."""
    if isinstance(data, dict):
        redacted = {}
        for key, value in data.items():
            if (
                key.lower()
                in {
                    "username",
                    "password",
                    "x-api-key",
                    "apikey",
                    "cookies",
                    "authorization",
                }
                and value
            ):
                redacted[key] = "[**redacted**]"
            else:
                redacted[key] = sanitize_kwargs(value)
        return redacted
    if isinstance(data, list):
        return [sanitize_kwargs(item) for item in data]
    return data


async def make_request(
    method: str,
    endpoint: str,
    settings,
    timeout: float | None = None,
    *,
    log_error=True,
    **kwargs,
) -> requests.Response:
    """
    A utility function to make HTTP requests (GET, POST, DELETE, PUT).
    """
    ignore_test_run = kwargs.pop("ignore_test_run", False)
    request_timeout = timeout
    if request_timeout is None:
        request_timeout = getattr(
            getattr(settings, "general", None), "request_timeout", 15
        )

    if settings.general.test_run and not ignore_test_run:
        if method.lower() in ("put", "post", "delete"):
            if logger.isEnabledFor(logging.DEBUG):
                sanitized_kwargs = sanitize_kwargs(copy.deepcopy(kwargs))
                logger.debug(
                    f"common.py/make_request: [Test Run] Simulating {method.upper()} request to {endpoint} with kwargs={sanitized_kwargs}"
                )
            return DummyResponse(text="Test run - no actual call made", status_code=200)

    try:
        if logger.isEnabledFor(logging.DEBUG):
            sanitized_kwargs = sanitize_kwargs(copy.deepcopy(kwargs))
            logger.debug(
                f"common.py/make_request: Making {method.upper()} request to {endpoint} with kwargs={sanitized_kwargs}"
            )

        # Make the request using the method passed (get, post, etc.)
        response = await asyncio.to_thread(
            getattr(requests, method.lower()),
            endpoint,
            **kwargs,
            verify=settings.general.ssl_verification,
            timeout=request_timeout,
        )
        response.raise_for_status()
        return response
    except requests.exceptions.HTTPError as http_err:
        if log_error:
            logger.error(f"HTTP error occurred: {http_err}", exc_info=True)
        raise

    except Exception as err:
        if log_error:
            logger.error(f"Other error occurred: {err}", exc_info=True)
        raise


def wait_and_exit(seconds=30):
    logger.info(f"Decluttarr will wait for {seconds} seconds and then exit.")
    # Raise SystemExit instead of blocking with time.sleep(), so the async
    # event loop (and web UI) stays responsive. main_with_restart() catches
    # SystemExit and handles the retry delay.
    sys.exit(1)


def is_definitive_setup_error(exc):
    """Definitive = a configuration error that cannot heal without user action."""
    for candidate in (exc, exc.__cause__):
        if getattr(candidate, "definitive", False):
            return True
        if isinstance(candidate, requests.exceptions.HTTPError):
            response = getattr(candidate, "response", None)
            if response is not None and response.status_code in (401, 403):
                return True
    return False


def extract_json_from_response(response, key: str | None = None):
    try:
        data = response.json()
    except ValueError as e:
        raise ValueError("Response content is not valid JSON") from e

    if key is None:
        return data

    if not isinstance(data, dict):
        raise ValueError("Response JSON is not a dictionary, cannot extract key")

    if key not in data:
        raise ValueError(f"Key '{key}' not found in API response")

    return data[key]
