"""End-to-end API tests using a fake engine (no model download needed).

The Kokoro engine is exercised manually (see README verification); these tests
cover the API contract and the registry wiring with a lightweight fake so they
run fast and offline in CI.
"""

from __future__ import annotations

import base64

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import registry
from app.engines.base import TTSEngine
from app.schemas import TTSRequest, VoiceInfo


class FakeEngine(TTSEngine):
    name = "fake"

    def load(self) -> None:
        pass

    def list_voices(self) -> list[VoiceInfo]:
        return [VoiceInfo(id="fake_en", language="en", gender="female")]

    def languages(self) -> list[str]:
        return ["en"]

    def synthesize(self, req: TTSRequest):
        if req.voice and req.voice != "fake_en":
            raise ValueError(f"Unknown voice '{req.voice}'.")
        # 0.1s of silence at 24 kHz.
        return np.zeros(2400, dtype=np.float32), 24_000


@pytest.fixture()
def app_client():
    registry.register(FakeEngine())
    from app.main import app

    return TestClient(app)


def test_health(app_client):
    res = app_client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_models_lists_fake(app_client):
    res = app_client.get("/models")
    assert res.status_code == 200
    names = [m["name"] for m in res.json()]
    assert "fake" in names


def test_voices(app_client):
    res = app_client.get("/voices?model=fake")
    assert res.status_code == 200
    assert res.json()[0]["id"] == "fake_en"


def test_tts_audio(app_client):
    res = app_client.post("/tts", json={"text": "hi", "model": "fake"})
    assert res.status_code == 200
    assert res.headers["content-type"] == "audio/wav"
    assert res.content[:4] == b"RIFF"


def test_tts_json(app_client):
    res = app_client.post(
        "/tts", json={"text": "hi", "model": "fake", "response": "json"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["sample_rate"] == 24_000
    assert base64.b64decode(body["audio_base64"])[:4] == b"RIFF"


def test_tts_unknown_model(app_client):
    res = app_client.post("/tts", json={"text": "hi", "model": "nope"})
    assert res.status_code == 404


def test_tts_bad_voice(app_client):
    res = app_client.post(
        "/tts", json={"text": "hi", "model": "fake", "voice": "ghost"}
    )
    assert res.status_code == 400
