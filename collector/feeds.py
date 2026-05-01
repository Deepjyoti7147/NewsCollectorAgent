"""
Curated RSS feed sources for Indian stock market news.
Covers: NSE/BSE announcements, business news, RBI/SEBI, macro indicators,
global market movers that impact Indian equities.
"""

RSS_FEEDS = [
    # ── Indian Business & Financial Media ─────────────────────────────────────
    {
        "name": "Economic Times Markets",
        "url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
        "category": "markets",
        "weight": 1.0,
    },
    {
        "name": "Economic Times Stocks",
        "url": "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
        "category": "stocks",
        "weight": 1.0,
    },
    {
        "name": "Mint Markets",
        "url": "https://www.livemint.com/rss/markets",
        "category": "markets",
        "weight": 1.0,
    },
    {
        "name": "Mint Money",
        "url": "https://www.livemint.com/rss/money",
        "category": "economy",
        "weight": 0.8,
    },
    {
        "name": "Business Standard Markets",
        "url": "https://www.business-standard.com/rss/markets-106.rss",
        "category": "markets",
        "weight": 1.0,
    },
    {
        "name": "Business Standard Economy",
        "url": "https://www.business-standard.com/rss/economy-policy-100.rss",
        "category": "economy",
        "weight": 0.9,
    },
    {
        "name": "Financial Express Markets",
        "url": "https://www.financialexpress.com/market/feed/",
        "category": "markets",
        "weight": 0.9,
    },
    {
        "name": "Moneycontrol News",
        "url": "https://www.moneycontrol.com/rss/latestnews.xml",
        "category": "markets",
        "weight": 1.0,
    },
    {
        "name": "Moneycontrol Markets",
        "url": "https://www.moneycontrol.com/rss/marketreports.xml",
        "category": "markets",
        "weight": 0.9,
    },
    {
        "name": "NDTV Profit",
        "url": "https://feeds.feedburner.com/ndtvprofit-latest",
        "category": "markets",
        "weight": 0.8,
    },
    {
        "name": "Zee Business",
        "url": "https://www.zeebiz.com/feeds/rss.xml",
        "category": "markets",
        "weight": 0.7,
    },

    # ── Regulatory & Exchange ──────────────────────────────────────────────────
    {
        "name": "SEBI Press Releases",
        "url": "https://www.sebi.gov.in/sebirss.xml",
        "category": "regulatory",
        "weight": 1.0,
    },
    {
        "name": "RBI Press Releases",
        "url": "https://www.rbi.org.in/scripts/rss.aspx",
        "category": "regulatory",
        "weight": 1.0,
    },

    # ── Global Macro (impacts Indian market) ──────────────────────────────────
    {
        "name": "Reuters Business",
        "url": "https://feeds.reuters.com/reuters/businessNews",
        "category": "global_macro",
        "weight": 0.7,
    },
    {
        "name": "Bloomberg Asia",
        "url": "https://feeds.bloomberg.com/markets/news.rss",
        "category": "global_macro",
        "weight": 0.7,
    },
    {
        "name": "Investing.com INR/USD",
        "url": "https://www.investing.com/rss/currencies_Rates.rss",
        "category": "forex",
        "weight": 0.6,
    },

    # ── Sector-Specific ────────────────────────────────────────────────────────
    {
        "name": "Economic Times IT/Tech",
        "url": "https://economictimes.indiatimes.com/tech/rssfeeds/13357270.cms",
        "category": "sector_tech",
        "weight": 0.8,
    },
    {
        "name": "Economic Times Banking",
        "url": "https://economictimes.indiatimes.com/industry/banking/finance/banking/rssfeeds/44065691.cms",
        "category": "sector_banking",
        "weight": 0.8,
    },
    {
        "name": "Economic Times Energy",
        "url": "https://economictimes.indiatimes.com/industry/energy/rssfeeds/13358472.cms",
        "category": "sector_energy",
        "weight": 0.7,
    },
    {
        "name": "Economic Times Auto",
        "url": "https://economictimes.indiatimes.com/industry/auto/rssfeeds/518386.cms",
        "category": "sector_auto",
        "weight": 0.7,
    },
]

# Categories used for DB tagging
CATEGORY_LABELS = {
    "markets": "Markets",
    "stocks": "Stocks",
    "economy": "Economy",
    "regulatory": "Regulatory",
    "global_macro": "Global Macro",
    "forex": "Forex",
    "sector_tech": "Technology",
    "sector_banking": "Banking & Finance",
    "sector_energy": "Energy",
    "sector_auto": "Automobile",
}
