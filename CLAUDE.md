# CLAUDE.md

## Memory bank (les ALLTID først)
Ved start av hver økt: les `memory-bank/projectBrief.md`, deretter `memory-bank/activeContext.md`, deretter `memory-bank/progress.md` før du svarer.
Oppdater `activeContext.md` og `progress.md` etter vesentlige beslutninger og ved slutten av økten (bruk memory-bank-skillen).

## Hurtigreferanse
- Deploy: Helm-chart `deploy/helm/sibr-market` til Talos-cluster (kube-context `admin@homelab-k8s`, namespace `sibr-market`). Se `deploy/README.md`.
- Images: `ghcr.io/sigvardbratlie/sibr-<modul>`, **arm64**.
- Secrets: Helm-template `templates/secrets.yaml` med verdier fra gitignored `deploy/helm/sibr-market/values.secrets.yaml` (genereres fra `*/.env` med `make secrets`). Aldri commit `.env`, `values.secrets.yaml` eller nøkler.
- Tester: `pytest api/tests`, `pytest cadastral/tests`, `pytest scraping/tests`, `pytest modeling/tests`.
- `legacy/` = gammel GCP- og Pi/systemd-oppsett. Kun referanse.
