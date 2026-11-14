"""API tests. Skipped automatically if FastAPI isn't installed."""

import numpy as np
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from timbre import audio as A  # noqa: E402
from timbre.config import Settings  # noqa: E402
from timbre.server import create_app  # noqa: E402


@pytest.fixture
def client(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", engine="demo")
    with TestClient(create_app(settings)) as c:
        yield c


def _clip_bytes(tmp_path) -> bytes:
    sr = 22050
    t = np.arange(sr * 6) / sr
    tone = (0.3 * np.sin(2 * np.pi * 150 * t)).astype(np.float32)
    return A.save_wav(tmp_path / "clip.wav", tone, sr).read_bytes()


def test_full_flow(client, tmp_path):
    assert client.get("/api/status").json()["engine"]["name"] == "demo"

    files = {"file": ("clip.wav", _clip_bytes(tmp_path), "audio/wav")}
    denied = client.post("/api/voices", data={"name": "Narrator"}, files=files)
    assert denied.status_code == 403

    voice = client.post("/api/voices", data={"name": "Narrator", "consent": "true"}, files=files).json()
    assert client.get(f"/api/voices/{voice['id']}/audio").status_code == 200

    take = client.post("/api/speak", json={"voice_id": voice["id"], "text": "Hello there."}).json()
    assert client.get(f"/api/takes/{take['id']}/take.wav").status_code == 200
    assert client.get(f"/api/takes/{take['id']}/take.srt").status_code == 200

    bad = client.post("/api/speak", json={"voice_id": voice["id"], "text": ""})
    assert bad.status_code == 422

    assert client.delete(f"/api/takes/{take['id']}").status_code == 204
    assert client.get("/").status_code == 200
