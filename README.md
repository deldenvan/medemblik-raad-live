# Gemeenteraad Medemblik – live meelezen

Schrijft de livestream van de gemeenteraad van Medemblik automatisch uit, terwijl de
vergadering bezig is. Meelezers openen een webpagina en zien de tekst binnenkomen,
met tijden erbij. Handig voor doven en slechthorenden, voor wie zonder geluid wil
volgen en om achteraf snel iets terug te zoeken.

## Wat het doet

1. Zoekt elke minuut of er een vergadering live is (standaard op
   `medemblik.raadsinformatie.nl/live`).
2. Haalt het geluid op met `ffmpeg`.
3. Zet spraak om naar tekst met Whisper (`faster-whisper`), lokaal, zonder clouddienst.
4. Toont de tekst live op een webpagina. Tekst die nog kan veranderen staat grijs.
5. Bewaart elke vergadering in `data/` en biedt downloads als tekst en als ondertitels (`.srt`).

Op de pagina: zoeken in de tekst, grotere of kleinere letters, licht/donker en
automatisch meescrollen (scroll omhoog om terug te lezen; de knop "Naar live" brengt je terug).

## Installeren op CloudPanel

Zie [deploy/cloudpanel/README.md](deploy/cloudpanel/README.md): Python-site aanmaken,
één installatiescript draaien en een paar regels in de Vhost plakken. Daar staat ook
hoe je automatisch uitrollen instelt: elke wijziging op `main` komt dan vanzelf op je server.

## Starten met Docker

```bash
cp .env.example .env
docker compose up -d --build
```

Open daarna http://localhost:8000. De eerste keer wordt het Whisper-model
gedownload (ongeveer 1,6 GB voor `large-v3-turbo`).

## Starten zonder Docker

Nodig: Python 3.10+ en ffmpeg.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.server
```

## Instellingen (`.env`)

| Variabele | Uitleg |
|---|---|
| `STREAM_URL` | De livepagina, of een directe `.m3u8`-link. Een lokaal bestand mag ook (om te testen). |
| `WHISPER_MODEL` | `large-v3-turbo` (beste), `medium` of `small` (sneller, minder goed). |
| `WHISPER_COMPUTE` | `int8` op een gewone processor, `float16` op een NVIDIA-videokaart. |
| `STEP_SECONDS` | Hoe vaak de tekst wordt bijgewerkt. |
| `SESSION_GAP_MINUTES` | Valt de stream korter weg dan dit, dan gaat dezelfde vergadering verder. |
| `TRANSCRIBER=mock` | Testmodus zonder model: toont nepzinnen. |

### Namen goed laten herkennen

Zet namen van raadsleden, wethouders, de burgemeester en fracties in `vocab.txt`
(één per regel). Whisper krijgt die lijst mee en schrijft de namen dan veel vaker goed.

### Als de stream niet automatisch gevonden wordt

De livepagina laadt de video soms via JavaScript. Werkt het automatisch zoeken niet:
open de livepagina tijdens een vergadering in de browser, open de ontwikkelaarstools
(F12) → tabblad *Netwerk*, filter op `m3u8` en zet die link in `STREAM_URL`.

## Hardware

- Met een NVIDIA-videokaart loopt `large-v3-turbo` ruim in echte tijd.
- Op alleen een processor: kies `medium` of `small` met `WHISPER_COMPUTE=int8` als de
  tekst achterloopt. Een moderne processor met 8 kernen haalt `large-v3-turbo` int8
  meestal net.

## Testen zonder vergadering

```bash
TRANSCRIBER=mock STREAM_URL=/pad/naar/opname.mp3 python -m app.server
```

Met een echte opname van een eerdere raadsvergadering en `TRANSCRIBER=whisper` test je
de echte herkenning.

## Let op

De tekst is automatisch gemaakt en kan fouten bevatten. Het is geen officieel verslag.
Wil je de pagina openbaar maken, overleg dan met de griffie over gebruik van de
uitzending en zet de pagina achter een reverse proxy met HTTPS.

## Opbouw

- `app/stream.py` – zoekt de stream en levert audio via ffmpeg
- `app/transcriber.py` – doorlopende transcriptie (voorlopige en definitieve tekst)
- `app/server.py` – webserver, WebSocket, downloads
- `app/static/index.html` – de pagina voor meelezers
