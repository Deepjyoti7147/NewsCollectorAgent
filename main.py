"""
NewsCollectorAgent – main entry point.

Runs as a long-lived daemon with APScheduler.
On 1 vCPU / 1 GB RAM + 2 GB swap:
  • Single-process, no threads for feed fetching (sequential)
  • Small psycopg2 pool (1-3 connections)
  • Politeness delay between RSS requests
  • Structured JSON logging to stdout (captured by systemd / docker)
"""

import logging
import os
import signal
import sys
import time
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv

from collector.db import DBHandler
from collector.parser import FeedParser

# ── Logging setup ─────────────────────────────────────────────────────────────

def _setup_logging(level: str = "INFO") -> None:
    fmt = (
        '{"time":"%(asctime)s","level":"%(levelname)s",'
        '"logger":"%(name)s","msg":%(message)r}'
    )
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=fmt,
        stream=sys.stdout,
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    # Suppress noisy libraries
    for lib in ("apscheduler", "urllib3", "requests", "feedparser"):
        logging.getLogger(lib).setLevel(logging.WARNING)


logger = logging.getLogger("news_collector")

# ── Globals ───────────────────────────────────────────────────────────────────

_db: DBHandler | None = None
_parser: FeedParser | None = None
_scheduler: BlockingScheduler | None = None


# ── Core job ─────────────────────────────────────────────────────────────────

def collect_news() -> None:
    """
    Collect from all RSS feeds and persist to PostgreSQL.
    Called on every scheduled tick.
    """
    global _db, _parser

    run_id: int | None = None
    try:
        run_id = _db.start_run()
        logger.info("Collector run #%d started", run_id)

        articles, feeds_ok = _parser.fetch_all_feeds()
        inserted, skipped = _db.save_articles(articles)

        _db.complete_run(
            run_id,
            feeds_fetched=feeds_ok,
            articles_new=inserted,
            articles_skipped=skipped,
            status="COMPLETED",
        )
        logger.info(
            "Run #%d done — feeds=%d new=%d skipped=%d",
            run_id, feeds_ok, inserted, skipped,
        )

    except Exception as exc:
        logger.exception("Collector run failed: %s", exc)
        if run_id and _db:
            try:
                _db.complete_run(run_id, status="FAILED", error_message=str(exc))
            except Exception:
                pass


def cleanup_old_data() -> None:
    """Weekly maintenance: delete articles older than retention_days."""
    retention = int(os.environ.get("RETENTION_DAYS", "365"))
    try:
        deleted = _db.cleanup_old_articles(retention_days=retention)
        logger.info("Cleanup: removed %d articles older than %d days", deleted, retention)
    except Exception as exc:
        logger.error("Cleanup failed: %s", exc)


# ── Signal handlers ───────────────────────────────────────────────────────────

def _shutdown(signum, frame) -> None:
    logger.info("Signal %d received — shutting down gracefully", signum)
    if _scheduler:
        _scheduler.shutdown(wait=False)
    if _parser:
        _parser.close()
    if _db:
        _db.close()
    sys.exit(0)


# ── Bootstrap ─────────────────────────────────────────────────────────────────

def main() -> None:
    global _db, _parser, _scheduler

    load_dotenv()
    _setup_logging(os.environ.get("LOG_LEVEL", "INFO"))

    # ── Config from environment ────────────────────────────────────────────────
    pg_dsn = os.environ.get("POSTGRES_DSN")
    if not pg_dsn:
        # Build DSN from individual vars (easier for .env / docker-compose)
        pg_dsn = (
            f"host={os.environ.get('POSTGRES_HOST', 'localhost')} "
            f"port={os.environ.get('POSTGRES_PORT', '5432')} "
            f"dbname={os.environ.get('POSTGRES_DB', 'newsdb')} "
            f"user={os.environ.get('POSTGRES_USER', 'newsuser')} "
            f"password={os.environ.get('POSTGRES_PASSWORD', '')} "
            f"sslmode={os.environ.get('POSTGRES_SSLMODE', 'prefer')}"
        )

    # Interval in minutes between full collection runs (default: 15)
    interval_min = int(os.environ.get("COLLECT_INTERVAL_MINUTES", "15"))
    request_delay = float(os.environ.get("REQUEST_DELAY_SECONDS", "1.5"))
    run_once = os.environ.get("RUN_ONCE", "false").lower() == "true"

    logger.info("Starting NewsCollectorAgent — interval=%d min", interval_min)

    # ── Initialise DB ─────────────────────────────────────────────────────────
    _db = DBHandler(dsn=pg_dsn, min_conn=1, max_conn=3)
    _db.connect(retries=10, delay=5.0)

    # ── Initialise parser ─────────────────────────────────────────────────────
    _parser = FeedParser(request_delay=request_delay)

    # ── Signal handlers ───────────────────────────────────────────────────────
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # ── RUN_ONCE mode (for testing / one-shot cron) ───────────────────────────
    if run_once:
        logger.info("RUN_ONCE=true — executing single collection cycle")
        collect_news()
        cleanup_old_data()
        _parser.close()
        _db.close()
        return

    # ── Scheduler ─────────────────────────────────────────────────────────────
    _scheduler = BlockingScheduler(timezone="Asia/Kolkata")

    # Collect on interval (default every 15 min)
    _scheduler.add_job(
        collect_news,
        trigger=IntervalTrigger(minutes=interval_min),
        id="collect_news",
        name="RSS News Collection",
        max_instances=1,                # never run overlapping jobs
        coalesce=True,
        replace_existing=True,
        next_run_time=datetime.now(),   # fire immediately on start
    )

    # Weekly cleanup — Sunday 02:00 IST
    _scheduler.add_job(
        cleanup_old_data,
        trigger=CronTrigger(day_of_week="sun", hour=2, minute=0, timezone="Asia/Kolkata"),
        id="cleanup",
        name="Old Article Cleanup",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )

    logger.info("Scheduler started — waiting for jobs")
    try:
        _scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        _shutdown(0, None)


if __name__ == "__main__":
    main()
