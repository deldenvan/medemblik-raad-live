#!/usr/bin/env bash
# Installeert de live-transcriptie op een CloudPanel-server.
#
# Gebruik (als root, vanuit de map van de site):
#   sudo bash deploy/cloudpanel/install.sh <site-gebruiker> <app-poort>
#
# Voorbeeld:
#   cd /home/raadlive/htdocs/raad.example.nl
#   sudo bash deploy/cloudpanel/install.sh raadlive 8090
#
# Het script mag vaker gedraaid worden (bijvoorbeeld na een update).
set -euo pipefail

SITE_USER="${1:?Geef de site-gebruiker op (zie CloudPanel > Sites > Site User)}"
APP_PORT="${2:?Geef de App Port op (zie CloudPanel > Sites > Settings)}"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SERVICE="raad-live-${SITE_USER}"

if [[ $EUID -ne 0 ]]; then
  echo "Draai dit script als root (sudo)." >&2
  exit 1
fi
id "$SITE_USER" >/dev/null 2>&1 || { echo "Gebruiker $SITE_USER bestaat niet." >&2; exit 1; }

echo "==> Systeempakketten (ffmpeg, python3-venv)"
apt-get update -qq
apt-get install -y -qq ffmpeg python3-venv python3-pip rsync >/dev/null

PYTHON="$(command -v python3)"
"$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
  || { echo "Python 3.10 of nieuwer is nodig." >&2; exit 1; }

echo "==> Python-omgeving in $APP_DIR/.venv"
chown -R "$SITE_USER":"$SITE_USER" "$APP_DIR"
sudo -u "$SITE_USER" -H bash -c "
  cd '$APP_DIR'
  [ -d .venv ] || '$PYTHON' -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
"

echo "==> Instellingen (.env)"
if [[ ! -f "$APP_DIR/.env" ]]; then
  sudo -u "$SITE_USER" cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  # Op een server zonder videokaart: kleiner model, int8.
  sed -i 's/^WHISPER_MODEL=.*/WHISPER_MODEL=medium/; s/^WHISPER_DEVICE=.*/WHISPER_DEVICE=cpu/' "$APP_DIR/.env"
fi
# Alleen bereikbaar via NGINX van CloudPanel, op de App Port.
grep -q '^HOST=' "$APP_DIR/.env" && sed -i 's/^HOST=.*/HOST=127.0.0.1/' "$APP_DIR/.env" \
  || echo 'HOST=127.0.0.1' >> "$APP_DIR/.env"
sed -i "s/^PORT=.*/PORT=${APP_PORT}/" "$APP_DIR/.env"

echo "==> systemd-service $SERVICE"
sed -e "s|@USER@|$SITE_USER|g" -e "s|@DIR@|$APP_DIR|g" \
  "$APP_DIR/deploy/cloudpanel/raad-live.service" > "/etc/systemd/system/${SERVICE}.service"

# Laat de site-gebruiker (en dus het automatisch uitrollen) alleen deze service herstarten.
SYSTEMCTL="$(command -v systemctl)"
JOURNALCTL="$(command -v journalctl)"
SUDOERS="/etc/sudoers.d/${SERVICE}"
echo "$SITE_USER ALL=(root) NOPASSWD: $SYSTEMCTL restart $SERVICE, $SYSTEMCTL status $SERVICE, $JOURNALCTL -u $SERVICE *" \
  > "$SUDOERS.tmp"
chmod 440 "$SUDOERS.tmp"
visudo -cf "$SUDOERS.tmp" >/dev/null && mv "$SUDOERS.tmp" "$SUDOERS"

systemctl daemon-reload
systemctl enable "$SERVICE" >/dev/null
systemctl restart "$SERVICE"

sleep 3
if curl -fsS "http://127.0.0.1:${APP_PORT}/healthz" >/dev/null; then
  echo "==> Klaar. De app draait op poort ${APP_PORT}."
else
  echo "==> De app reageert nog niet. Bij de eerste start wordt het model gedownload;"
  echo "    kijk mee met: journalctl -u ${SERVICE} -f"
fi
echo
echo "Vergeet niet de WebSocket-regels in de Vhost te zetten (zie deploy/cloudpanel/README.md)."
echo "Logboek:   journalctl -u ${SERVICE} -f"
echo "Herstart:  systemctl restart ${SERVICE}"
