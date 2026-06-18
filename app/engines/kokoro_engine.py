"""Kokoro-82M TTS engine.

Kokoro outputs 24 kHz float32 mono audio. Voice ids encode language + gender:
the first char is the Kokoro lang_code group (a/b = English, h = Hindi, ...) and
the second char is f/m (female/male), e.g. ``af_heart``, ``hf_alpha``, ``am_adam``.
"""

from __future__ import annotations

import numpy as np
from kokoro import KPipeline

from app.config import settings
from app.engines.base import TTSEngine
from app.schemas import TTSRequest, VoiceInfo

SAMPLE_RATE = 24_000
REPO_ID = "hexgrad/Kokoro-82M"
DEFAULT_VOICE = "af_heart"

# Request language code -> Kokoro lang_code group.
_LANG_TO_CODE: dict[str, str] = {
    "en": "a",
    "en-us": "a",
    "en-gb": "b",
    "hi": "h",
    "es": "e",
    "fr": "f",
    "it": "i",
    "pt": "p",
    "pt-br": "p",
    "ja": "j",
    "zh": "z",
}

# Kokoro lang_code group -> human language label used in VoiceInfo.
_CODE_TO_LANG: dict[str, str] = {
    "a": "en",
    "b": "en-gb",
    "h": "hi",
    "e": "es",
    "f": "fr",
    "i": "it",
    "p": "pt",
    "j": "ja",
    "z": "zh",
}

# Fixed Kokoro voice catalog (subset of the published voices, English + Hindi first).
_VOICES: list[str] = [
    # American English — female
    "af_heart", "af_bella", "af_nicole", "af_sarah", "af_sky", "af_aoede",
    "af_kore", "af_nova", "af_river",
    # American English — male
    "am_adam", "am_michael", "am_echo", "am_eric", "am_fenrir", "am_liam",
    "am_onyx", "am_puck",
    # British English — female / male
    "bf_alice", "bf_emma", "bf_isabella", "bf_lily",
    "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
    # Hindi — female / male
    "hf_alpha", "hf_beta", "hm_omega", "hm_psi",
]


def _voice_info(voice_id: str) -> VoiceInfo:
    code = voice_id[0]
    gender = {"f": "female", "m": "male"}.get(voice_id[1])
    return VoiceInfo(id=voice_id, language=_CODE_TO_LANG.get(code, code), gender=gender)


class KokoroEngine(TTSEngine):
    name = "kokoro"

    def __init__(self) -> None:
        self._pipelines: dict[str, KPipeline] = {}

    def load(self) -> None:
        # Build the default English pipeline up front so weights download once
        # and the first request isn't paying for it.
        self._pipeline(_LANG_TO_CODE["en"])

    def list_voices(self) -> list[VoiceInfo]:
        return [_voice_info(v) for v in _VOICES]

    def languages(self) -> list[str]:
        codes = {v[0] for v in _VOICES}
        return sorted(_CODE_TO_LANG[c] for c in codes if c in _CODE_TO_LANG)

    def _pipeline(self, lang_code: str) -> KPipeline:
        if lang_code not in self._pipelines:
            self._pipelines[lang_code] = KPipeline(
                lang_code=lang_code,
                repo_id=REPO_ID,
                device=settings.kokoro_device or None,
            )
        return self._pipelines[lang_code]

    def _resolve(self, req: TTSRequest) -> tuple[str, str]:
        """Resolve (voice, lang_code), validating they are consistent."""
        voice = req.voice or DEFAULT_VOICE
        if voice not in _VOICES:
            raise ValueError(
                f"Unknown voice '{voice}'. Known voices: {', '.join(_VOICES)}"
            )
        voice_code = voice[0]

        if req.language:
            lang_code = _LANG_TO_CODE.get(req.language.lower())
            if lang_code is None:
                raise ValueError(
                    f"Unsupported language '{req.language}'. "
                    f"Supported: {', '.join(sorted(_LANG_TO_CODE))}"
                )
            if req.voice and lang_code != voice_code:
                raise ValueError(
                    f"Voice '{voice}' does not match language '{req.language}'."
                )
        else:
            lang_code = voice_code
        return voice, lang_code

    def stream(self, req: TTSRequest):
        voice, lang_code = self._resolve(req)
        pipeline = self._pipeline(lang_code)

        produced = False
        for result in pipeline(req.text, voice=voice, speed=req.speed):
            audio = getattr(result, "audio", None)
            if audio is None and isinstance(result, (tuple, list)):
                audio = result[-1]
            if audio is None:
                continue
            if hasattr(audio, "detach"):  # torch tensor
                audio = audio.detach().cpu().numpy()
            produced = True
            yield np.asarray(audio, dtype=np.float32).reshape(-1), SAMPLE_RATE

        if not produced:
            raise RuntimeError("Kokoro returned no audio for the given input.")

    def synthesize(self, req: TTSRequest) -> tuple[np.ndarray, int]:
        chunks = [audio for audio, _ in self.stream(req)]
        return np.concatenate(chunks), SAMPLE_RATE
