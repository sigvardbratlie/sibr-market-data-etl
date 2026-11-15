#!/usr/bin/env bash
# Kjører pipeline-stegene sekvensielt. Stopper ved første feil.
#   ./pipelines/run.sh                  # standard steg (STEPS)
#   ./pipelines/run.sh scraping clean   # valgfrie steg
#   ./pipelines/run.sh --update         # git pull + rebuild først
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

# Samme rekkefølge som Vertex-pipelinen. Legg til api/cadastral/predict ved behov.
DEFAULT_STEPS=(scraping clean)

UPDATE=0
STEPS=()
for arg in "$@"; do
  case "$arg" in
    --update) UPDATE=1 ;;
    *) STEPS+=("$arg") ;;
  esac
done
[[ ${#STEPS[@]} -eq 0 ]] && STEPS=("${DEFAULT_STEPS[@]}")

# Hindre overlappende kjøringer
if command -v flock >/dev/null; then
  exec 9>"/tmp/sibr-pipeline.lock"
  flock -n 9 || { echo "En kjøring pågår allerede, avslutter."; exit 0; }
fi

log() { echo "[$(date '+%F %T')] $*"; }

# Ctrl+C / systemctl stop: avbryt hele pipelinen, ikke bare steget som kjører
trap 'log "Avbrutt"; exit 130' INT TERM

if [[ $UPDATE -eq 1 ]]; then
  log "Oppdaterer kode og bygger images"
  git pull --ff-only
  docker compose --profile job build
fi

start=$(date +%s)
for step in "${STEPS[@]}"; do
  log "▶ $step"
  t0=$(date +%s)
  docker compose run --rm "$step"
  log "✔ $step ($(( $(date +%s) - t0 ))s)"
done
log "Ferdig: ${STEPS[*]} på $(( $(date +%s) - start ))s"
docker image prune -f >/dev/null
