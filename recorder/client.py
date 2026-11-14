"""Polite HTTP client for the public, unauthenticated Polymarket US gateway.

No keys, no auth headers, no order endpoints. GET only.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://gateway.polymarket.us"
USER_AGENT = "polymarket-orderbook-recorder/0.1 (+https://github.com/rgoudie36-crypto/polymarket-orderbook-recorder)"

# Documented public limit is 25 req/s per IP. We stay far below it.
DEFAULT_MIN_INTERVAL = 0.1  # seconds between request starts (<= 10 req/s)
RETRY_STATUSES = {429, 500, 502, 503, 504}


class HttpError(Exception):
    def __init__(self, status, url):
        super().__init__(f"HTTP {status} for {url}")
        self.status = status
        self.url = url


def _default_fetch(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read() if e.fp else b""


class Client:
    """GET-only JSON client with pacing and backoff.

    `fetch`, `clock` and `sleep` are injectable so tests never touch the network.
    """

    def __init__(self, base_url=BASE_URL, min_interval=DEFAULT_MIN_INTERVAL, max_retries=4,
                 timeout=20, fetch=None, clock=time.monotonic, sleep=time.sleep):
        self.base_url = base_url.rstrip("/")
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.timeout = timeout
        self._fetch = fetch or _default_fetch
        self._clock = clock
        self._sleep = sleep
        self._last_start = None
        self.requests_made = 0
        self.retries = 0
        self.bytes_received = 0

    def _pace(self):
        if self._last_start is not None:
            wait = self.min_interval - (self._clock() - self._last_start)
            if wait > 0:
                self._sleep(wait)
        self._last_start = self._clock()

    def get_json(self, path, params=None):
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params, doseq=True)
        attempt = 0
        while True:
            self._pace()
            self.requests_made += 1
            try:
                status, body = self._fetch(url, self.timeout)
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                status, body = None, b""
            if status == 200:
                self.bytes_received += len(body)
                return json.loads(body)
            retryable = status is None or status in RETRY_STATUSES
            if not retryable or attempt >= self.max_retries:
                raise HttpError(status, url)
            # Docs: on 429 stop, wait >= 1 s, then back off exponentially.
            self._sleep(min(30.0, 1.0 * (2 ** attempt)))
            attempt += 1
            self.retries += 1
