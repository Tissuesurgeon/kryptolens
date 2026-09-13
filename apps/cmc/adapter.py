from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger("kryptolens.cmc")

BASE_URL = "https://pro-api.coinmarketcap.com"


class CMCError(Exception):
    def __init__(self, message: str, status_code: int | None = None, payload: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


@dataclass
class CMCCall:
    endpoint: str
    params: dict
    status_code: int
    credit_count: int | None
    payload: dict
    elapsed_ms: int
    error: str = ""
    fields_used: list[str] = field(default_factory=list)


class CMCAdapter:
    def __init__(self, api_key: str | None = None, client: httpx.Client | None = None):
        self.api_key = api_key if api_key is not None else os.getenv("CMC_API_KEY", "")
        self.client = client or httpx.Client(timeout=20.0)
        self._cache: dict[str, tuple[float, CMCCall]] = {}

    def close(self) -> None:
        self.client.close()

    def get_listings(self, start: int = 1, limit: int = 100, convert: str = "USD") -> CMCCall:
        return self._get(
            "/v3/cryptocurrency/listings/latest",
            {"start": start, "limit": limit, "convert": convert},
            fields=["price", "percent_change_24h", "volume_24h", "volume_change_24h", "market_cap", "cmc_rank"],
        )

    def get_quotes(self, symbols: list[str], convert: str = "USD") -> CMCCall:
        return self._get(
            "/v3/cryptocurrency/quotes/latest",
            {"symbol": ",".join(symbols), "convert": convert},
            fields=["price", "percent_change_24h", "volume_24h", "volume_change_24h", "market_cap", "cmc_rank"],
        )

    def get_global_metrics(self, convert: str = "USD") -> CMCCall:
        return self._get("/v1/global-metrics/quotes/latest", {"convert": convert}, fields=["quote"])

    def get_fear_greed(self) -> CMCCall:
        return self._get(
            "/v3/fear-and-greed/latest",
            {},
            fields=["value", "value_classification"],
        )

    def _get(self, endpoint: str, params: dict, fields: list[str]) -> CMCCall:
        cache_key = f"{endpoint}:{sorted(params.items())}"
        cached = self._cache.get(cache_key)
        if cached and time.time() - cached[0] < 60:
            return cached[1]
        if not self.api_key:
            raise CMCError("CMC_API_KEY is not configured")

        started = time.time()
        try:
            response = self.client.get(
                f"{BASE_URL}{endpoint}",
                params=params,
                headers={
                    "Accept": "application/json",
                    "X-CMC_PRO_API_KEY": self.api_key,
                },
            )
        except httpx.TimeoutException as exc:
            raise CMCError("CMC request timed out") from exc
        except httpx.HTTPError as exc:
            raise CMCError(f"CMC request failed: {exc}") from exc

        elapsed = int((time.time() - started) * 1000)
        payload: dict = {}
        try:
            payload = response.json()
        except ValueError:
            payload = {"raw": response.text[:2000]}

        status = payload.get("status") or {}
        credit = status.get("credit_count")
        error = status.get("error_message") or ""
        logger.info(
            "cmc_request endpoint=%s status=%s credits=%s elapsed_ms=%s",
            endpoint,
            response.status_code,
            credit,
            elapsed,
        )

        call = CMCCall(
            endpoint=endpoint,
            params=params,
            status_code=response.status_code,
            credit_count=credit,
            payload=payload,
            elapsed_ms=elapsed,
            error=error,
            fields_used=fields,
        )
        if response.status_code == 429:
            raise CMCError("CMC rate limit", status_code=429, payload=payload)
        if response.status_code >= 400:
            raise CMCError(error or f"CMC HTTP {response.status_code}", status_code=response.status_code, payload=payload)
        self._cache[cache_key] = (time.time(), call)
        return call
