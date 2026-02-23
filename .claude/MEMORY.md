# Project Memory: sibr-market-data-etl

## Prosjektstruktur
- `api/` – DataApi klasse (geocoding + Statens Vegvesen)
  - `src/api.py` – hoved-modul med `DataApi`
  - `src/api/__init__.py` – tom pakke (skygger api.py ved vanlig import!)
  - `tests/` – tester (opprettet 2026-02-22)
- `scraping/` – Scrapy-spiders
- `modeling/` – modellering

## Viktig: src/api.py vs src/api/-konflikt
`src/api/` (pakke) skygger for `src/api.py` (modul) ved normal import.
`from src.api import DataApi` feiler.
**Løsning:** Bruk `importlib.util.spec_from_file_location` i conftest.py for å laste `src/api.py` direkte.

## Tester (api/tests/)
- Kjøres med: `python -m pytest tests/` fra `api/`-mappen
- Venv: prosjektrotens `.venv` (ikke api-spesifikk)
- pytest-asyncio mode: `asyncio_mode = "auto"` (konfigurert i pyproject.toml)
- 77 tester: 48 unit + 29 integrasjon

## Avhengigheter
- `sibr_api` (ApiBase, NotFoundError, RateLimitError) – installert i .venv
- `sibr_module` (BigQuery, SecretsManager) – installert i .venv
- Ekstern kode (GCP, Firestore) mockes alltid i tester

## Kjøre tester
```bash
/Users/sigvardbratlie/PycharmProjects/sibr-market-data-etl/.venv/bin/python -m pytest api/tests/ -v
```
Eller fra api/-mappen:
```bash
python -m pytest tests/ -v
```
