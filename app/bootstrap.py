"""Wire concrete engines into the registry.

Call register_default_engines() once during application startup. Adding a new
model = import it here and register an instance.
"""

from __future__ import annotations

from app.engines.kokoro_engine import KokoroEngine
from app.registry import register


def register_default_engines() -> None:
    register(KokoroEngine())
