from __future__ import annotations

from .base import Engine, EngineInfo

ENGINES = {
    "xtts": "timbre.engines.xtts:XTTSEngine",
    "demo": "timbre.engines.demo:DemoEngine",
}


def create_engine(name: str, device: str = "auto") -> Engine:
    if name not in ENGINES:
        raise ValueError(f"Unknown engine '{name}'. Choose one of: {', '.join(ENGINES)}")
    module_path, cls_name = ENGINES[name].split(":")
    import importlib

    cls = getattr(importlib.import_module(module_path), cls_name)
    return cls(device=device)


__all__ = ["Engine", "EngineInfo", "ENGINES", "create_engine"]
