# Installeren op CloudPanel

Zo zet je de live-transcriptie op een server met [CloudPanel](https://www.cloudpanel.io/).
Je hebt nodig: inloggen op CloudPanel als beheerder, en SSH-toegang als root
(of een gebruiker met `sudo`).

## 1. Site aanmaken

1. CloudPanel → **Sites** → **Add Site** → **Create a Python Site**.
2. Vul in:
   - **Domain Name**: bijvoorbeeld `raad.jouwdomein.nl`
   - **Python Version**: 3.10 of nieuwer (3.12 is prima)
   - **App Port**: bijvoorbeeld `8090` (onthoud dit getal)
   - **Site User** en wachtwoord: bijvoorbeeld `raadlive`
3. Zet bij **SSL/TLS** een gratis Let's Encrypt-certificaat aan.

## 2. Code op de server zetten

Log in via SSH als de site-gebruiker en haal de code op in de map van de site:

```bash
ssh raadlive@jouwserver
cd ~/htdocs/raad.jouwdomein.nl
git clone https://github.com/<jouw-account>/medemblik-raad-live.git .
```

(De map moet leeg zijn. Staat er al een bestand in, verwijder dat eerst.)

## 3. Installatiescript draaien (als root)

```bash
ssh root@jouwserver
cd /home/raadlive/htdocs/raad.jouwdomein.nl
bash deploy/cloudpanel/install.sh raadlive 8090
```

Het script:
- installeert `ffmpeg`
- maakt een Python-omgeving en installeert de onderdelen
- maakt `.env` aan (model `medium`, alleen bereikbaar via CloudPanel op de App Port)
- maakt een systemd-service `raad-live-raadlive`, zodat de app altijd draait,
  ook na een herstart van de server

De eerste keer downloadt de app het spraakmodel (`medium`: ongeveer 1,5 GB). Dat kan
een paar minuten duren. Meekijken:

```bash
journalctl -u raad-live-raadlive -f
```

## 4. Vhost aanpassen voor de live-verbinding

De pagina krijgt nieuwe tekst binnen via een WebSocket. Daarvoor moet NGINX een paar
extra regels hebben.

1. CloudPanel → **Sites** → jouw site → tab **Vhost**.
2. Zoek in het `server`-blok met `listen 443` de regel `location / {`.
3. Plak **daarboven** de inhoud van [`vhost-websocket.conf`](vhost-websocket.conf).
4. **Save**.

Open daarna `https://raad.jouwdomein.nl`. Rechtsboven staat:
- **geen uitzending**: alles werkt, er is alleen nu geen vergadering live
- **LIVE**: de tekst verschijnt
- **verbinding verbroken** (blijft staan): de Vhost-regels van stap 4 ontbreken

## Instellingen aanpassen

Bewerk `.env` in de map van de site (bijvoorbeeld via **File Manager** in CloudPanel
of via SSH) en herstart:

```bash
systemctl restart raad-live-raadlive
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

Na deze eenmalige instelling komt elke wijziging op de `main`-branch van GitHub
vanzelf op je server. GitHub Actions doet dan:

1. de code controleren;
2. de code via SSH naar je server kopiëren (`.env`, `.venv` en `data/` blijven onaangeraakt);
3. `deploy/cloudpanel/update.sh` draaien: onderdelen bijwerken, de app herstarten en
   controleren of hij weer reageert.

Valt een uitrol midden in een vergadering, dan is de app ongeveer een halve minuut weg.
De tekst tot dan toe blijft staan en de transcriptie gaat daarna verder.

### Stap A – Server klaarmaken (eenmalig, als root)

Draai het installatiescript nog een keer. Het geeft de site-gebruiker dan toestemming om
**alleen deze app** te herstarten, en installeert `rsync`:

```bash
cd /home/raadlive/htdocs/raad.jouwdomein.nl
bash deploy/cloudpanel/install.sh raadlive 8090
```

### Stap B – Een sleutel voor GitHub maken (op je eigen computer)

```bash
ssh-keygen -t ed25519 -N "" -C "github-deploy" -f raad-deploy
```

Je krijgt twee bestanden: `raad-deploy` (geheim, voor GitHub) en `raad-deploy.pub`
(openbaar, voor de server).

### Stap C – De openbare sleutel op de server zetten (als root)

Zet de inhoud van `raad-deploy.pub` bij de site-gebruiker:

```bash
mkdir -p /home/raadlive/.ssh
echo "PLAK-HIER-DE-INHOUD-VAN-raad-deploy.pub" >> /home/raadlive/.ssh/authorized_keys
chown -R raadlive:raadlive /home/raadlive/.ssh
chmod 700 /home/raadlive/.ssh && chmod 600 /home/raadlive/.ssh/authorized_keys
```

Controleer vanaf je eigen computer dat het werkt:

```bash
ssh -i raad-deploy raadlive@jouwserver "echo gelukt"
```

### Stap D – De vingerafdruk van je server ophalen (op je eigen computer)

```bash
ssh-keyscan jouwserver
```

Kopieer alle regels die dit toont. Zo weet GitHub zeker dat het met jóuw server praat.
(Draait SSH op een andere poort, gebruik dan `ssh-keyscan -p POORT jouwserver`.)

### Stap E – Geheimen invullen in GitHub

Ga in de repository naar **Settings → Secrets and variables → Actions →
New repository secret** en maak aan:

| Naam | Waarde |
|---|---|
| `DEPLOY_HOST` | het adres van je server, bijv. `123.45.67.89` of `server.jouwdomein.nl` |
| `DEPLOY_USER` | de site-gebruiker, bijv. `raadlive` |
| `DEPLOY_PATH` | de map van de site, bijv. `/home/raadlive/htdocs/raad.jouwdomein.nl` |
| `DEPLOY_SSH_KEY` | de volledige inhoud van het bestand `raad-deploy` (dus niet `.pub`) |
| `DEPLOY_KNOWN_HOSTS` | de regels uit stap D |
| `DEPLOY_SSH_PORT` | alleen nodig als SSH niet op poort 22 draait |

Verwijder daarna het bestand `raad-deploy` van je computer, of bewaar het veilig.

### Stap F – Testen

Ga in GitHub naar **Actions → Uitrollen naar CloudPanel → Run workflow**. Na een
minuut of twee staat er een groen vinkje. Bij een rood kruis: klik erop, de foutmelding
staat bij de stap die mislukte.

Zolang de geheimen niet zijn ingevuld, slaat de workflow het uitrollen gewoon over.

### Goed om te weten

- `.env` staat niet in GitHub en wordt nooit overschreven. Instellingen wijzig je dus op
  de server zelf (daarna `systemctl restart raad-live-raadlive`).
- `vocab.txt` (de namenlijst) staat wél in GitHub. Pas die aan in de repository; bij de
  volgende uitrol staat hij op de server.
- Wat je met de hand op de server in de code wijzigt, wordt bij de volgende uitrol
  overschreven.

## Met de hand bijwerken (zonder automatisch uitrollen)

```bash
cd /home/raadlive/htdocs/raad.jouwdomein.nl
sudo -u raadlive git pull
sudo -u raadlive bash deploy/cloudpanel/update.sh
```

Je `.env` blijft bewaard.

## Problemen oplossen

| Probleem | Oplossing |
|---|---|
| `502 Bad Gateway` | De app draait niet. Bekijk `journalctl -u raad-live-raadlive -n 50`. |
| Blijft op "geen uitzending" tijdens een vergadering | De stream wordt niet gevonden. Zet de `.m3u8`-link in `STREAM_URL` (zie de hoofd-README). |
| "verbinding verbroken" blijft staan | De Vhost-regels van stap 4 ontbreken of staan in het verkeerde blok. |
| Server erg traag | Kies een kleiner model of verlaag `WHISPER_THREADS`. |
