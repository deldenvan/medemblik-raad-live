"""Webserver: toont de live transcriptie en stuurt updates via WebSocket."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

from . import config, stream
from .transcriber import Segment, StreamingTranscriber, make_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
log = logging.getLogger("server")
STATIC = Path(__file__).parent / "static"


class State:
    def __init__(self) -> None:
        self.status = "starten"  # starten | wachten | live | fout
        self.session_id: str | None = None
        self.started_at: float | None = None
        self.segments: list[dict] = []
        self.pending = ""
        self.clients: set[WebSocket] = set()
        self.logfile: Path | None = None
        self.last_audio: float = 0.0  # wandklok-tijd van laatste audio

    def snapshot(self) -> dict:
        return {"type": "snapshot", "status": self.status, "title": config.TITLE,
                "session": self.session_id, "started_at": self.started_at,
                "segments": self.segments, "pending": self.pending}

    async def broadcast(self, msg: dict) -> None:
        data = json.dumps(msg, ensure_ascii=False)
        for ws in list(self.clients):
            try:
                await ws.send_text(data)
            except Exception:  # noqa: BLE001
                self.clients.discard(ws)

    async def set_status(self, status: str, detail: str = "") -> None:
        self.status = status
        await self.broadcast({"type": "status", "status": status, "detail": detail})

    def new_session(self) -> None:
        self.started_at = time.time()
        self.session_id = datetime.now().strftime("%Y-%m-%d_%H%M")
        self.segments = []
        self.pending = ""
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.logfile = config.DATA_DIR / f"{self.session_id}.jsonl"

    def add(self, seg: Segment) -> dict:
        item = {"id": len(self.segments), "start": round(seg.start, 2),
                "end": round(seg.end, 2), "text": seg.text,
                "clock": datetime.fromtimestamp((self.started_at or 0) + seg.start).strftime("%H:%M:%S")}
        self.segments.append(item)
        if self.logfile:
            with self.logfile.open("a", encoding="utf-8") as f:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        return item


state = State()


async def run_pipeline() -> None:
    engine = await asyncio.to_thread(make_engine)
    while True:
        await state.set_status("wachten", "Zoeken naar een live uitzending…")
        media = await stream.resolve(config.STREAM_URL)
        if not media:
            log.info("Geen live uitzending gevonden; opnieuw over %ss", config.RETRY_SECONDS)
            await asyncio.sleep(config.RETRY_SECONDS)
            continue

        log.info("Stream gevonden: %s", media)
        resume = (state.started_at is not None
                  and time.time() - state.last_audio < config.SESSION_GAP_MINUTES * 60)
        if resume:
            offset = time.time() - state.started_at
            context = " ".join(s["text"] for s in state.segments[-5:])
            log.info("Zelfde vergadering, ga verder op %.0fs", offset)
        else:
            state.new_session()
            await state.broadcast(state.snapshot())
            offset, context = 0.0, ""
        tr = StreamingTranscriber(engine, offset, context)
        last_step = time.monotonic()
        got_audio = False
        try:
            async for chunk in stream.pcm_chunks(media):
                if not got_audio:
                    got_audio = True
                    await state.set_status("live")
                tr.add_audio(chunk)
                state.last_audio = time.time()
                if time.monotonic() - last_step >= config.STEP_SECONDS:
                    last_step = time.monotonic()
                    await _emit(*await asyncio.to_thread(tr.step))
            await _emit(*await asyncio.to_thread(tr.step, True))
        except Exception as e:  # noqa: BLE001
            log.exception("Fout in pipeline")
            await state.set_status("fout", str(e))
        log.info("Uitzending gestopt.")
        await asyncio.sleep(config.RETRY_SECONDS if not got_audio else 5)


async def _emit(final: list[Segment], pending: str) -> None:
    for seg in final:
        await state.broadcast({"type": "segment", "segment": state.add(seg)})
    if pending != state.pending or final:
        state.pending = pending
        await state.broadcast({"type": "pending", "text": pending})


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(run_pipeline())
    yield
    task.cancel()


app = FastAPI(title=config.TITLE, lifespan=lifespan)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/healthz")
async def healthz() -> JSONResponse:
    return JSONResponse({"ok": True, "status": state.status})


@app.get("/api/transcript")
async def transcript() -> JSONResponse:
    return JSONResponse(state.snapshot())


def _fmt(t: float, sep: str) -> str:
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02}:{int(m):02}:{int(s):02}{sep}{int((t % 1) * 1000):03}"


@app.get("/download.txt")
async def download_txt() -> PlainTextResponse:
    body = "\n".join(f"[{s['clock']}] {s['text']}" for s in state.segments)
    return PlainTextResponse(body, headers={
        "Content-Disposition": f'attachment; filename="raad-medemblik-{state.session_id}.txt"'})


@app.get("/download.srt")
async def download_srt() -> PlainTextResponse:
    blocks = [f"{i + 1}\n{_fmt(s['start'], ',')} --> {_fmt(s['end'], ',')}\n{s['text']}\n"
              for i, s in enumerate(state.segments)]
    return PlainTextResponse("\n".join(blocks), headers={
        "Content-Disposition": f'attachment; filename="raad-medemblik-{state.session_id}.srt"'})


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    await websocket.accept()
    state.clients.add(websocket)
    await websocket.send_text(json.dumps(state.snapshot(), ensure_ascii=False))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        state.clients.discard(websocket)


def main() -> None:
    import uvicorn

    uvicorn.run(app, host=config.HOST, port=config.PORT, proxy_headers=True,
                ws_ping_interval=20, ws_ping_timeout=20)


if __name__ == "__main__":
    main()
