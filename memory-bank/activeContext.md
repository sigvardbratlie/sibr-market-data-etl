# Active Context

_Sist oppdatert: 2026-11-15_

## Nå: første deploy av scraping til Talos-clusteret (branch `feat/helm`)
Helm-chart, Dockerfiles, CI og secrets-script er skrevet og validert (`helm lint` + `kubectl apply --dry-run=server` mot clusteret; scraping-image bygget og røyktestet lokalt på arm64). Committet og pushet; **PR #1** (`feat/helm` -> `main`): https://github.com/sigvardbratlie/sibr-market-data-etl/pull/1. Ikke deployet ennå. Namespace: `sibr-market`.

Gjenstår for å få scraping i drift:
1. Merge PR #1 til `main` (trigger `images`-workflow -> GHCR). Sjekk at alle fire images bygger på arm64.
2. Sett GHCR-pakkene til public (eller `imageCredentials` i values.secrets.yaml).
3. `make secrets` (genererer values.secrets.yaml) -> `make deploy` -> `make run-now` -> `make logs`.

## Beslutninger
- **Én pipeline-CronJob** der stegene kjøres sekvensielt som initContainers (neste starter kun ved exit 0). Velges med `pipeline.steps` i values. Nå: `[scraping]`.
- **Én suspendert CronJob per steg** som mal for manuelle kjøringer (`make run-step STEP=api`) og egne planer.
- Secrets som **Helm-template** med verdier fra gitignored `values.secrets.yaml` (bruker ønsket template fremfor eget kubectl-script). Tom `secrets:` = existingSecret-modus.
- GHCR som registry (gratis); images public siden repoet er public -> ingen pull secret.
- Flyt: PR -> merge til main -> CI bygger endrede moduler (`latest` + `sha-*`). `make deploy` fra Mac kun ved endring i chart/values/secrets. Default `image.tag=latest` + `pullPolicy: Always` (CI bygger ikke alle moduler hver gang, så `sha-<HEAD>` finnes ikke alltid). Mulig neste steg: Argo CD/Flux (GitOps) for automatisk deploy.
- Pod Security `restricted` på namespace; images kjører som UID 10001.
- Toleration for control-plane-taint (single node). Fjernes når det kommer worker-noder.
- docker-compose.yml beholdes kun for lokal kjøring på Mac.

## Åpne punkter
- Proxy-credentials lå hardkodet i `scraping/finn_scraper/settings.py` i git-historikken (fjernet nå). **Bør roteres** hos proxy-leverandøren.
- Raspberry Pi har ingen RTC: pods viste "56y ago" ved boot. Sjekk at NTP er synket (`talosctl time`) før cron-tider stoles på.
- `*/3` i dag-i-måned nullstilles ved månedsskifte (31. -> 1.). Akseptert.
- modeling-imaget (torch m.m.) er stort; ikke bygget/testet på arm64 ennå.
