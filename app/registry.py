"""Engine registry with lazy loading.

Engines are registered at import time (see app/engines/__init__.py) but their
heavy `load()` runs only on first use, so importing the app stays cheap.
"""

from __future__ import annotations

from app.engines.base import TTSEngine
from app.schemas import ModelInfo

_ENGINES: dict[str, TTSEngine] = {}
_LOADED: set[str] = set()


def register(engine: TTSEngine) -> None:
    if not getattr(engine, "name", None):
        raise ValueError("Engine must define a non-empty 'name'.")
    _ENGINES[engine.name] = engine


def names() -> list[str]:
    return sorted(_ENGINES)


def get(name: str) -> TTSEngine:
    engine = _ENGINES.get(name)
    if engine is None:
        raise KeyError(name)
    if name not in _LOADED:
        engine.load()
        _LOADED.add(name)
    return engine


def list_models() -> list[ModelInfo]:
    models: list[ModelInfo] = []
    for name in names():
        engine = _ENGINES[name]
        models.append(
            ModelInfo(
                name=name,
                languages=engine.languages(),
                voice_count=len(engine.list_voices()),
            )
        )
    return models
