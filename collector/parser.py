"""
RSS feed parser for Indian stock market news.
Memory-conscious: streams feed entries one at a time,
never loads full HTML of articles.
"""

import hashlib
import logging
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

import feedparser
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from collector.feeds import RSS_FEEDS, CATEGORY_LABELS

logger = logging.getLogger("news_collector.parser")


def _make_session(timeout: int = 15) -> requests.Session:
    """Session with retry + conservative timeouts."""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=2, pool_maxsize=4)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(
        {
            "User-Agent": (
                "NewsCollectorAgent/1.0 "
                "(Indian Stock Market RSS Aggregator; "
                "+https://github.com/Deepjyoti7147/NewsCollectorAgent)"
            ),
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        }
    )
    return session


def _parse_date(entry) -> Optional[datetime]:
    """Best-effort date parsing from feedparser entry."""
    # feedparser already gives published_parsed (struct_time in UTC)
    if getattr(entry, "published_parsed", None):
        try:
            return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        except Exception:
            pass

    raw = getattr(entry, "published", None) or getattr(entry, "updated", None)
    if raw:
        try:
            return parsedate_to_datetime(raw).astimezone(timezone.utc)
        except Exception:
            pass

    return datetime.now(tz=timezone.utc)


def _content_hash(title: str, link: str) -> str:
    """SHA-256 of normalised title + link — used as dedup key in DB."""
    key = f"{title.strip().lower()}|{link.strip().lower()}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _extract_summary(entry) -> str:
    """Pull the best available summary text (≤ 1000 chars)."""
    for attr in ("summary", "description", "content"):
        val = getattr(entry, attr, None)
        if isinstance(val, list) and val:
            val = val[0].get("value", "")
        if val and isinstance(val, str):
            # Strip HTML tags roughly (avoid heavy libs)
            import re
            val = re.sub(r"<[^>]+>", " ", val)
            val = re.sub(r"\s+", " ", val).strip()
            if len(val) > 20:
                return val[:1000]
    return ""


class FeedParser:
    def __init__(
        self,
        request_delay: float = 1.5,
        timeout: int = 15,
    ):
        self._session = _make_session(timeout=timeout)
        self._timeout = timeout
        self._delay = request_delay  # politeness delay between feeds

    # ── Public API ─────────────────────────────────────────────────────────────

    def fetch_all_feeds(self) -> tuple[list[dict], int]:
        """
        Iterate every configured feed and return (articles, feeds_ok).
        Yields deduplicated articles ready for DB insertion.
        """
        all_articles: list[dict] = []
        seen_hashes: set[str] = set()
        feeds_ok = 0

        for feed_cfg in RSS_FEEDS:
            try:
                articles = self._fetch_feed(feed_cfg, seen_hashes)
                all_articles.extend(articles)
                feeds_ok += 1
            except Exception as exc:
                logger.warning("Feed '%s' failed: %s", feed_cfg["name"], exc)

            # Politeness delay to respect rate limits
            time.sleep(self._delay)

        logger.info(
            "Fetched %d feeds, %d unique articles", feeds_ok, len(all_articles)
        )
        return all_articles, feeds_ok

    # ── Internal ──────────────────────────────────────────────────────────────

    def _fetch_feed(self, feed_cfg: dict, seen_hashes: set) -> list[dict]:
        url = feed_cfg["url"]
        name = feed_cfg["name"]
        category = feed_cfg.get("category", "markets")

        logger.debug("Fetching feed: %s", name)

        # Use requests to download so we control timeouts; feedparser parses str
        try:
            resp = self._session.get(url, timeout=self._timeout)
            resp.raise_for_status()
            raw_xml = resp.text
        except requests.RequestException as exc:
            logger.warning("[%s] HTTP error: %s", name, exc)
            return []

        parsed = feedparser.parse(raw_xml)

        if parsed.bozo and not parsed.entries:
            logger.warning("[%s] feedparser bozo flag (malformed feed)", name)
            return []

        articles = []
        for entry in parsed.entries:
            title = (getattr(entry, "title", "") or "").strip()
            link = (getattr(entry, "link", "") or "").strip()

            if not title or not link:
                continue

            h = _content_hash(title, link)
            if h in seen_hashes:
                continue
            seen_hashes.add(h)

            articles.append(
                {
                    "title": title[:500],
                    "summary": _extract_summary(entry),
                    "link": link[:2000],
                    "published_at": _parse_date(entry),
                    "source_name": name,
                    "category": CATEGORY_LABELS.get(category, category),
                    "content_hash": h,
                    "raw_content": None,  # full content scraping not done to save memory
                }
            )

        logger.info("[%s] %d new entries", name, len(articles))
        return articles

    def close(self):
        self._session.close()
