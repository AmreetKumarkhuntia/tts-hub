"""Audio encoding helpers: float32 mono PCM -> WAV bytes."""

from __future__ import annotations

import io
import struct

import numpy as np
import soundfile as sf

# RIFF/data sizes are unknown when streaming, so we write the max value and let
# players read until the connection closes (standard "streaming WAV" trick).
_STREAMING_SIZE = 0xFFFFFFFF


def to_wav_bytes(samples: np.ndarray, sample_rate: int) -> bytes:
    """Encode a float32 mono waveform in [-1, 1] as a 16-bit PCM WAV."""
    audio = np.asarray(samples, dtype=np.float32)
    audio = np.clip(audio, -1.0, 1.0)
    buffer = io.BytesIO()
    sf.write(buffer, audio, sample_rate, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


def duration_secs(samples: np.ndarray, sample_rate: int) -> float:
    if sample_rate <= 0:
        return 0.0
    return float(len(samples)) / float(sample_rate)


def to_pcm16_bytes(samples: np.ndarray) -> bytes:
    """Encode a float32 mono waveform in [-1, 1] as little-endian 16-bit PCM."""
    audio = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    return (audio * 32767.0).astype("<i2").tobytes()


def streaming_wav_header(
    sample_rate: int, channels: int = 1, bits_per_sample: int = 16
) -> bytes:
    """A 44-byte PCM WAV header with placeholder sizes, for streamed audio.

    Followed by little-endian PCM frames (see to_pcm16_bytes). The chunk/data
    sizes are set to the max so players don't wait for a known length.
    """
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    return b"".join(
        [
            b"RIFF",
            struct.pack("<I", _STREAMING_SIZE),
            b"WAVE",
            b"fmt ",
            struct.pack(
                "<IHHIIHH",
                16,  # fmt chunk size
                1,  # PCM
                channels,
                sample_rate,
                byte_rate,
                block_align,
                bits_per_sample,
            ),
            b"data",
            struct.pack("<I", _STREAMING_SIZE),
        ]
    )
