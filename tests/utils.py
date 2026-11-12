from __future__ import annotations

from pathlib import Path


def get_absolute_path(path: str) -> Path:
    return Path(__file__).parent.joinpath(path).resolve()
