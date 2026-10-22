"""État de traitement par vidéo (reprise après interruption)."""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from video_ocr.config import AppConfig

def to_portable(path: str | Path, base: str | Path) -> str:
    """Chemin relatif à ``base`` (séparateurs « / ») pour que les résultats restent valides sur un autre PC.

    Si les deux chemins ne sont pas sur le même lecteur, le chemin absolu est conservé.
    """
    try:
        return Path(os.path.relpath(Path(path).resolve(), Path(base).resolve())).as_posix()
    except ValueError:
        return str(Path(path).resolve())


def from_portable(path: str, base: str | Path) -> Path:
    """Inverse de ``to_portable`` : chemin relatif résolu depuis ``base``."""
    p = Path(path)
    return p if p.is_absolute() else (Path(base) / p).resolve()


STEPS = ["ocr", "segments", "translation", "render", "export"]
# Sections de configuration dont dépend chaque étape (cumulatif : une étape dépend aussi des précédentes).
STEP_SECTIONS = {
    "ocr": ["sampling", "ocr"],
    "segments": ["segments"],
    "translation": ["translation"],
    "render": ["render"],
    "export": [],
}


def file_fingerprint(path: str | Path, full_limit: int = 512 * 1024 * 1024) -> str:
    """SHA-256 du fichier (début + fin + taille au-delà de ``full_limit``)."""
    path = Path(path)
    size = path.stat().st_size
    h = hashlib.sha256()
    h.update(str(size).encode())
    with path.open("rb") as fh:
        if size <= full_limit:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        else:
            h.update(fh.read(8 << 20))
            fh.seek(-8 << 20, 2)
            h.update(fh.read())
    return h.hexdigest()


def step_hashes(cfg: AppConfig) -> dict[str, str]:
    """Empreinte cumulative de configuration pour chaque étape."""
    data = cfg.to_dict()
    hashes: dict[str, str] = {}
    acc: dict[str, Any] = {}
    for step in STEPS:
        for section in STEP_SECTIONS[step]:
            acc[section] = data[section]
        hashes[step] = hashlib.sha256(json.dumps(acc, sort_keys=True).encode()).hexdigest()[:16]
    return hashes


@dataclass
class VideoState:
    source: str
    fingerprint: str = ""
    status: str = "pending"  # pending | running | complete | partial | failed | interrupted
    steps: dict[str, str] = field(default_factory=dict)  # étape -> empreinte de config utilisée
    error: str = ""
    warnings: list[str] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)
    updated: str = ""
    config: dict[str, Any] = field(default_factory=dict)

    def save(self, path: Path) -> None:
        self.updated = datetime.now().isoformat(timespec="seconds")
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path) -> "VideoState | None":
        if not path.exists():
            return None
        try:
            return cls(**json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, TypeError):
            return None

    def first_invalid_step(self, hashes: dict[str, str]) -> str | None:
        """Première étape à (re)faire, None si tout est à jour."""
        for step in STEPS:
            if self.steps.get(step) != hashes[step]:
                return step
        return None
