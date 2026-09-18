from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

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


def parse_as_of(value) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        parsed = datetime.strptime(text[:10], "%Y-%m-%d")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class CMCAdapter:
    def __init__(
        self,
        api_key: str | None = None,
        client: httpx.Client | None = None,
        as_of=None,
    ):
        self.api_key = api_key if api_key is not None else os.getenv("CMC_API_KEY", "")
        self.client = client or httpx.Client(timeout=20.0)
        self.as_of = parse_as_of(as_of)
        self._cache: dict[str, tuple[float, CMCCall]] = {}

    def close(self) -> None:
        self.client.close()

    def get_listings(self, start: int = 1, limit: int = 100, convert: str = "USD") -> CMCCall:
        if self.as_of:
            return self.get_listings_historical(self.as_of.date(), limit=limit, convert=convert)
        return self._get(
            "/v3/cryptocurrency/listings/latest",
            {"start": start, "limit": limit, "convert": convert},
            fields=["price", "percent_change_24h", "volume_24h", "volume_change_24h", "market_cap", "cmc_rank"],
        )

    def get_quotes(self, symbols: list[str], convert: str = "USD") -> CMCCall:
        if self.as_of:
            return self.get_quotes_historical(symbols, self.as_of, convert=convert)
        return self._get(
            "/v3/cryptocurrency/quotes/latest",
            {"symbol": ",".join(symbols), "convert": convert},
            fields=["price", "percent_change_24h", "volume_24h", "volume_change_24h", "market_cap", "cmc_rank"],
        )

    def get_quotes_historical(self, symbols: list[str], as_of, convert: str = "USD") -> CMCCall:
        moment = parse_as_of(as_of)
        if moment is None:
            raise CMCError("Historical quotes require an as_of date")
        start = moment.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        call = self._get(
            "/v2/cryptocurrency/quotes/historical",
            {
                "symbol": ",".join(symbols),
                "time_start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "time_end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "interval": "hourly",
                "convert": convert,
            },
            fields=["price", "percent_change_24h", "volume_24h", "volume_change_24h", "market_cap", "cmc_rank"],
        )
        from apps.cmc.normalize import flatten_historical_quotes

        call.payload = flatten_historical_quotes(call.payload)
        return call

    def get_listings_historical(self, as_of, limit: int = 100, convert: str = "USD") -> CMCCall:
        moment = parse_as_of(as_of)
        if moment is None:
            raise CMCError("Historical listings require an as_of date")
        return self._get(
            "/v1/cryptocurrency/listings/historical",
            {"date": moment.date().isoformat(), "limit": limit, "convert": convert},
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

    def get_content_latest(
        self,
        start: int = 1,
        limit: int = 20,
        symbols: list[str] | None = None,
        news_type: str = "news",
        language: str = "en",
    ) -> CMCCall:
        """CMC News/Headlines and Alexandria articles. GET /v1/content/latest."""
        params: dict = {
            "start": start,
            "limit": max(1, min(int(limit), 200)),
            "news_type": news_type or "news",
            "language": language or "en",
        }
        cleaned = [item.strip().upper() for item in (symbols or []) if item and item.strip()]
        if cleaned:
            params["symbol"] = ",".join(cleaned)
        return self._get(
            "/v1/content/latest",
            params,
            fields=["title", "subtitle", "source_name", "source_url", "type", "assets", "released_at"],
        )

    def get_quotes_historical_range(self, symbols: list[str], window: str = "30d", convert: str = "USD") -> CMCCall:
        start, end, interval = _window_bounds(window)
        call = self._get(
            "/v2/cryptocurrency/quotes/historical",
            {
                "symbol": ",".join(symbols),
                "time_start": start,
                "time_end": end,
                "interval": interval,
                "convert": convert,
            },
            fields=["price", "percent_change_24h", "volume_24h", "market_cap"],
        )
        from apps.cmc.normalize import flatten_historical_quotes

        call.payload = flatten_historical_quotes(call.payload)
        return call

    def get_ohlcv_historical(self, symbols: list[str], window: str = "30d", convert: str = "USD") -> CMCCall:
        start, end, interval = _window_bounds(window)
        return self._get(
            "/v2/cryptocurrency/ohlcv/historical",
            {
                "symbol": ",".join(symbols),
                "time_start": start,
                "time_end": end,
                "interval": interval,
                "convert": convert,
            },
            fields=["open", "high", "low", "close", "volume"],
        )

    def get_trending_latest(self) -> CMCCall:
        return self._get(
            "/v1/cryptocurrency/trending/latest",
            {"limit": 20},
            fields=["id", "name", "symbol", "cmc_rank"],
        )

    def get_gainers_losers(self) -> CMCCall:
        return self._get(
            "/v1/cryptocurrency/trending/gainers-losers",
            {"limit": 20},
            fields=["id", "name", "symbol", "percent_change_24h"],
        )

    def get_listings_new(self, limit: int = 20) -> CMCCall:
        return self._get(
            "/v1/cryptocurrency/listings/new",
            {"limit": max(1, min(int(limit), 100))},
            fields=["id", "name", "symbol", "date_added"],
        )

    def get_categories(self, limit: int = 50) -> CMCCall:
        return self._get(
            "/v1/cryptocurrency/categories",
            {"limit": max(1, min(int(limit), 200))},
            fields=["id", "name", "market_cap", "volume"],
        )

    def get_category(self, category_id: str, convert: str = "USD") -> CMCCall:
        return self._get(
            "/v1/cryptocurrency/category",
            {"id": category_id, "convert": convert},
            fields=["id", "name", "coins"],
        )

    def get_price_performance_stats(self, symbols: list[str], convert: str = "USD") -> CMCCall:
        return self._get(
            "/v2/cryptocurrency/price-performance-stats/latest",
            {"symbol": ",".join(symbols), "convert": convert},
            fields=["percent_change"],
        )

    def get_altcoin_season(self) -> CMCCall:
        return self._get("/v3/altcoin-season/latest", {}, fields=["value", "value_classification"])

    def get_cmc_index(self, symbol: str = "CMC20") -> CMCCall:
        return self._get(
            "/v3/index/quotes/latest",
            {"symbol": symbol},
            fields=["price", "percent_change_24h"],
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
            message = error or f"CMC HTTP {response.status_code}"
            if response.status_code in {401, 403}:
                message = _plan_message(endpoint)
            raise CMCError(message, status_code=response.status_code, payload=payload)
        self._cache[cache_key] = (time.time(), call)
        return call


def _window_bounds(window: str) -> tuple[str, str, str]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    text = (window or "30d").strip().lower()
    amount = 30
    unit = "d"
    match = None
    for token in (text,):
        digits = "".join(ch for ch in token if ch.isdigit())
        if digits:
            amount = int(digits)
        if "h" in token:
            unit = "h"
        elif "m" in token and "d" not in token:
            unit = "m"
    if unit == "h":
        start = now - timedelta(hours=max(1, amount))
        interval = "hourly"
    elif unit == "m":
        start = now - timedelta(minutes=max(1, amount))
        interval = "hourly"
    else:
        start = now - timedelta(days=max(1, amount))
        interval = "daily"
    return start.strftime("%Y-%m-%dT%H:%M:%SZ"), now.strftime("%Y-%m-%dT%H:%M:%SZ"), interval


def _plan_message(endpoint: str) -> str:
    labels = {
        "/v1/content/latest": "CoinMarketCap Content Latest (News/Headlines) is not available on this API plan.",
        "/v1/cryptocurrency/trending/latest": "Trending latest is not available on this API plan.",
        "/v1/cryptocurrency/trending/gainers-losers": "Gainers and losers are not available on this API plan.",
        "/v1/cryptocurrency/listings/new": "New listings are not available on this API plan.",
        "/v1/cryptocurrency/categories": "Categories are not available on this API plan.",
        "/v1/cryptocurrency/category": "Category detail is not available on this API plan.",
        "/v2/cryptocurrency/quotes/historical": "Historical quotes are not available on this API plan.",
        "/v2/cryptocurrency/ohlcv/historical": "Historical OHLCV is not available on this API plan.",
        "/v2/cryptocurrency/price-performance-stats/latest": "Price performance stats are not available on this API plan.",
        "/v3/altcoin-season/latest": "Altcoin season is not available on this API plan.",
        "/v3/index/quotes/latest": "CMC index is not on this plan.",
    }
    return labels.get(endpoint, f"{endpoint} is not available on this API plan.")
