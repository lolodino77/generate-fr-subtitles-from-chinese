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


# Réglages qui ne changent pas le contenu produit par l'étape : ils décident seulement si la vidéo est traitée
# (sonde). Les exclure évite de recalculer des vidéos déjà bien traitées quand on ajuste la sonde.
HASH_EXCLUDED = {"ocr": {"skip_when_no_subtitles", "no_subtitle_min_frames", "no_subtitle_clear_ratio"}}


def _canonical(value: Any) -> Any:
    """Forme canonique pour l'empreinte : 8 et 8.0 donnent la même empreinte."""
    if isinstance(value, dict):
        return {k: _canonical(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def step_hashes(cfg: AppConfig) -> dict[str, str]:
    """Empreinte cumulative de configuration pour chaque étape."""
    data = _canonical(cfg.to_dict())
    for section, keys in HASH_EXCLUDED.items():
        data[section] = {k: v for k, v in data[section].items() if k not in keys}
    hashes: dict[str, str] = {}
    acc: dict[str, Any] = {}
    for step in STEPS:
        for section in STEP_SECTIONS[step]:
            acc[section] = data[section]
        if step == "translation":  # le contenu du glossaire influence la traduction
            from video_ocr.translation.translator import glossary_path

            gp = glossary_path(cfg.translation)
            acc["glossary_sha"] = hashlib.sha256(gp.read_bytes()).hexdigest() if gp else ""
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
    no_subtitles: bool = False  # écartée d'après la sonde : pas de sous-titres incrustés, vidéo non traitée
    probe: dict[str, Any] = field(default_factory=dict)  # indicateurs de la sonde (diagnostic)

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
