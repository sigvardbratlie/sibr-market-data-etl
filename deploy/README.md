# Deploy – Kubernetes (Talos på Raspberry Pi) med Helm

```
GitHub (main) ──Actions──► ghcr.io/sigvardbratlie/sibr-<modul>:sha-xxxx (arm64)
                                      │
helm upgrade --install ──► namespace sibr-market
   ├─ CronJob sibr-market-pipeline   "0 2 */3 * *" Europe/Oslo
   │     pod: [init] scraping → [init] clean → … → [main] siste steg   (styres av pipeline.steps)
   └─ CronJob sibr-market-<steg>     suspendert, mal for manuelle kjøringer / egen plan
```

## Første gangs oppsett
```bash
# 1. Images (enten CI ved push til main, eller fra Mac – native arm64):
export GHCR_TOKEN=<classic PAT: write:packages>
make login build-push MODULES=scraping

#    Deretter: GitHub -> Packages -> sibr-<modul> -> Package settings -> Change visibility: Public
#    (da trengs ingen pull secret; repoet er public uansett)

# 2. Secrets: values.secrets.yaml (gitignored). Generer fra */.env, eller fyll ut fra values.secrets.example.yaml
make secrets

# 3. Deploy (chartet lager Secrets fra values.secrets.yaml)
make deploy    # = helm upgrade --install sibr-market deploy/helm/sibr-market -n sibr-market -f values.secrets.yaml --set image.tag=latest

# 4. Test nå i stedet for å vente til 02:00
make run-now && make logs
```

## Daglig bruk
| Kommando | Hva |
|---|---|
| `make status` | CronJobs, Jobs, pods |
| `make run-now` | Trigger pipelinen |
| `make run-step STEP=api` | Kjør ett steg |
| `make logs` | Følg nyeste pod (alle containere) |
| `kubectl -n sibr-market get cronjob sibr-market-pipeline -o jsonpath='{.status.lastScheduleTime}'` | Siste planlagte kjøring |

## Utvide pipelinen
I `values.yaml` (eller `--set`):
```yaml
pipeline:
  steps: [scraping, clean, api, cadastral, predict]
```
Husk at image for modulen må finnes i GHCR (`make build-push MODULES="modeling api cadastral"`).

Gi et steg egen plan i stedet:
```yaml
steps:
  api:
    standalone: { enabled: true, suspend: false, schedule: "0 6 * * 1" }
```

## Hvordan planlegging fungerer i k8s
`CronJob` er innebygd (controller-manager). Ingen ekstra scheduler trengs. Feltene som betyr noe her:
- `timeZone: Europe/Oslo`: ellers UTC.
- `concurrencyPolicy: Forbid`: hopper over ny kjøring hvis forrige pågår.
- `startingDeadlineSeconds: 3600`: kjøringen startes likevel hvis noden var nede under 1 time.
- `backoffLimit: 0`: én feil = jobben feiler (ingen ny full scraping-runde automatisk).
- `activeDeadlineSeconds`: hard tidsgrense.
- `*/3` på dag-i-måned er "dag 1, 4, 7 … 31" og nullstilles ved månedsskifte.

Sekvensiell kjøring uten Argo: stegene er `initContainers`, som Kubernetes kjører én og én i rekkefølge, og neste starter kun ved exit 0. Trenger du parallelle grener, retry per steg eller UI, er neste steg Argo Workflows (`CronWorkflow`).

## Secrets
`templates/secrets.yaml` lager én Secret per nøkkel under `secrets:` i values; stegene leser dem via `envFrom` (`steps.<x>.secretName`). Verdiene ligger kun i gitignored `values.secrets.yaml` og i Helm sin release-secret i clusteret. Er `secrets:` tom, forventes Secretene å finnes fra før (existingSecret-mønsteret). Neste nivå om ønskelig: SOPS (`helm-secrets`) for å kunne committe krypterte verdier, eller External Secrets mot GCP Secret Manager.

Private GHCR-pakker: sett `imageCredentials` (registry/username/password=PAT read:packages) i `values.secrets.yaml`. Da lages pull secret automatisk.

## Talos-spesifikt
- Single node med control-plane-taint → chartet har `tolerations` for det. Alternativt `cluster.allowSchedulingOnControlPlanes: true` i Talos machine config.
- Namespace `sibr-market` har Pod Security `restricted`; imagene kjører som UID 10001.
- Pi-en mangler RTC: sjekk `talosctl -n 192.168.10.67 time` om cron-tider virker feil.
