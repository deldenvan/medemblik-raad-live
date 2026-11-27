#!/usr/bin/env bash
# Installeert de live-transcriptie op een HestiaCP-server.
#
# Gebruik (als root, vanuit de map met de code):
#   bash deploy/hestiacp/install.sh <hestia-gebruiker> <domein> [app-poort]
#
# Voorbeeld:
#   cd /home/daniel/web/raad.example.nl/private/raad-live
#   bash deploy/hestiacp/install.sh daniel raad.example.nl 8090
#
# Het web-domein moet al bestaan in HestiaCP. Het script mag vaker gedraaid worden.
set -euo pipefail

HUSER="${1:?Geef de HestiaCP-gebruiker op}"
DOMAIN="${2:?Geef het domein op (moet al bestaan in HestiaCP)}"
APP_PORT="${3:-8090}"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SERVICE="raad-live-${HUSER}"
HESTIA="${HESTIA:-/usr/local/hestia}"
export PATH="$HESTIA/bin:$PATH"

die() { echo "FOUT: $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Draai dit script als root."
[[ -f "$HESTIA/conf/hestia.conf" ]] || die "HestiaCP niet gevonden in $HESTIA."
[[ "$APP_PORT" =~ ^[0-9]+$ ]] || die "Poort moet een getal zijn."
id "$HUSER" >/dev/null 2>&1 || die "Gebruiker $HUSER bestaat niet."
v-list-web-domain "$HUSER" "$DOMAIN" >/dev/null 2>&1 \
  || die "Web-domein $DOMAIN bestaat niet voor $HUSER. Maak het eerst aan in HestiaCP."

# shellcheck disable=SC1091
source "$HESTIA/conf/hestia.conf"
WEB_SYSTEM="${WEB_SYSTEM:-}"
PROXY_SYSTEM="${PROXY_SYSTEM:-}"

echo "==> Systeempakketten (ffmpeg, python3-venv, rsync)"
apt-get update -qq
apt-get install -y -qq ffmpeg python3-venv python3-pip rsync curl >/dev/null

PYTHON="$(command -v python3)"
"$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
  || die "Python 3.10 of nieuwer is nodig."

echo "==> Python-omgeving in $APP_DIR/.venv"
chown -R "$HUSER":"$HUSER" "$APP_DIR"
sudo -u "$HUSER" -H bash -c "
  cd '$APP_DIR'
  [ -d .venv ] || '$PYTHON' -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
"

echo "==> Instellingen (.env)"
if [[ ! -f "$APP_DIR/.env" ]]; then
  sudo -u "$HUSER" cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  # Op een server zonder videokaart: kleiner model.
  sed -i 's/^WHISPER_MODEL=.*/WHISPER_MODEL=medium/; s/^WHISPER_DEVICE=.*/WHISPER_DEVICE=cpu/' "$APP_DIR/.env"
fi
# Alleen bereikbaar via NGINX, niet direct van buitenaf.
sed -i 's/^HOST=.*/HOST=127.0.0.1/' "$APP_DIR/.env"
grep -q '^HOST=' "$APP_DIR/.env" || echo 'HOST=127.0.0.1' >> "$APP_DIR/.env"
sed -i "s/^PORT=.*/PORT=${APP_PORT}/" "$APP_DIR/.env"
grep -q '^PORT=' "$APP_DIR/.env" || echo "PORT=${APP_PORT}" >> "$APP_DIR/.env"

echo "==> systemd-service $SERVICE"
sed -e "s|@USER@|$HUSER|g" -e "s|@DIR@|$APP_DIR|g" \
  "$APP_DIR/deploy/hestiacp/raad-live.service" > "/etc/systemd/system/${SERVICE}.service"

# Laat de gebruiker (en dus het automatisch uitrollen) alleen deze service herstarten.
SYSTEMCTL="$(command -v systemctl)"
JOURNALCTL="$(command -v journalctl)"
SUDOERS="/etc/sudoers.d/${SERVICE}"
echo "$HUSER ALL=(root) NOPASSWD: $SYSTEMCTL restart $SERVICE, $SYSTEMCTL status $SERVICE, $JOURNALCTL -u $SERVICE *" \
  > "$SUDOERS.tmp"
chmod 440 "$SUDOERS.tmp"
visudo -cf "$SUDOERS.tmp" >/dev/null && mv "$SUDOERS.tmp" "$SUDOERS"

systemctl daemon-reload
systemctl enable "$SERVICE" >/dev/null
systemctl restart "$SERVICE"

echo "==> NGINX-template voor $DOMAIN"
TPL_NAME="raad-live-${APP_PORT}"
if [[ "$PROXY_SYSTEM" == "nginx" ]]; then
  # NGINX vóór Apache: we gebruiken een "proxy-template".
  TPL_DIR="$HESTIA/data/templates/web/nginx"
  LISTEN_HTTP="%proxy_port%"; LISTEN_HTTPS="%proxy_ssl_port%"
  APPLY=(v-change-web-domain-proxy-tpl "$HUSER" "$DOMAIN" "$TPL_NAME" "" "yes")
elif [[ "$WEB_SYSTEM" == "nginx" ]]; then
  # Alleen NGINX (met PHP-FPM): we gebruiken een "web-template".
  TPL_DIR="$HESTIA/data/templates/web/nginx/php-fpm"
  LISTEN_HTTP="%web_port%"; LISTEN_HTTPS="%web_ssl_port%"
  APPLY=(v-change-web-domain-tpl "$HUSER" "$DOMAIN" "$TPL_NAME" "yes")
else
  die "Deze server gebruikt geen NGINX (WEB_SYSTEM=$WEB_SYSTEM). Dat wordt niet ondersteund."
fi
for ext in tpl stpl; do
  sed -e "s|@APP_PORT@|$APP_PORT|g" -e "s|@LISTEN_HTTP@|$LISTEN_HTTP|g" \
      -e "s|@LISTEN_HTTPS@|$LISTEN_HTTPS|g" \
      "$APP_DIR/deploy/hestiacp/templates/raad-live.$ext" > "$TPL_DIR/$TPL_NAME.$ext"
done
"${APPLY[@]}"

echo "==> SSH-toegang voor $HUSER (nodig voor automatisch uitrollen)"
CUR_SHELL="$(getent passwd "$HUSER" | cut -d: -f7)"
case "$CUR_SHELL" in
  */bash|*/sh) echo "    al ingesteld ($CUR_SHELL)" ;;
  *) v-change-user-shell "$HUSER" bash && echo "    shell gewijzigd naar bash" ;;
esac

sleep 3
echo
if curl -fsS "http://127.0.0.1:${APP_PORT}/healthz" >/dev/null 2>&1; then
  echo "Klaar. Open https://${DOMAIN}"
else
  echo "De app reageert nog niet. Bij de eerste start wordt het spraakmodel gedownload;"
  echo "kijk mee met: journalctl -u ${SERVICE} -f"
fi
echo "Zet in HestiaCP nog SSL (Let's Encrypt) aan voor ${DOMAIN} als dat nog niet is gebeurd."
echo "Logboek:   journalctl -u ${SERVICE} -f"
echo "Herstart:  systemctl restart ${SERVICE}"
