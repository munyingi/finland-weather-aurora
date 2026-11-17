"""HTTP client with retries. Sources call `client.get(url, params)` and get bytes back,
which lets the demo mode swap in a fake client that serves recorded-format payloads."""

from __future__ import annotations

from typing import Protocol

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import config


class Client(Protocol):
    def get(self, url: str, params: dict | None = None) -> bytes: ...


class HttpClient:
    def __init__(self, timeout: int = config.HTTP_TIMEOUT_S) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        retry = Retry(
            total=5,
            backoff_factor=2,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
            respect_retry_after_header=True,
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.headers["User-Agent"] = config.USER_AGENT

    def get(self, url: str, params: dict | None = None) -> bytes:
        resp = self.session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.content
