"""Pydantic request/response models shared across engines and the API."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.config import settings


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Text to synthesize.")
    model: str = Field(default_factory=lambda: settings.default_model)
    voice: Optional[str] = Field(None, description="Engine voice id; engine default if omitted.")
    language: Optional[str] = Field(None, description="Language code, e.g. 'en' or 'hi'.")
    speed: float = Field(1.0, ge=0.5, le=2.0)
    format: Literal["wav"] = "wav"
    response: Literal["audio", "json"] = "audio"


class VoiceInfo(BaseModel):
    id: str
    language: str
    gender: Optional[str] = None


class ModelInfo(BaseModel):
    name: str
    languages: list[str]
    voice_count: int


class AudioJSONResponse(BaseModel):
    audio_base64: str
    sample_rate: int
    format: str
    duration_secs: float
    model: str
    voice: str
