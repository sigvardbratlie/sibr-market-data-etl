#!/usr/bin/env bash
# Engangsoppsett på Raspberry Pi. Kjør fra repo-roten: ./pipelines/install.sh
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USER_NAME="${SUDO_USER:-$USER}"

if ! command -v docker >/dev/null; then
  echo "Installerer Docker..."
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker "$USER_NAME"
  echo "Logg ut og inn igjen (docker-gruppe), og kjør scriptet på nytt."
  exit 0
fi

for m in scraping modeling api cadastral; do
  [[ -f "$REPO_DIR/$m/.env" ]] || echo "⚠️  Mangler $m/.env – kopier den fra maskinen din (scp)."
done

echo "Bygger images (tar en stund første gang)..."
cd "$REPO_DIR" && docker compose --profile job build

for f in sibr-pipeline.service sibr-pipeline.timer; do
  sed -e "s|__USER__|$USER_NAME|g" -e "s|__REPO__|$REPO_DIR|g" \
    "$REPO_DIR/pipelines/systemd/$f" | sudo tee "/etc/systemd/system/$f" >/dev/null
done
sudo systemctl daemon-reload
sudo systemctl enable --now sibr-pipeline.timer
systemctl list-timers sibr-pipeline.timer --no-pager
echo "Ferdig. Test nå: sudo systemctl start sibr-pipeline.service && journalctl -u sibr-pipeline -f"
