"""
PostgreSQL database handler for the NewsCollectorAgent.
Stores and deduplicates news articles; designed for remote DB VM.
Uses connection pooling via psycopg2 + simple retry logic.
"""

import json
import logging
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Optional

import psycopg2
import psycopg2.extras
from psycopg2 import pool

logger = logging.getLogger("news_collector.db")

# ── DDL ─────────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS watchlist (
    id              SERIAL PRIMARY KEY,
    symbol          TEXT UNIQUE NOT NULL,
    added_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS yf_news (
    id              BIGSERIAL PRIMARY KEY,
    symbol          TEXT NOT NULL,
    news_id         TEXT NOT NULL,
    content_type    TEXT,
    title           TEXT NOT NULL,
    summary         TEXT,
    pub_date        TIMESTAMPTZ,
    provider_name   TEXT,
    provider_url    TEXT,
    article_url     TEXT,
    thumbnail_url   TEXT,
    fetched_at      TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT yf_news_id_uq UNIQUE (news_id)
);

CREATE INDEX IF NOT EXISTS idx_yf_news_symbol ON yf_news (symbol);
CREATE INDEX IF NOT EXISTS idx_yf_news_pub_date ON yf_news (pub_date DESC);
CREATE INDEX IF NOT EXISTS idx_yf_news_fetched_at ON yf_news (fetched_at DESC);

CREATE TABLE IF NOT EXISTS news_articles (
    id              BIGSERIAL PRIMARY KEY,
    title           TEXT        NOT NULL,
    summary         TEXT,
    link            TEXT        NOT NULL,
    published_at    TIMESTAMPTZ,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_name     TEXT        NOT NULL,
    category        TEXT        NOT NULL DEFAULT 'markets',
    content_hash    CHAR(64)    NOT NULL,   -- SHA-256 of normalised title+link
    raw_content     TEXT,

    CONSTRAINT news_articles_content_hash_uq UNIQUE (content_hash)
);

