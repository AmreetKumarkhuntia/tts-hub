"""tts-hub: pluggable self-hosted TTS server.

Silences third-party noise (PyTorch/Kokoro deprecation warnings and the
Hugging Face "unauthenticated request" notice) before those libraries load, so
the server console stays clean. These are library internals, not our code.
"""

import warnings

__version__ = "0.1.0"

warnings.filterwarnings("ignore", category=UserWarning, module=r"torch\..*")
warnings.filterwarnings("ignore", category=FutureWarning, module=r"torch\..*")
warnings.filterwarnings("ignore", category=UserWarning, module=r"kokoro\..*")

try:  # silence Hugging Face's "unauthenticated request" / download chatter
    from huggingface_hub.utils import logging as _hf_logging

    _hf_logging.set_verbosity_error()
except Exception:
    pass
