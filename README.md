# NewsCollectorAgent

A lightweight, production-ready daemon that continuously collects Indian stock market news from curated RSS feeds and stores it in a remote PostgreSQL database.

Designed to run comfortably on a **1 vCPU / 1 GB RAM + 2 GB swap** cloud VM.

---

## Features

- **Watchlist API** — REST endpoints to add/remove tickers (e.g. TCS, MSFT) for targeted news tracking
- **yfinance integration** — automatically fetches latest news for watchlist tickers with smart rate-limiting
- **SHA-256 deduplication** — duplicate articles across RSS feeds or yfinance are never stored twice
- **APScheduler daemon** — polls feeds every 15 minutes; watchlist every 5 minutes; weekly cleanup job
- **Two deployment options**: Docker Compose (exposed API) or bare-metal systemd service

---

## Project Structure

```
NewsCollectorAgent/
├── collector/
│   ├── __init__.py
│   ├── feeds.py          # Curated RSS feed list (20+ sources)
│   ├── parser.py         # RSS parser + HTTP client + SHA-256 dedup
│   ├── db.py             # PostgreSQL handler (connection pool, schema, upsert)
│   ├── watchlist.py      # yfinance news fetcher with rate-limiting
│   └── api.py            # Flask REST API for watchlist management
├── deploy/
│   ├── setup_vm.sh           # Collector VM setup (Ubuntu/Debian)
│   ├── setup_postgres_vm.sh  # DB VM setup with PostgreSQL tuning
│   └── news-collector.service # systemd unit file
├── main.py               # Entry point — scheduler + config from env
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

---

## Quick Start

### 1. PostgreSQL VM (DB Server)

```bash
# On the DB VM
export POSTGRES_PASSWORD="your_strong_password"
export COLLECTOR_VM_IP="10.0.0.5"   # IP of your collector VM
sudo bash deploy/setup_postgres_vm.sh
```

Open port **5432** in your cloud firewall **only** from the collector VM's IP.

---

### 2. Collector VM — Docker (Recommended)

```bash
# SSH into collector VM
git clone https://github.com/Deepjyoti7147/NewsCollectorAgent.git
cd NewsCollectorAgent

cp .env.example .env
nano .env   # fill POSTGRES_HOST, POSTGRES_PASSWORD, etc.

docker compose up -d
docker compose logs -f
```

---

### 2. Collector VM — Bare-metal systemd

```bash
# As root on the collector VM
bash deploy/setup_vm.sh

cp /opt/news-collector/.env.example /opt/news-collector/.env
nano /opt/news-collector/.env   # fill in real values

sudo systemctl start news-collector
sudo journalctl -u news-collector -f
```

---

## Configuration (`.env`)

| Variable | Default | Description |
|---|---|---|
| `POSTGRES_HOST` | `localhost` | DB VM hostname / IP |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_DB` | `newsdb` | Database name |
| `POSTGRES_USER` | `newsuser` | DB user |
| `POSTGRES_PASSWORD` | *(required)* | DB password |
| `POSTGRES_SSLMODE` | `prefer` | `prefer` / `require` / `disable` |
| `POSTGRES_DSN` | — | Full DSN (overrides individual fields) |
| `COLLECT_INTERVAL_MINUTES` | `15` | How often to poll all feeds |
| `REQUEST_DELAY_SECONDS` | `1.5` | Delay between individual feed requests |
| `RETENTION_DAYS` | `90` | Auto-delete articles older than N days |
| `RUN_ONCE` | `false` | Exit after one collection cycle |
| `API_PORT` | `5000` | Port for the Watchlist REST API |
| `API_HOST` | `0.0.0.0` | Host for the API server |
| `YF_FETCH_DELAY_SECONDS` | `120` | Delay between yfinance requests per ticker |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` |

## Watchlist API

Manage the symbols you want to track via yfinance news.

| Endpoint | Method | Description |
|---|---|---|
| `/watchlist` | `GET` | List all tracked symbols |
| `/watchlist/<symbol>` | `POST` | Add a ticker to the watchlist |
| `/watchlist/<symbol>` | `DELETE` | Remove a ticker |

**Example Usage:**
```bash
# Add TCS to tracking
curl -X POST http://localhost:5000/watchlist/TCS

