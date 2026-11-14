"""FastAPI web server: JSON API under /api and the web interface at /."""

from __future__ import annotations

import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .audio import AudioError
from .config import Settings, settings as default_settings
from .studio import Studio

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class SpeakRequest(BaseModel):
    voice_id: str
    text: str = Field(max_length=5000)
    language: str = "en"
    speed: float = 1.0


class BatchRequest(BaseModel):
    voice_id: str
    script: str = Field(max_length=50_000)
    language: str = "en"
    speed: float = 1.0


class RenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)


def create_app(settings: Settings | None = None, studio: Studio | None = None) -> FastAPI:
    settings = settings or default_settings
    studio = studio or Studio(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        print(f"Loading {studio.engine.label} on {studio.engine.device}…")
        studio.load()
        print("Ready.")
        yield

    app = FastAPI(title="Timbre", version=__version__, lifespan=lifespan)
    app.state.studio = studio

    # ------------------------------------------------------------- status

    @app.get("/api/status")
    def status():
        info = studio.engine.info()
        return {"version": __version__, "ready": studio.engine.loaded, "engine": info.__dict__}

    # ------------------------------------------------------------- voices

    @app.get("/api/voices")
    def list_voices():
        return [v.to_dict() for v in studio.voices.list()]

    @app.post("/api/voices", status_code=201)
    def add_voice(
        name: str = Form(...),
        consent: bool = Form(False),
        notes: str = Form(""),
        file: UploadFile = File(...),
    ):
        suffix = Path(file.filename or "clip.wav").suffix or ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            shutil.copyfileobj(file.file, tmp, length=1024 * 1024)
            tmp_path = Path(tmp.name)
        try:
            if tmp_path.stat().st_size > MAX_UPLOAD_BYTES:
                raise HTTPException(413, "Clips are limited to 25 MB. Trim it to 10–30 seconds of speech.")
            voice = studio.voices.add(name, tmp_path, consent=consent, notes=notes)
        except PermissionError as exc:
            raise HTTPException(403, _msg(exc))
        except AudioError as exc:
            raise HTTPException(422, _msg(exc))
        finally:
            tmp_path.unlink(missing_ok=True)
        return voice.to_dict()

    @app.get("/api/voices/{voice_id}/audio")
    def voice_audio(voice_id: str):
        try:
            return FileResponse(studio.voices.reference_path(voice_id), media_type="audio/wav")
        except KeyError as exc:
            raise HTTPException(404, _msg(exc))

    @app.patch("/api/voices/{voice_id}")
    def rename_voice(voice_id: str, body: RenameRequest):
        try:
            return studio.voices.rename(voice_id, body.name).to_dict()
        except KeyError as exc:
            raise HTTPException(404, _msg(exc))

    @app.delete("/api/voices/{voice_id}", status_code=204)
    def delete_voice(voice_id: str):
        try:
            studio.voices.delete(voice_id)
        except KeyError as exc:
            raise HTTPException(404, _msg(exc))

    # ------------------------------------------------------------- generation

    @app.post("/api/speak")
    def speak(body: SpeakRequest):
        return _generate(lambda: studio.speak(body.voice_id, body.text, body.language, body.speed))

    @app.post("/api/batch")
    def batch(body: BatchRequest):
        return _generate(lambda: studio.batch(body.voice_id, body.script, body.language, body.speed))

    def _generate(fn):
        try:
            return fn().to_dict()
        except KeyError as exc:
            raise HTTPException(404, _msg(exc))
        except ValueError as exc:
            raise HTTPException(422, _msg(exc))

    # ------------------------------------------------------------- takes

    @app.get("/api/takes")
    def list_takes(limit: int = 50):
        return [t.to_dict() for t in studio.list_takes(limit)]

    @app.get("/api/takes/{take_id}/{filename}")
    def take_file(take_id: str, filename: str, download: bool = False):
        try:
            path = studio.take_file(take_id, filename)
        except KeyError as exc:
            raise HTTPException(404, _msg(exc))
        media = "audio/wav" if path.suffix == ".wav" else "text/plain"
        name = f"timbre-{take_id}-{filename}" if download else None
        return FileResponse(path, media_type=media, filename=name)

    @app.delete("/api/takes/{take_id}", status_code=204)
    def delete_take(take_id: str):
        try:
            studio.delete_take(take_id)
        except KeyError as exc:
            raise HTTPException(404, _msg(exc))

    # ------------------------------------------------------------- web UI

    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app


def _msg(exc: Exception) -> str:
    """KeyError wraps its message in quotes; return the plain message."""
    return str(exc.args[0]) if exc.args else str(exc)
