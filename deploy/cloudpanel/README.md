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

## Bijwerken naar een nieuwe versie

```bash
cd /home/raadlive/htdocs/raad.jouwdomein.nl
sudo -u raadlive git pull
bash deploy/cloudpanel/install.sh raadlive 8090
```

Je `.env` blijft bewaard.

## Problemen oplossen

| Probleem | Oplossing |
|---|---|
| `502 Bad Gateway` | De app draait niet. Bekijk `journalctl -u raad-live-raadlive -n 50`. |
| Blijft op "geen uitzending" tijdens een vergadering | De stream wordt niet gevonden. Zet de `.m3u8`-link in `STREAM_URL` (zie de hoofd-README). |
| "verbinding verbroken" blijft staan | De Vhost-regels van stap 4 ontbreken of staan in het verkeerde blok. |
| Server erg traag | Kies een kleiner model of verlaag `WHISPER_THREADS`. |
