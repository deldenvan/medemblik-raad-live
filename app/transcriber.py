"""Doorlopende transcriptie met faster-whisper.

Werkwijze: audio komt binnen in een buffer. Elke STEP_SECONDS wordt de hele buffer
getranscribeerd. Alle zinnen behalve de laatste zijn 'definitief' (de laatste kan
nog veranderen als er meer audio binnenkomt). Definitieve audio wordt uit de buffer
gehaald, zodat het werk per stap klein blijft.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from . import config

log = logging.getLogger("transcriber")


@dataclass
class Segment:
    start: float  # seconden sinds begin uitzending
    end: float
    text: str


def _load_prompt() -> str | None:
    try:
        words = [w.strip() for w in config.VOCAB_FILE.read_text("utf-8").splitlines()
                 if w.strip() and not w.startswith("#")]
    except FileNotFoundError:
        return None
    # Whisper gebruikt max. ~224 tokens prompt; houd het compact.
    return ("Vergadering van de gemeenteraad van Medemblik. " + ", ".join(words))[:800]


class WhisperEngine:
    def __init__(self) -> None:
        from faster_whisper import WhisperModel

        log.info("Model %s laden (%s/%s)…", config.WHISPER_MODEL,
                 config.WHISPER_DEVICE, config.WHISPER_COMPUTE)
        self.model = WhisperModel(config.WHISPER_MODEL, device=config.WHISPER_DEVICE,
                                  compute_type=config.WHISPER_COMPUTE,
                                  cpu_threads=config.WHISPER_THREADS)
        self.prompt = _load_prompt()

    def transcribe(self, audio: np.ndarray, context: str) -> list[Segment]:
        prompt = " ".join(p for p in (self.prompt, context[-300:]) if p) or None
        segments, _ = self.model.transcribe(
            audio,
            language=config.LANGUAGE,
            beam_size=5,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            initial_prompt=prompt,
            condition_on_previous_text=False,
        )
        return [Segment(s.start, s.end, s.text.strip()) for s in segments if s.text.strip()]


class MockEngine:
    """Zonder model: geeft nepzinnen terug. Handig om de website te testen."""

    def __init__(self) -> None:
        self.n = 0

    def transcribe(self, audio: np.ndarray, context: str) -> list[Segment]:
        dur = len(audio) / 16000
        out, t = [], 0.0
        while t + 3 <= dur:
            self.n += 1
            out.append(Segment(t, t + 3, f"Testzin {self.n}: de voorzitter geeft het woord aan de wethouder."))
            t += 3
        return out


def make_engine():
    return MockEngine() if config.TRANSCRIBER == "mock" else WhisperEngine()


class StreamingTranscriber:
    """Houdt de buffer bij en splitst resultaten in definitief en voorlopig."""

    def __init__(self, engine, offset: float = 0.0, context: str = "") -> None:
        self.engine = engine
        self.buffer = np.zeros(0, dtype=np.float32)
        self.offset = offset  # tijd (s) sinds begin vergadering van het begin van de buffer
        self.context = context

    def add_audio(self, pcm16: bytes) -> None:
        samples = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        self.buffer = np.concatenate([self.buffer, samples])

    @property
    def buffered_seconds(self) -> float:
        return len(self.buffer) / 16000

    def step(self, flush: bool = False) -> tuple[list[Segment], str]:
        """Geeft (nieuwe definitieve segmenten, voorlopige tekst) terug."""
        if len(self.buffer) < 16000:  # < 1 s
            return [], ""
        segs = self.engine.transcribe(self.buffer, self.context)
        if not segs:
            # Alleen stilte: gooi alles behalve de laatste seconde weg.
            if self.buffered_seconds > 5:
                self._drop(self.buffered_seconds - 1)
            return [], ""

        force = flush or self.buffered_seconds >= config.MAX_BUFFER_SECONDS
        # Laatste segment pas definitief als het ruim voor het einde van de buffer eindigt.
        last_done = segs[-1].end < self.buffered_seconds - 1.5
        final = segs if (force or last_done) else segs[:-1]
        pending = "" if (force or last_done) else segs[-1].text

        out = [Segment(self.offset + s.start, self.offset + s.end, s.text) for s in final]
        if final:
            self.context = (self.context + " " + " ".join(s.text for s in final))[-600:]
            cut = self.buffered_seconds if force else final[-1].end
            self._drop(cut)
        return out, pending

    def _drop(self, seconds: float) -> None:
        n = min(len(self.buffer), int(seconds * 16000))
        self.buffer = self.buffer[n:]
        self.offset += n / 16000
