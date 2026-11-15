# sibr-market-data-etl

End-to-end ETL pipeline for Norwegian marketplace data. Scrapes listings from Finn.no, enriches them with cadastral and geocoding data, and trains ML models for price predictions.

## Architecture

The project is a UV workspace with five modules:

```
Finn.no ──► Scraping ──► BigQuery (raw.*)
                              │
               ┌──────────────┼──────────────┐
               ▼              ▼              ▼
           Geocoding     Vehicle API    Cadastral
           (Geonorge)   (Vegvesen)    (Kartverket)
               └──────────────┼──────────────┘
                              ▼
                    Modeling (Clean → Train → Predict)
                              │
                              ▼
                    BigQuery (predictions.*)
```

| Module | Description |
|--------|-------------|
| **scraping** | Scrapy + Playwright spiders for 7 Finn.no categories (cars, homes, new homes, rentals, jobs, boats, motorcycles) |
| **modeling** | Data cleaning, preprocessing, and ML training (XGBoost, CatBoost, LightGBM) for price predictions |
| **cadastral** | Property enrichment via Kartverket Grunnbok API (ownership, transfers, legal status) |
| **api** | Geocoding (Geonorge/Nominatim) and vehicle data enrichment (Statens Vegvesen) |
| **deploy** | Helm chart: Kubernetes CronJobs on a self-hosted Talos cluster (Raspberry Pi, arm64) |

## Tech Stack

- **Python 3.11** / **UV** package manager
- **Scrapy + Playwright** for scraping
- **XGBoost, CatBoost, LightGBM** for ML
- **Google Cloud**: BigQuery, Cloud Storage, Firestore (storage only)
- **Kubernetes + Helm** (Talos Linux on Raspberry Pi) for scheduling, **GHCR** for images

## Setup

```bash
# Install UV (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Set up environment variables

# Install Playwright browsers (for scraping)
playwright install chromium
```

### Required Environment Variables

| Variable | Description |
|----------|-------------|
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to GCP service account key |
| `PROJECT_ID` | GCP project ID (`sibr-market`) |
| `REGION` | GCP region (`europe-west1`) |
| `GRUNNBOK_USERNAME` | Kartverket API username |
| `GRUNNBOK_PASSWORD` | Kartverket API password (via Secret Manager) |
| `STATENS_VEGVESEN_API_KEY` | Vegvesen API key (via Secret Manager) |
| `GMAIL_PASSWORD` | For data quality alert emails |

## Usage

### Scraping

```bash
cd scraping
python main.py --spiders cars homes jobs
python main.py --urls-file urls.txt
python main.py --log_level DEBUG
```

### Modeling

```bash
cd modeling
python main.py --dataset cars --task clean
python main.py --dataset cars --task pre_processed
python main.py --dataset cars --task train
python main.py --dataset cars --task predict
python main.py --run_all
```

### Cadastral

```bash
cd cadastral
python main.py --update-project --fill --transfer-type active --ownership-type eier --save
python main.py --by-properties 0301 123 456 0 0
```

### API Enrichment

```bash
cd api
python main.py --task geocode
python main.py --task statens-vegvesen
python main.py --task all
```

### Pipeline on Kubernetes

See [deploy/README.md](deploy/README.md).

```bash
make secrets && make deploy && make run-now
```

## Testing

```bash
pytest scraping/tests/
pytest modeling/tests/
```

## Deployment

Images are built for arm64 by GitHub Actions on push to `main` (`.github/workflows/images.yml`) and pushed to `ghcr.io/sigvardbratlie/sibr-<module>`. The Helm chart in `deploy/helm/sibr-market` runs the pipeline as a Kubernetes CronJob every 3rd day at 02:00 (Europe/Oslo). Previous GCP setup (Cloud Build + Vertex AI) lives in `legacy/`.

## Project Structure

```
sibr-market-data-etl/
├── scraping/          # Finn.no scrapers (Scrapy + Playwright)
├── modeling/          # ML pipeline (clean, train, predict)
├── cadastral/         # Kartverket property enrichment
├── api/               # Geocoding & vehicle data enrichment
├── deploy/            # Helm chart + scripts for k8s
├── memory-bank/       # Project context across sessions
├── legacy/            # Old GCP / Pi-systemd setup
└── pyproject.toml     # UV workspace definition
```
