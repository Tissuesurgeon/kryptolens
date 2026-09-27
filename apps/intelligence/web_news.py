"""Public CoinMarketCap headlines. The paid content API is not used."""

from __future__ import annotations

import json
import os
import re

HEADLINES_URL = "https://coinmarketcap.com/headlines/news/"
MAX_HEADLINES = 6
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)


def fetch_headlines() -> list[dict]:
    """Up to six headlines from the public page. Empty when tests are running or the page fails."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return []
    try:
        import httpx

        response = httpx.get(
            HEADLINES_URL,
            headers={"User-Agent": _USER_AGENT, "Accept": "text/html"},
            timeout=15.0,
            follow_redirects=True,
        )
        response.raise_for_status()
        return parse_headlines_html(response.text)
    except Exception:
        return []


def parse_headlines_html(html: str) -> list[dict]:
    match = _NEXT_DATA.search(html or "")
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    feed = ((data.get("props") or {}).get("pageProps") or {}).get("newsFeed") or []
    kept: list[dict] = []
    seen: set[str] = set()
    for item in feed:
        row = _headline(item)
        if not row or row["link"] in seen:
            continue
        seen.add(row["link"])
        kept.append(row)
        if len(kept) >= MAX_HEADLINES:
            break
    return kept


def headlines_from_content(items: list[dict]) -> list[dict]:
    kept: list[dict] = []
    seen: set[str] = set()
    for item in items or []:
        title = str(item.get("title") or "").strip()
        link = str(item.get("source_url") or item.get("link") or "").strip()
        if not title or title in seen:
            continue
        seen.add(title)
        kept.append(
            {
                "title": title,
                "link": link,
                "time": str(item.get("released_at") or item.get("time") or ""),
                "source_name": str(item.get("source_name") or "CoinMarketCap"),
            }
        )
        if len(kept) >= MAX_HEADLINES:
            break
    return kept


def headlines_as_news_items(headlines: list[dict]) -> list[dict]:
    return [
        {
            "title": item.get("title") or "",
            "source_name": item.get("source_name") or "CoinMarketCap",
            "source_url": item.get("link") or "",
            "released_at": item.get("time") or "",
            "assets": [],
        }
        for item in headlines
        if item.get("title")
    ]


def _headline(item) -> dict | None:
    if not isinstance(item, dict):
        return None
    meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
    title = str(meta.get("title") or "").strip()
    link = str(meta.get("sourceUrl") or "").strip()
    if not title or not link.startswith("http"):
        return None
    return {
        "title": title,
        "link": link,
        "time": str(meta.get("releasedAt") or item.get("createdAt") or ""),
        "source_name": str(meta.get("sourceName") or "CoinMarketCap"),
    }
