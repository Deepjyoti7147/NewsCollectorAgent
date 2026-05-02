"""
watchlist.py — yfinance news collector for the watchlist.

Loops through every ticker in the `watchlist` table, fetches news via
yf.Ticker.get_news(), and stores results in `yf_news`.

Rate-limiting:
  • Minimum 2 minutes between consecutive requests to yfinance
    (configurable via YF_FETCH_DELAY_SECONDS env var, default 120).
"""

import logging
import time
from datetime import datetime, timezone
from typing import Optional

import yfinance as yf

logger = logging.getLogger("news_collector.watchlist")


class WatchlistCollector:
    """Fetches yfinance news for each ticker in the DB watchlist."""

    def __init__(self, db_handler, fetch_delay: float = 120.0):
        """
        Parameters
        ----------
        db_handler : DBHandler
            Shared database handler instance.
        fetch_delay : float
            Seconds to wait between consecutive yfinance requests.
            Default 120 s (2 minutes) to stay well within rate limits.
        """
        self._db = db_handler
        self.fetch_delay = fetch_delay

    # ── Public entry point ────────────────────────────────────────────────────

    def run(self) -> dict:
        """
        Iterate over all active watchlist tickers and persist their news.

        Returns a summary dict: {tickers_processed, articles_new, articles_skipped, errors}.
        """
        tickers = self._db.get_watchlist()
        if not tickers:
            logger.info("Watchlist is empty — nothing to fetch")
            return {"tickers_processed": 0, "articles_new": 0, "articles_skipped": 0, "errors": 0}

        logger.info("WatchlistCollector: processing %d ticker(s)", len(tickers))

        total_new = total_skipped = total_errors = 0

        for idx, ticker in enumerate(tickers):
            symbol = ticker["symbol"]
            try:
                news_items = self._fetch_news(symbol)
                new, skipped = self._db.save_yf_news(symbol, news_items)
                total_new += new
                total_skipped += skipped
                logger.info(
                    "[%d/%d] %s — fetched=%d new=%d skipped=%d",
                    idx + 1, len(tickers), symbol, len(news_items), new, skipped,
                )
            except Exception as exc:
                logger.error("Error fetching news for %s: %s", symbol, exc)
                total_errors += 1

            # Politeness delay between requests (skip after last ticker)
            if idx < len(tickers) - 1:
                logger.debug("Sleeping %.0f s before next ticker …", self.fetch_delay)
                time.sleep(self.fetch_delay)

        summary = {
            "tickers_processed": len(tickers),
            "articles_new": total_new,
            "articles_skipped": total_skipped,
            "errors": total_errors,
        }
        logger.info("WatchlistCollector done: %s", summary)
        return summary

    # ── Private helpers ───────────────────────────────────────────────────────

    def _fetch_news(self, symbol: str) -> list[dict]:
        """Call yfinance and return raw news items for *symbol*."""
        logger.debug("Fetching yfinance news for %s …", symbol)
        ticker = yf.Ticker(symbol)
        news = ticker.get_news()
        logger.debug("yfinance returned %d item(s) for %s", len(news), symbol)
        return news

    @staticmethod
    def parse_article(symbol: str, item: dict) -> Optional[dict]:
        """
        Extract the fields we care about from a raw yfinance news dict.

        Stored fields
        -------------
        symbol          — watchlist ticker
        news_id         — Yahoo Finance article UUID (dedup key)
        content_type    — e.g. STORY
        title
        summary
        pub_date        — ISO-8601 string → TIMESTAMPTZ
        provider_name   — e.g. "Simply Wall St."
        provider_url
        article_url     — canonical Yahoo Finance link
        thumbnail_url   — original thumbnail (may be None)
        """
        try:
            content = item.get("content", {})
            if not content:
                return None

            news_id = content.get("id") or item.get("id")
            title = content.get("title", "").strip()
            if not news_id or not title:
                return None

            # Provider
            provider = content.get("provider", {}) or {}
            provider_name = provider.get("displayName", "")
            provider_url = provider.get("url", "")

            # URL — prefer clickThroughUrl, fall back to canonicalUrl
            click = content.get("clickThroughUrl") or content.get("canonicalUrl") or {}
            article_url = click.get("url", "")

            # Thumbnail
            thumb = content.get("thumbnail") or {}
            thumbnail_url = thumb.get("originalUrl") or None

            # pub_date — parse from ISO string if present
            pub_date_str = content.get("pubDate") or content.get("displayTime")
            pub_date: Optional[datetime] = None
            if pub_date_str:
                try:
                    pub_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
                except ValueError:
                    pub_date = None

            return {
                "symbol": symbol.upper(),
                "news_id": news_id,
                "content_type": content.get("contentType", "STORY"),
                "title": title,
                "summary": content.get("summary", ""),
                "pub_date": pub_date,
                "provider_name": provider_name,
                "provider_url": provider_url,
                "article_url": article_url,
                "thumbnail_url": thumbnail_url,
            }
        except Exception as exc:
            logger.warning("Failed to parse news item: %s | item=%s", exc, item)
            return None
