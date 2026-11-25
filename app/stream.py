"""Vindt de echte stream-URL en levert ruwe audio (16 kHz mono, 16-bit) via ffmpeg."""
from __future__ import annotations

import asyncio
import html
import logging
import re
import shutil
import urllib.parse
import urllib.request
from typing import AsyncIterator

log = logging.getLogger("stream")

SAMPLE_RATE = 16000
BYTES_PER_SECOND = SAMPLE_RATE * 2

_MEDIA_RE = re.compile(r"\.(m3u8|mpd|mp3|aac|m4a|mp4|ts|wav|ogg|opus)(\?|$)", re.I)
_M3U8_IN_PAGE = re.compile(r"https?:[^\"'\s<>]+?\.m3u8[^\"'\s<>]*", re.I)
_IFRAME_RE = re.compile(r"<iframe[^>]+src=[\"']([^\"']+)[\"']", re.I)

UA = "Mozilla/5.0 (X11; Linux x86_64) raad-live-transcriptie"


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "replace")


def _scan_page(url: str, depth: int = 0) -> str | None:
    """Zoek een .m3u8 in de HTML van een pagina (en één niveau iframes)."""
    try:
        page = _get(url)
    except Exception as e:  # noqa: BLE001
        log.warning("Kan %s niet ophalen: %s", url, e)
        return None
    text = html.unescape(page).replace("\\/", "/")
    m = _M3U8_IN_PAGE.search(text)
    if m:
        return m.group(0)
    if depth < 1:
        for src in _IFRAME_RE.findall(text):
            src = urllib.parse.urljoin(url, html.unescape(src))
            found = _scan_page(src, depth + 1)
            if found:
                return found
    return None


async def _yt_dlp(url: str) -> str | None:
    if not shutil.which("yt-dlp"):
        return None
    proc = await asyncio.create_subprocess_exec(
        "yt-dlp", "-g", "-f", "bestaudio/best", "--no-warnings", url,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out, _ = await proc.communicate()
    if proc.returncode == 0 and out.strip():
        return out.decode().splitlines()[0].strip()
    return None


async def resolve(url: str) -> str | None:
    """Geef een URL terug die ffmpeg direct kan afspelen, of None als er niets live is."""
    if _MEDIA_RE.search(url.split("#")[0]):
        return url
    found = await _yt_dlp(url)
    if found:
        return found
    return await asyncio.to_thread(_scan_page, url)


async def pcm_chunks(media_url: str, chunk_seconds: float = 0.5) -> AsyncIterator[bytes]:
    """Start ffmpeg en lever audio in stukjes van chunk_seconds."""
    cmd = ["ffmpeg", "-nostdin", "-loglevel", "error"]
    if media_url.startswith("http"):
        cmd += ["-reconnect", "1", "-reconnect_streamed", "1",
                "-reconnect_delay_max", "10", "-user_agent", UA]
    else:
        cmd += ["-re"]  # lokaal bestand: afspelen in echte tijd, handig om te testen
    cmd += ["-i", media_url, "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "-"]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    size = int(BYTES_PER_SECOND * chunk_seconds)
    try:
        assert proc.stdout
        while True:
            try:
                data = await proc.stdout.readexactly(size)
            except asyncio.IncompleteReadError as e:
                if e.partial:
                    yield e.partial
                break
            yield data
    finally:
        if proc.returncode is None:
            proc.kill()
        err = (await proc.stderr.read()).decode(errors="replace").strip() if proc.stderr else ""
        await proc.wait()
        if err:
            log.warning("ffmpeg: %s", err[-500:])

