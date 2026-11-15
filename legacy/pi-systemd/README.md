# Pipelines – lokal kjøring på Raspberry Pi

Docker Compose for jobbene + systemd-timer for planlegging. Erstatter Vertex AI / Cloud Build.
Data lagres fortsatt i BigQuery (credentials via `GOOGLE_APPLICATION_CREDENTIALS_JSON` i hver modul sin `.env`).

## Oppsett (én gang)
```bash
git clone <repo> ~/sibr-market-data-etl && cd ~/sibr-market-data-etl
# fra Mac: scp {scraping,modeling,api,cadastral}/.env pi@<pi>:~/sibr-market-data-etl/<modul>/
./pipelines/install.sh
```

## Bruk
| Kommando | Hva |
|---|---|
| `./pipelines/run.sh` | Kjør standard steg (scraping → clean) |
| `./pipelines/run.sh api cadastral` | Kjør valgfrie steg |
| `./pipelines/run.sh --update` | `git pull` + rebuild, så kjør |
| `sudo systemctl start sibr-pipeline` | Trigger planlagt jobb manuelt |
| `journalctl -u sibr-pipeline -f` | Følg logger |
| `systemctl list-timers sibr-pipeline.timer` | Neste kjøring |

Plan: kl 02:00 hver 3. dag (`pipelines/systemd/sibr-pipeline.timer`). `Persistent=true` tar igjen kjøringer hvis Pi-en var av.
Standard steg endres i `DEFAULT_STEPS` i `run.sh`.
