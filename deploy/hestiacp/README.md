# Installeren op HestiaCP

Zo zet je de live-transcriptie op een server met [HestiaCP](https://hestiacp.com/).
Je hebt nodig: inloggen op HestiaCP, en SSH-toegang als root (of een gebruiker met `sudo`).

In de voorbeelden hieronder heet de HestiaCP-gebruiker `daniel`, het domein
`raad.jouwdomein.nl` en de interne poort van de app `8090`. Vervang die door je eigen waarden.

HestiaCP heeft geen apart sitetype voor Python. Het installatiescript lost dat op: het
maakt een eigen NGINX-template aan dat alle bezoekers doorstuurt naar de app (inclusief
de live-verbinding via WebSocket) en koppelt dat aan je domein. Dat werkt zowel met
**NGINX + Apache** als met **alleen NGINX**.

## 1. Web-domein aanmaken

1. HestiaCP → **Web** → **Add Web Domain**.
2. Vul het domein in, bijvoorbeeld `raad.jouwdomein.nl`, en sla op.
3. Zet bij het domein **Enable SSL for this domain** en **Use Let's Encrypt** aan.
   (De DNS van het domein moet al naar je server wijzen.)

## 2. Code op de server zetten

De code komt in de map `private/` van het domein, zodat de broncode zelf nooit via de
website te zien is:

```bash
ssh root@jouwserver
cd /home/daniel/web/raad.jouwdomein.nl/private
git clone https://github.com/deldenvan/medemblik-raad-live.git raad-live
```

## 3. Installatiescript draaien (als root)

```bash
cd /home/daniel/web/raad.jouwdomein.nl/private/raad-live
bash deploy/hestiacp/install.sh daniel raad.jouwdomein.nl 8090
```

Het script:
- installeert `ffmpeg` en `rsync`
- maakt een Python-omgeving en installeert de onderdelen
- maakt `.env` aan (model `medium`, alleen intern bereikbaar op poort 8090)
- maakt een systemd-service `raad-live-daniel`, zodat de app altijd draait, ook na een
  herstart van de server
- maakt het NGINX-template `raad-live-8090` en zet dat op je domein
- geeft de gebruiker SSH-toegang (shell `bash`), nodig voor automatisch uitrollen

De eerste keer downloadt de app het spraakmodel (`medium`: ongeveer 1,5 GB). Dat kan een
paar minuten duren. Meekijken:

```bash
journalctl -u raad-live-daniel -f
```

Open daarna `https://raad.jouwdomein.nl`. Rechtsboven staat:
- **geen uitzending**: alles werkt, er is alleen nu geen vergadering live
- **LIVE**: de tekst verschijnt
- **verbinding verbroken** (blijft staan): het template staat niet goed op het domein (zie
  "Problemen oplossen")

> Verander in HestiaCP bij dit domein niet het **Proxy Template** (NGINX + Apache) of
> **Web Template** (alleen NGINX). Dat moet `raad-live-8090` blijven.

## Instellingen aanpassen

Bewerk `.env` in de map van de app en herstart:

```bash
nano /home/daniel/web/raad.jouwdomein.nl/private/raad-live/.env
systemctl restart raad-live-daniel
```

### Welk model past bij mijn server?

Spraakherkenning vraagt veel van de processor. Kies naar je server:

| Server | `WHISPER_MODEL` | Opmerking |
|---|---|---|
| 2 kernen, 4 GB | `small` | werkt, maar maakt meer fouten |
| 4 kernen, 8 GB | `medium` | goede balans (standaard) |
| 8+ kernen, 8+ GB | `large-v3-turbo` | beste kwaliteit |

Loopt de tekst steeds verder achter op de uitzending? Kies dan een kleiner model.
Draaien er andere sites op dezelfde server? Zet `WHISPER_THREADS` op ongeveer de helft
van het aantal kernen.

## Automatisch uitrollen (aanbevolen)

Na deze eenmalige instelling komt elke wijziging op de `main`-branch van GitHub vanzelf
op je server. GitHub Actions doet dan:

1. de code controleren;
2. de code via SSH naar je server kopiëren (`.env`, `.venv` en `data/` blijven onaangeraakt);
3. `deploy/hestiacp/update.sh` draaien: onderdelen bijwerken, de app herstarten en
   controleren of hij weer reageert.

Valt een uitrol midden in een vergadering, dan is de app ongeveer een halve minuut weg.
De tekst tot dan toe blijft staan en de transcriptie gaat daarna verder.

### Stap A – Een sleutel voor GitHub maken (op je eigen computer)

```bash
ssh-keygen -t ed25519 -N "" -C "github-deploy" -f raad-deploy
```

Je krijgt twee bestanden: `raad-deploy` (geheim, voor GitHub) en `raad-deploy.pub`
(openbaar, voor de server).

### Stap B – De openbare sleutel aan de HestiaCP-gebruiker geven

Via HestiaCP: log in als `daniel`, klik rechtsboven op je gebruiker → **SSH Keys** →
**Add SSH Key** en plak de inhoud van `raad-deploy.pub`.

Of als root via SSH:

```bash
v-add-user-ssh-key daniel "PLAK-HIER-DE-INHOUD-VAN-raad-deploy.pub"
```

Controleer vanaf je eigen computer dat het werkt:

```bash
ssh -i raad-deploy daniel@jouwserver "echo gelukt"
```

### Stap C – De vingerafdruk van je server ophalen (op je eigen computer)

```bash
ssh-keyscan jouwserver
```

Kopieer alle regels die dit toont. Zo weet GitHub zeker dat het met jóuw server praat.
(Draait SSH op een andere poort, gebruik dan `ssh-keyscan -p POORT jouwserver`.)

### Stap D – Geheimen invullen in GitHub

Ga in de repository naar **Settings → Secrets and variables → Actions →
New repository secret** en maak aan:

| Naam | Waarde |
|---|---|
| `DEPLOY_HOST` | het adres van je server, bijv. `123.45.67.89` of `server.jouwdomein.nl` |
| `DEPLOY_USER` | de HestiaCP-gebruiker, bijv. `daniel` |
| `DEPLOY_PATH` | de map van de app, bijv. `/home/daniel/web/raad.jouwdomein.nl/private/raad-live` |
| `DEPLOY_SSH_KEY` | de volledige inhoud van het bestand `raad-deploy` (dus niet `.pub`) |
| `DEPLOY_KNOWN_HOSTS` | de regels uit stap C |
| `DEPLOY_SSH_PORT` | alleen nodig als SSH niet op poort 22 draait |

Verwijder daarna het bestand `raad-deploy` van je computer, of bewaar het veilig.

### Stap E – Testen

Ga in GitHub naar **Actions → Uitrollen naar HestiaCP → Run workflow**. Na een minuut
of twee staat er een groen vinkje. Bij een rood kruis: klik erop, de foutmelding staat
bij de stap die mislukte.

Zolang de geheimen niet zijn ingevuld, slaat de workflow het uitrollen gewoon over.

### Goed om te weten

- `.env` staat niet in GitHub en wordt nooit overschreven. Instellingen wijzig je dus op
  de server zelf.
- `vocab.txt` (de namenlijst) staat wél in GitHub. Pas die aan in de repository; bij de
  volgende uitrol staat hij op de server.
- Wat je met de hand op de server in de code wijzigt, wordt bij de volgende uitrol
  overschreven.
- Verander je de poort of het domein, draai dan `install.sh` opnieuw.

## Met de hand bijwerken (zonder automatisch uitrollen)

```bash
cd /home/daniel/web/raad.jouwdomein.nl/private/raad-live
sudo -u daniel git pull
sudo -u daniel bash deploy/hestiacp/update.sh
```

## Problemen oplossen

| Probleem | Oplossing |
|---|---|
| `502 Bad Gateway` | De app draait niet. Bekijk `journalctl -u raad-live-daniel -n 50`. |
| Je ziet de standaardpagina van HestiaCP | Het template staat niet op het domein. Draai `install.sh` opnieuw. |
| "verbinding verbroken" blijft staan | Controleer in HestiaCP dat het domein template `raad-live-8090` gebruikt. |
| Let's Encrypt lukt niet | Controleer of de DNS van het domein naar de server wijst en probeer opnieuw. |
| Uitrollen faalt bij "Code naar de server kopiëren" | SSH-sleutel of `DEPLOY_KNOWN_HOSTS` klopt niet. Test stap B opnieuw. |
| Blijft op "geen uitzending" tijdens een vergadering | De stream wordt niet gevonden. Zet de `.m3u8`-link in `STREAM_URL` (zie de hoofd-README). |
| Server erg traag | Kies een kleiner model of verlaag `WHISPER_THREADS`. |
