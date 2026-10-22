"""Sélection des vidéos locales (fichiers ou dossiers)."""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".m4v", ".webm", ".avi"}


def discover_videos(inputs: Iterable[str | Path], recursive: bool = False) -> tuple[list[Path], list[str]]:
    """Retourne (vidéos triées sans doublon, problèmes rencontrés).

    Les sorties de l'application (``*_bilingue.mp4``) ne sont jamais reprises comme sources.
    """
    videos: list[Path] = []
    problems: list[str] = []
    for item in inputs:
        path = Path(item)
        if path.is_dir():
            pattern = "**/*" if recursive else "*"
            found = [p for p in sorted(path.glob(pattern)) if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS]
            if not found:
                problems.append(f"Aucune vidéo dans le dossier {path}")
            videos.extend(found)
        elif path.is_file():
            if path.suffix.lower() in VIDEO_EXTENSIONS:
                videos.append(path)
            else:
                problems.append(f"Format non pris en charge : {path.name}")
        else:
            problems.append(f"Introuvable : {path}")
    unique: list[Path] = []
    seen: set[Path] = set()
    for v in videos:
        key = v.resolve()
        if key in seen or v.stem.endswith("_bilingue") or v.stem.endswith(".partial"):
            continue
        seen.add(key)
        unique.append(v)
    return unique, problems