CREATE INDEX IF NOT EXISTS idx_news_published_at  ON news_articles (published_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_category      ON news_articles (category);
CREATE INDEX IF NOT EXISTS idx_news_source        ON news_articles (source_name);
CREATE INDEX IF NOT EXISTS idx_news_fetched_at    ON news_articles (fetched_at DESC);

CREATE TABLE IF NOT EXISTS collector_runs (
    id              BIGSERIAL   PRIMARY KEY,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    feeds_fetched   INTEGER     DEFAULT 0,
    articles_new    INTEGER     DEFAULT 0,
    articles_skipped INTEGER    DEFAULT 0,
    error_message   TEXT,
    status          TEXT        NOT NULL DEFAULT 'RUNNING'  -- RUNNING | COMPLETED | FAILED
);
"""


class DBHandler:
    """Thread-safe PostgreSQL handler with a small connection pool."""

    _pool: Optional[pool.ThreadedConnectionPool] = None

    def __init__(self, dsn: str, min_conn: int = 1, max_conn: int = 3):
        self.dsn = dsn
        self.min_conn = min_conn
        self.max_conn = max_conn

    # ── Pool lifecycle ────────────────────────────────────────────────────────

    def connect(self, retries: int = 5, delay: float = 5.0) -> None:
        """Open the connection pool (with retry for cold-start DB)."""
        for attempt in range(1, retries + 1):
            try:
                self._pool = pool.ThreadedConnectionPool(
                    self.min_conn,
                    self.max_conn,
                    dsn=self.dsn,
                    connect_timeout=10,
                )
                logger.info("PostgreSQL pool opened (min=%d, max=%d)", self.min_conn, self.max_conn)
                self._init_schema()
                return
            except psycopg2.OperationalError as exc:
                logger.warning("DB connect attempt %d/%d failed: %s", attempt, retries, exc)
                if attempt < retries:
                    time.sleep(delay)
        raise RuntimeError("Could not connect to PostgreSQL after %d attempts" % retries)

    def close(self) -> None:
        if self._pool:
            self._pool.closeall()
            logger.info("PostgreSQL pool closed")

    @contextmanager
    def _get_conn(self):
        conn = self._pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)

    # ── Schema ────────────────────────────────────────────────────────────────

    def _init_schema(self) -> None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(SCHEMA_SQL)
        logger.info("Schema verified/created")

    # ── Article persistence ────────────────────────────────────────────────────

    def save_articles(self, articles: list[dict]) -> tuple[int, int]:
        """
        Bulk-insert articles; skips duplicates via content_hash.
        Returns (inserted, skipped).
        """
        if not articles:
            return 0, 0

        inserted = skipped = 0

        with self._get_conn() as conn:
            with conn.cursor() as cur:
                for art in articles:
                    try:
                        cur.execute(
                            """
                            INSERT INTO news_articles
                                (title, summary, link, published_at, source_name,
                                 category, content_hash, raw_content)
                            VALUES
                                (%(title)s, %(summary)s, %(link)s, %(published_at)s,
                                 %(source_name)s, %(category)s, %(content_hash)s, %(raw_content)s)
                            ON CONFLICT (content_hash) DO NOTHING
                            """,
                            art,
                        )
                        if cur.rowcount:
                            inserted += 1
                        else:
                            skipped += 1
                    except Exception as exc:
                        logger.warning("Failed to insert article '%s': %s", art.get("title", "?"), exc)
                        skipped += 1

        return inserted, skipped

    # ── Collector run tracking ─────────────────────────────────────────────────

    def start_run(self) -> int:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO collector_runs (status) VALUES ('RUNNING') RETURNING id"
                )
                return cur.fetchone()[0]

    def complete_run(
        self,
        run_id: int,
        feeds_fetched: int = 0,
        articles_new: int = 0,
        articles_skipped: int = 0,
        status: str = "COMPLETED",
        error_message: Optional[str] = None,
    ) -> None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE collector_runs
                    SET completed_at    = NOW(),
                        feeds_fetched   = %s,
                        articles_new    = %s,
                        articles_skipped = %s,
                        status          = %s,
                        error_message   = %s
                    WHERE id = %s
                    """,
                    (feeds_fetched, articles_new, articles_skipped, status, error_message, run_id),
                )

    # ── Watchlist management ───────────────────────────────────────────────────

    def get_watchlist(self) -> list[dict]:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT symbol FROM watchlist ORDER BY symbol")
                return cur.fetchall()

    def add_to_watchlist(self, symbol: str) -> bool:
        symbol = symbol.upper().strip()
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO watchlist (symbol) VALUES (%s) ON CONFLICT DO NOTHING",
                        (symbol,),
                    )
                    return cur.rowcount > 0
        except Exception as exc:
            logger.error("Failed to add %s to watchlist: %s", symbol, exc)
            return False

    def remove_from_watchlist(self, symbol: str) -> bool:
        symbol = symbol.upper().strip()
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM watchlist WHERE symbol = %s", (symbol,))
                    return cur.rowcount > 0
        except Exception as exc:
            logger.error("Failed to remove %s from watchlist: %s", symbol, exc)
            return False

    # ── yfinance news persistence ──────────────────────────────────────────────

    def save_yf_news(self, symbol: str, news_items: list[dict]) -> tuple[int, int]:
        """
        Deduplicate and save news from yfinance.
        Uses a helper to parse items before insertion.
        """
        from collector.watchlist import WatchlistCollector
        
        if not news_items:
            return 0, 0

        inserted = skipped = 0
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                for item in news_items:
                    parsed = WatchlistCollector.parse_article(symbol, item)
                    if not parsed:
                        skipped += 1
                        continue

                    # Use a SAVEPOINT per row so a single failure doesn't abort
                    # the entire transaction (psycopg2 InFailedSqlTransaction).
                    try:
                        cur.execute("SAVEPOINT yf_insert")
                        cur.execute(
                            """
                            INSERT INTO yf_news
                                (symbol, news_id, content_type, title, summary, pub_date,
                                 provider_name, provider_url, article_url, thumbnail_url)
                            VALUES
                                (%(symbol)s, %(news_id)s, %(content_type)s, %(title)s, %(summary)s, %(pub_date)s,
                                 %(provider_name)s, %(provider_url)s, %(article_url)s, %(thumbnail_url)s)
                            ON CONFLICT (news_id) DO NOTHING
                            """,
                            parsed,
                        )
                        cur.execute("RELEASE SAVEPOINT yf_insert")
                        if cur.rowcount:
                            inserted += 1
                        else:
                            skipped += 1
                    except Exception as exc:
                        cur.execute("ROLLBACK TO SAVEPOINT yf_insert")
                        cur.execute("RELEASE SAVEPOINT yf_insert")
                        logger.warning("Failed to insert YF news '%s': %s", parsed.get("news_id"), exc)
                        skipped += 1
        return inserted, skipped

    # ── Maintenance ───────────────────────────────────────────────────────────

    def cleanup_old_articles(self, retention_days: int = 90) -> int:
        """Delete articles older than `retention_days`. Returns rows deleted."""
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM news_articles WHERE fetched_at < %s",
                    (cutoff,),
                )
                return cur.rowcount

    def get_stats(self) -> dict:
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        COUNT(*)                                    AS total_articles,
                        COUNT(*) FILTER (WHERE fetched_at > NOW() - INTERVAL '24h') AS last_24h,
                        MIN(published_at)                           AS oldest,
                        MAX(published_at)                           AS newest
                    FROM news_articles
                    """
                )
                return dict(cur.fetchone())
