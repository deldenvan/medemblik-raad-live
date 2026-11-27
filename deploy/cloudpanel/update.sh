#!/usr/bin/env bash
# Werkt de app bij na nieuwe code. Draait als de site-gebruiker (geen root nodig).
# Wordt automatisch aangeroepen door GitHub Actions (.github/workflows/deploy.yml),
# maar kan ook met de hand:  bash deploy/cloudpanel/update.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$APP_DIR"
SERVICE="raad-live-$(id -un)"
PORT="$(grep -E '^PORT=' .env | cut -d= -f2 || true)"
PORT="${PORT:-8000}"

echo "==> Python-onderdelen bijwerken"
.venv/bin/pip install -q -r requirements.txt

echo "==> $SERVICE herstarten"
# Toegestaan zonder wachtwoord door /etc/sudoers.d/ (aangemaakt door install.sh).
sudo -n systemctl restart "$SERVICE"

echo "==> Wachten tot de app reageert"
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${PORT}/healthz" >/dev/null 2>&1; then
    echo "==> Klaar: app draait weer."
    exit 0
  fi
  sleep 2
done
echo "De app reageert na 2 minuten nog niet. Laatste logregels:" >&2
sudo -n journalctl -u "$SERVICE" -n 30 --no-pager >&2 || true
exit 1
