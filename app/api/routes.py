"""HTTP API: health, model/voice discovery, and synthesis.

Audio responses stream per synthesis segment (low time-to-first-audio): a WAV
header is sent first, then little-endian PCM frames as each segment is produced.
The JSON response buffers the full clip (it can't be streamed).
"""

from __future__ import annotations

import base64

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app import registry
from app.audio import duration_secs, streaming_wav_header, to_pcm16_bytes, to_wav_bytes
from app.config import settings
from app.engines.base import TTSEngine
from app.schemas import AudioJSONResponse, ModelInfo, TTSRequest, VoiceInfo

router = APIRouter()


def _get_engine(name: str) -> TTSEngine:
    try:
        return registry.get(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown model '{name}'.")


def _audio_stream(engine: TTSEngine, req: TTSRequest) -> StreamingResponse:
    """Stream audio as a WAV header followed by per-segment PCM frames.

    The first segment is pulled eagerly so validation errors surface as proper
    HTTP status codes before the 200 response body starts.
    """
    chunks = engine.stream(req)
    try:
        first, sample_rate = next(chunks)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except StopIteration:
        raise HTTPException(status_code=500, detail="No audio produced.")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Synthesis failed: {exc}")

    def body():
        yield streaming_wav_header(sample_rate)
        yield to_pcm16_bytes(first)
        for samples, _ in chunks:
            yield to_pcm16_bytes(samples)

    return StreamingResponse(
        body(),
        media_type="audio/wav",
        headers={
            "Content-Disposition": 'inline; filename="speech.wav"',
            "X-Sample-Rate": str(sample_rate),
            "Cache-Control": "no-store",
        },
    )


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "default_model": settings.default_model}


@router.get("/models", response_model=list[ModelInfo])
def models() -> list[ModelInfo]:
    return registry.list_models()


@router.get("/voices", response_model=list[VoiceInfo])
def voices(model: str = Query(default=None)) -> list[VoiceInfo]:
    return _get_engine(model or settings.default_model).list_voices()


@router.post("/tts")
def tts(req: TTSRequest):
    engine = _get_engine(req.model)

    if req.response == "json":
        try:
            samples, sample_rate = engine.synthesize(req)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Synthesis failed: {exc}")
        return AudioJSONResponse(
            audio_base64=base64.b64encode(to_wav_bytes(samples, sample_rate)).decode(
                "ascii"
            ),
            sample_rate=sample_rate,
            format=req.format,
            duration_secs=round(duration_secs(samples, sample_rate), 3),
            model=req.model,
            voice=req.voice or "default",
        )

    return _audio_stream(engine, req)


@router.get("/tts")
def tts_get(
    text: str = Query(..., min_length=1),
    model: str = Query(default=None),
    voice: str | None = Query(default=None),
    language: str | None = Query(default=None),
    speed: float = Query(default=1.0, ge=0.5, le=2.0),
):
    """Streaming synthesis over GET so an <audio> element can play it directly."""
    req = TTSRequest(
        text=text,
        model=model or settings.default_model,
        voice=voice or None,
        language=language or None,
        speed=speed,
        response="audio",
    )
    return _audio_stream(_get_engine(req.model), req)
