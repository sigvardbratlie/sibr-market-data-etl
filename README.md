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
| **pipelines** | Vertex AI pipeline orchestration with Kubeflow Pipelines |

## Tech Stack

- **Python 3.11** / **UV** package manager
- **Scrapy + Playwright** for scraping
- **XGBoost, CatBoost, LightGBM** for ML
- **Google Cloud**: BigQuery, Cloud Storage, Firestore, Vertex AI, Secret Manager, Cloud Build
- **Kubeflow Pipelines** for orchestration

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

### Pipelines

```bash
cd pipelines
python pipeline.py --commit-sha <sha> --run --skip-schedule
```

## Testing

```bash
pytest scraping/tests/
pytest modeling/tests/
```

## Deployment

Deployment is handled via Google Cloud Build. A push to `main` with `"gcloud build"` in the commit message triggers:

1. Docker image builds for each module
2. Push to Artifact Registry (`europe-west1-docker.pkg.dev/sibr-market/sibr-market-repo/`)
3. Vertex AI pipeline compilation and deployment

## Project Structure

```
sibr-market-data-etl/
├── scraping/          # Finn.no scrapers (Scrapy + Playwright)
├── modeling/          # ML pipeline (clean, train, predict)
├── cadastral/         # Kartverket property enrichment
├── api/               # Geocoding & vehicle data enrichment
├── pipelines/         # Vertex AI orchestration (KFP)
├── cloudbuild.yaml    # CI/CD configuration
└── pyproject.toml     # UV workspace definition
```