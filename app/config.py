"""Instellingen, allemaal via omgevingsvariabelen (zie .env.example)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Lees .env als die bestaat (echte omgevingsvariabelen gaan voor).
_envfile = ROOT / ".env"
if _envfile.exists():
    for _line in _envfile.read_text("utf-8").splitlines():
        if "=" in _line and not _line.lstrip().startswith("#"):
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


# Bron van de uitzending. Mag een directe .m3u8/audio-URL zijn, een YouTube-link,
# of de Notubiz-livepagina (dan zoekt de tool zelf de stream).
STREAM_URL = _env("STREAM_URL", "https://medemblik.raadsinformatie.nl/live")

# Hoe vaak (seconden) opnieuw proberen als er geen vergadering live is.
RETRY_SECONDS = int(_env("RETRY_SECONDS", "60"))

# Transcriptie
TRANSCRIBER = _env("TRANSCRIBER", "whisper")  # "whisper" of "mock" (voor testen)
WHISPER_MODEL = _env("WHISPER_MODEL", "large-v3-turbo")
WHISPER_DEVICE = _env("WHISPER_DEVICE", "auto")  # auto, cpu, cuda
WHISPER_COMPUTE = _env("WHISPER_COMPUTE", "default")  # int8 is snel op CPU
LANGUAGE = _env("LANGUAGE", "nl")

# Elke STEP_SECONDS wordt de nog niet afgeronde audio opnieuw getranscribeerd.
STEP_SECONDS = float(_env("STEP_SECONDS", "4"))
# Langer dan dit blijft tekst nooit "voorlopig".
MAX_BUFFER_SECONDS = float(_env("MAX_BUFFER_SECONDS", "25"))

# Valt de stream korter dan dit weg, dan gaat dezelfde vergadering verder
# (anders begint een nieuwe transcriptie).
SESSION_GAP_MINUTES = float(_env("SESSION_GAP_MINUTES", "30"))

# Lijst met namen en vaktermen die Whisper helpt (één per regel).
VOCAB_FILE = Path(_env("VOCAB_FILE", str(ROOT / "vocab.txt")))

DATA_DIR = Path(_env("DATA_DIR", str(ROOT / "data")))
HOST = _env("HOST", "0.0.0.0")
PORT = int(_env("PORT", "8000"))
TITLE = _env("TITLE", "Gemeenteraad Medemblik – live meelezen")
