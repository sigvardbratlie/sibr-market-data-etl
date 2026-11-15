# Project Brief – sibr-market-data-etl

## Hva
End-to-end ETL for norske markedsplassdata. Skraper annonser fra Finn.no, beriker med geokoding, kjøretøydata og matrikkel-/grunnbokdata, og trener ML-modeller for prisprediksjon. Data lagres i BigQuery (`sibr-market`).

## Moduler (UV workspace)
| Modul | Rolle | Image | Entrypoint |
|---|---|---|---|
| `scraping` | Scrapy-spiders for 7 Finn-kategorier -> BQ `raw.*` | `sibr-scraping` | `python main.py` |
| `modeling` | clean / train / predict (XGBoost, CatBoost, LightGBM, torch) | `sibr-modeling` | `python -m modeling.main` |
| `api` | Geokoding (Geonorge/Nominatim) + Statens vegvesen | `sibr-api` | `python -m api.main --task all` |
| `cadastral` | Kartverket Grunnbok (eierskap, overdragelser) | `sibr-cadastral` | `python -m cadastral.main` |

Logisk pipeline-rekkefølge: `scraping -> clean -> api -> cadastral -> predict` (train manuelt).

## Kjøremiljø (fra nov 2026)
- **Eget k8s-cluster**: Raspberry Pi (arm64, 8 GB), Talos Linux v1.14, k8s v1.37, single node (`talos-tt4-osg`, 192.168.10.67), kube-context `admin@homelab-k8s`.
- Deploy via **Helm-chart** `deploy/helm/sibr-market` -> CronJobs i namespace `sibr-market`.
- Images: `ghcr.io/sigvardbratlie/sibr-<modul>`, arm64, bygget av GitHub Actions (`.github/workflows/images.yml`) eller `make build-push`. GHCR container-lagring er gratis (også private) per nov 2026; plan: gjør pakkene public.
- Secrets: Helm-template (`templates/secrets.yaml`) -> Secrets `sibr-<modul>-env`, verdier i gitignored `values.secrets.yaml` (generert fra `*/.env` med `make secrets`). Aldri i git.
- Lagring er fortsatt BigQuery/GCS (auth: `GOOGLE_APPLICATION_CREDENTIALS_JSON` = base64 service account-nøkkel).

## Mål
- Kjøre hele pipelinen billig på eget cluster i stedet for GCP Vertex AI / Cloud Build.
- Prioritet 1: scraping hver 3. dag kl 02:00 (Europe/Oslo). De andre stegene ligger klare i chartet.

## Utenfor scope / senere
- Databricks: vurderes for læring, ikke prioritert.
- Flytte lagring bort fra BigQuery: ikke besluttet.
- Argo Workflows / ekte DAG-orkestrering: ikke nødvendig ennå (sekvensiell pod med initContainers holder).
