"""Engine interface every TTS backend implements.

Adding a model = subclass TTSEngine, implement the four methods, and register an
instance in app/engines/__init__.py. The API and tester are driven entirely by
/models and /voices, so they need no changes when a new engine is added.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

import numpy as np

from app.schemas import TTSRequest, VoiceInfo


class TTSEngine(ABC):
    #: Stable identifier used in the API (e.g. "kokoro").
    name: str

    @abstractmethod
    def load(self) -> None:
        """Perform heavy one-time initialization (model weights, pipelines)."""

    @abstractmethod
    def list_voices(self) -> list[VoiceInfo]:
        """Return the catalog of available voices."""

    @abstractmethod
    def languages(self) -> list[str]:
        """Return the language codes this engine supports."""

    @abstractmethod
    def synthesize(self, req: TTSRequest) -> tuple[np.ndarray, int]:
        """Synthesize speech.

        Returns a tuple of (float32 mono waveform in [-1, 1], sample_rate).
        Raises ValueError for invalid voice/language requests.
        """

    def stream(self, req: TTSRequest) -> Iterator[tuple[np.ndarray, int]]:
        """Yield audio incrementally as (float32 mono chunk, sample_rate).

        Default implementation yields the full clip in one chunk. Engines whose
        backend produces audio progressively should override this to yield each
        chunk as soon as it is ready (lower time-to-first-audio).
        """
        yield self.synthesize(req)
