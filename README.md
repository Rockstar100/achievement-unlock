# Pet Product Trend Intelligence

Tracks **dog and cat products only** across Amazon.in, Flipkart, and Google Trends (India). Birds, fish, and other pets are excluded by config and filters.

## Deploy to Render (client staging)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/Tervigon-Collective/pet-trend-intelligence)

1. Click the button → sign in to Render with GitHub (use an account that has access to **Tervigon-Collective**)
2. Approve the Blueprint → **Apply**
3. Wait ~5 min for Docker build
4. Open the service URL — no login required

Full details: [STAGING.md](STAGING.md)

## Default stack (local, open source)

```
Amazon.in (requests + Playwright fallback)
Google Trends (pytrends)
Flipkart (HTML or flipkart-scraper-api)
        │
        ▼
  CSV / JSON bronze  (data/bronze/)
        │
        ▼
  pandas gold transform  (transform/gold_builder.py)
        │
        ▼
  data/gold/gold_dim_trending_pet_products.*
        │
        ├── Dagster schedules → Slack (optional)
        └── Optional: ClickHouse + Cube.js (warehouse profile)
```

| Layer | Tool | Notes |
|-------|------|--------|
| Orchestration | Dagster | Jobs, schedules, asset checks |
| Amazon | requests + BeautifulSoup + **Playwright** | Playwright when HTML is empty/blocked |
| Flipkart | **dvishal485/flipkart-scraper-api** or HTML | Docker service on port 3001 |
| Trends | pytrends | geo=IN |
| Storage | CSV + JSON files | No ClickHouse required |
| Gold | pandas | `transform/gold_builder.py` |
| Alerts | slack-sdk | Webhooks in `.env` |

## Quick start

```bash
# 1. Python deps
pip install -r requirements.txt
playwright install chromium

# 2. Optional: Flipkart open-source API
docker compose up -d flipkart-scraper

# 3. Env
copy .env.example .env   # Windows
# set SLACK_* webhooks if you want digests

# 4. Run pipeline (live scrapes)
python scripts/run_local.py

# Skip Google Trends if rate-limited:
python scripts/run_local.py --skip-gtrends

# Sample data only (no live scrape):
python scripts/run_local.py --skip-scrape

# Production gate (tests + rebuild + healthcheck):
python scripts/prod_ready.py
python scripts/healthcheck.py
```

### Data checker dashboard (local QA)

Browse gold products (with images), bronze tables, and pipeline health in the browser:

```bash
python scripts/serve_dashboard.py
# Open http://127.0.0.1:8765
```

Set `DASHBOARD_PORT` / `DASHBOARD_HOST` to change bind address.

Set `ENVIRONMENT=production` to block sample fallbacks and `--skip-scrape`.


### Dagster UI

```bash
dagster dev -m dagster_project
```

### Sync bronze files

If `bronze_ecom_trends_amazon.csv` is open in an editor it may stay locked. The pipeline always writes `*_latest.csv` and reads that first.

```bash
python scripts/sync_bronze.py
# Close the locked CSV in the editor, then run again to overwrite the primary file.
```

### Optional warehouse (ClickHouse + Cube)

```bash
docker compose --profile warehouse up -d
```

## Configuration

Dog/cat categories and keywords live in:

- `config/amazon_categories.yaml`
- `config/flipkart_search_terms.yaml`
- `config/gtrends_keywords.yaml`

Environment variables: see `.env.example`.

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATA_DIR` | `data` | Bronze/gold output root |
| `AMAZON_USE_PLAYWRIGHT` | `auto` | `auto` / `always` / `never` |
| `FLIPKART_SCRAPER_URL` | `http://localhost:3001` | Open-source Flipkart API |
| `SLACK_DAILY_PULSE_WEBHOOK` | — | Daily Slack pulse |
| `SLACK_WEEKLY_DIGEST_WEBHOOK` | — | Weekly digest |

## Project layout

```
trending-product/
├── config/                 # Dog & cat YAML configs
├── dagster_project/        # Assets, jobs, schedules, file_store
├── scrapers/
│   ├── amazon/             # Bestsellers + Playwright fallback
│   ├── flipkart/           # API + HTML fallback
│   ├── gtrends/            # pytrends
│   └── filters/            # Dog/cat-only filter
├── transform/              # Gold builder (pandas)
├── notifications/          # Slack formatters
├── docker/flipkart-scraper # Dockerfile for OSS Flipkart API
├── data/bronze/            # Raw CSV + daily JSON
├── data/gold/              # Trending products
├── scripts/
│   ├── run_local.py
│   ├── sync_bronze.py
│   └── clean_and_rebuild.py
├── dbt/                    # Optional (warehouse path)
├── cube/                   # Optional semantic layer
└── tests/
```

## Data outputs

| Path | Description |
|------|-------------|
| `data/bronze/bronze_ecom_trends_amazon_latest.csv` | Amazon dog/cat bestsellers |
| `data/bronze/bronze_ecom_trends_flipkart.csv` | Flipkart search rankings |
| `data/bronze/bronze_ecom_trends_gtrends.csv` | Google Trends interest |
| `data/gold/gold_dim_trending_pet_products.csv` | Scored trending products |

## Legal

Web scraping may conflict with site terms of service. Review `LEGAL_REVIEW.md` and `COMPLIANCE_CHECKLIST.md` before production use. Prefer official APIs where available and keep rate limits conservative.