# List current watchlist
curl http://localhost:5000/watchlist

# Remove a ticker
curl -X DELETE http://localhost:5000/watchlist/AAPL
```

---

## Database Schema

### `news_articles`
| Column | Type | Notes |
|---|---|---|
| `id` | BIGSERIAL | Primary key |
| `title` | TEXT | Article title |
| `summary` | TEXT | Lead paragraph / description |
| `link` | TEXT | Original URL |
| `published_at` | TIMESTAMPTZ | Publication time |
| `fetched_at` | TIMESTAMPTZ | When collector stored it |
| `source_name` | TEXT | Feed name (e.g. "Moneycontrol News") |
| `category` | TEXT | Markets / Regulatory / Global Macro etc. |
| `content_hash` | CHAR(64) | SHA-256 of title+link — unique key |

### `yf_news` (Watchlist News)
| Column | Type | Notes |
|---|---|---|
| `id` | BIGSERIAL | Primary key |
| `symbol` | TEXT | Ticker symbol (e.g. TCS) |
| `news_id` | TEXT | Unique ID from Yahoo Finance |
| `title` | TEXT | Article title |
| `article_url` | TEXT | Link to the news |
| `provider_name` | TEXT | Source (e.g. Simply Wall St) |
| `pub_date` | TIMESTAMPTZ | Publication time |

### `watchlist`
| Column | Type | Notes |
|---|---|---|
| `symbol` | TEXT | Unique ticker symbol (Primary Key) |
| `added_at` | TIMESTAMPTZ | When it was added |

### `collector_runs`
Tracks each RSS collection cycle: status, articles inserted/skipped, timestamps.

---

## RSS Feed Sources

| Source | Category |
|---|---|
| Economic Times Markets / Stocks | Markets, Stocks |
| Mint Markets / Money | Markets, Economy |
| Business Standard Markets / Economy | Markets, Economy |
| Financial Express Markets | Markets |
| Moneycontrol News / Reports | Markets |
| NDTV Profit | Markets |
| Zee Business | Markets |
| **SEBI Press Releases** | Regulatory |
| **RBI Press Releases** | Regulatory |
| Reuters Business | Global Macro |
| Bloomberg Markets | Global Macro |
| Investing.com Forex | Forex |
| ET IT/Tech, Banking, Energy, Auto | Sector |

---

## Memory Profile

On the target VM (1 core / 1 GB RAM + 2 GB swap):

- **Idle**: ~60–80 MB RSS
- **During collection**: ~100–130 MB RSS (all feeds ~2 MB XML total)
- **PostgreSQL connection pool**: 1–3 connections (minimal overhead)
- Feed parsing is fully streaming — no full-page scraping or large payloads

---

## Useful Commands

```bash
# Check latest articles in DB
psql -U newsuser -d newsdb -c \
  "SELECT source_name, title, published_at FROM news_articles ORDER BY fetched_at DESC LIMIT 20;"

# Count by category
psql -U newsuser -d newsdb -c \
  "SELECT category, COUNT(*) FROM news_articles GROUP BY category ORDER BY count DESC;"

# View collector run history
psql -U newsuser -d newsdb -c \
  "SELECT id, started_at, status, articles_new, articles_skipped FROM collector_runs ORDER BY id DESC LIMIT 10;"

# One-shot test run (no scheduler)
RUN_ONCE=true python main.py
```

---

## Security Notes

1. **Firewall**: Open port 5432 on the DB VM **only** from the collector VM's IP.
2. **SSL**: Set `POSTGRES_SSLMODE=require` once you have SSL configured on PostgreSQL.
3. **No credentials in source**: all secrets live in `.env` (git-ignored).
4. **Non-root**: both Docker container and systemd service run as `newscollector` user.

---

## Extending

- **Add feeds**: edit `collector/feeds.py` — just add an entry to `RSS_FEEDS`.
- **Add full-text scraping**: hook into `parser.py` `_fetch_feed` and populate `raw_content`.
- **Expose a REST API**: add FastAPI on top of the DB handler for your StockDashboard to query.
- **Alerts**: add a job in `main.py` that queries recent articles for keywords (e.g. "circuit breaker", "SEBI order") and pushes a Telegram / Slack message.
