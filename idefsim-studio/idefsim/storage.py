"""Leitura e gravação de modelos (.idefsim = JSON)."""
from __future__ import annotations

import json
from pathlib import Path

from .model import Model

FILE_EXTENSION = ".idefsim"


def save_model(model: Model, path: str | Path) -> None:
    Path(path).write_text(json.dumps(model.to_dict(), ensure_ascii=False, indent=2),
                          encoding="utf-8")


def load_model(path: str | Path) -> Model:
    return Model.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
