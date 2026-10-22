"""Recherche des polices sans chemin absolu propre à une machine.

Une police est désignée par un nom de fichier (ex. « segoeuib.ttf »). Elle est cherchée, dans l'ordre :
chemin relatif à la racine du projet, dossier ``fonts/`` du projet, polices Windows (%WINDIR%\\Fonts),
polices installées pour l'utilisateur (%LOCALAPPDATA%\\Microsoft\\Windows\\Fonts), puis dossiers Linux/macOS.
Un chemin absolu reste accepté (rétrocompatibilité).
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from video_ocr.config import PROJECT_ROOT


def font_dirs() -> list[Path]:
    dirs = [PROJECT_ROOT / "fonts"]
    windir = os.environ.get("WINDIR") or os.environ.get("SystemRoot")
    if windir:
        dirs.append(Path(windir) / "Fonts")
    local = os.environ.get("LOCALAPPDATA")
    if local:
        dirs.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
    dirs += [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), Path.home() / ".fonts",
             Path("/Library/Fonts"), Path("/System/Library/Fonts")]
    return dirs


@lru_cache(maxsize=64)
def find_font(name: str) -> Path | None:
    """Chemin d'une police à partir de son nom de fichier (ou d'un chemin), None si introuvable."""
    if not name:
        return None
    cand = Path(name)
    if cand.is_absolute():
        return cand if cand.exists() else find_font(cand.name)
    if (PROJECT_ROOT / cand).exists():
        return PROJECT_ROOT / cand
    for d in font_dirs():
        if (d / cand.name).exists():
            return d / cand.name
        if d.is_dir() and d.parts[0] == "/":  # arborescences Linux : recherche récursive
            found = next(d.rglob(cand.name), None)
            if found:
                return found
    return None


def first_font(*names: str) -> Path | None:
    """Première police trouvée parmi plusieurs noms."""
    for n in names:
        p = find_font(n)
        if p:
            return p
    return None
