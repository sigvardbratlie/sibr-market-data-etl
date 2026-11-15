# Progress / Changelog

## Status
| Steg | Image | I k8s-chart | Aktiv i pipeline |
|---|---|---|---|
| scraping | ✅ bygget og testet arm64 | ✅ | ✅ (ikke deployet ennå) |
| clean | ⬜ ikke testet arm64 | ✅ | ⬜ |
| api | ⬜ | ✅ | ⬜ |
| cadastral | ⬜ | ✅ | ⬜ |
| predict | ⬜ | ✅ | ⬜ |
| train | ⬜ | ✅ (kun manuell) | ⬜ |

## Logg

### 2026-11-15 – Helm/k8s på Talos (branch `feat/helm`)
- Ny Helm-chart `deploy/helm/sibr-market`: pipeline-CronJob (sekvensielle initContainers) + suspendert CronJob per steg, `timeZone: Europe/Oslo`, `concurrencyPolicy: Forbid`, `ttlSecondsAfterFinished`, Pod Security `restricted`, control-plane-toleration.
- Dockerfiles: non-root UID 10001, `PYTHONUNBUFFERED`, torch fra CPU-index i modeling. `.env` lagt i alle `.dockerignore` (scraping/cadastral bakte tidligere `.env` inn i lokale builds).
- `.github/workflows/images.yml`: arm64-bygg på `ubuntu-24.04-arm` -> GHCR (`sha-<sha>` + `latest`), kun endrede moduler; helm lint.
- Secrets: først et kubectl-script, erstattet samme dag av Helm-template `templates/secrets.yaml` + gitignored `values.secrets.yaml` (+ `values.secrets.example.yaml`). `deploy/scripts/env-to-values.py` genererer filen fra `*/.env` (normaliserer quotes/mellomrom, dropper `GOOGLE_APPLICATION_CREDENTIALS`). Valgfri `imageCredentials` -> pull secret.
- `Makefile` som snarveier for build/push/secrets/deploy/run/logs.
- Pi/systemd-oppsettet (docker compose + timer) flyttet til `legacy/pi-systemd/`: virker ikke på Talos (ingen shell/systemd/Docker).
- `pipelines/` fjernet; KFP-requirements -> `legacy/gcp/`. Workspace-medlemmer som ikke fantes (`pipelines`, `bigquery-helper`) fjernet fra root `pyproject.toml`.
- scraping: advarsel sjekker nå `GOOGLE_APPLICATION_CREDENTIALS_JSON`.

### 2026-11-06 – Bort fra GCP, første forsøk: Docker Compose + systemd på Pi (ucommittet)
- `cloudbuild.yaml` og Vertex/KFP-`pipelines/pipeline.py` flyttet til `legacy/gcp/`. Begrunnelse: GCP (Vertex AI + Cloud Build) var dyrt og unødvendig komplekst for en batchjobb hver 3. dag.
- `docker-compose.yml` med jobbene bak profil `job`; `run.sh` + systemd-timer (`*-*-01/3 02:00`). Erstattet samme uke av k8s/Helm da Pi-en fikk Talos.
- scraping: spiders kjøres **sekvensielt** (ikke 7 samtidig), skånsommere tempo mot finn.no (`CONCURRENT_REQUESTS=16`, `DOWNLOAD_DELAY=0.3`, autothrottle target 5), exit-kode 1 ved feil, asyncio-reactor installeres eksplisitt, dobbel stream-logging fjernet, hardkodet proxy fjernet.

### 2026-09-04
- Rettet scraping etter HTML-endringer på Finn.no. Flere "gcloud build"-commits (Cloud Build-trigger).

### 2026-05 – 2026-06
- Refaktorering: data warehouse/nosql skilt ut i egne moduler per pakke, absolutte imports, logging-utils. Prosjektstruktur endret for å unngå `ModuleNotFound`.

### 2026-02 – 2026-03
- Repo omdøpt til `sibr-market-data-etl`, UV workspace, README.
- Tester for api (77 stk) og cadastral. `ApiBase` for async API-kall med rate limiting.
- Kjent felle: `api/src/api/` (pakke) skygger `src/api.py`; tester laster via `importlib` i conftest.

### Før 2026
- Kjørt som Vertex AI Pipeline (KFP) med cron `0 2 */3 * *`, images i Artifact Registry `europe-west1-docker.pkg.dev/sibr-market/sibr-market-repo/`, bygget av Cloud Build ved commit-melding "gcloud build".
