"""Localisation et exécution de FFmpeg / FFprobe."""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

from video_ocr.models import VideoInfo

log = logging.getLogger(__name__)

# Sous Windows, évite l'ouverture d'une console pour chaque sous-processus.
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


class FFmpegError(RuntimeError):
    """Erreur d'exécution de FFmpeg ou FFprobe."""


def find_binary(name: str, configured: str = "") -> str:
    """Trouve ``ffmpeg``/``ffprobe`` : chemin configuré, environnement Conda actif, puis PATH."""
    if configured:
        cand = Path(configured)
        if cand.is_dir():
            cand = cand / (name + (".exe" if os.name == "nt" else ""))
        elif cand.name.lower().startswith("ffmpeg") and name != "ffmpeg":
            cand = cand.with_name(cand.name.lower().replace("ffmpeg", name))
        if cand.exists():
            return str(cand)
    exe = name + (".exe" if os.name == "nt" else "")
    prefix = Path(sys.prefix)
    for sub in ("Library/bin", "bin", "Scripts"):
        cand = prefix / sub / exe
        if cand.exists():
            return str(cand)
    found = shutil.which(name)
    if found:
        return found
    raise FFmpegError(
        f"{name} introuvable. Installez-le dans l'environnement : conda install -n video_ocr -c conda-forge ffmpeg"
    )


def run(cmd: list[str], timeout: float | None = None) -> subprocess.CompletedProcess[bytes]:
    """Exécute une commande et lève ``FFmpegError`` avec la fin de stderr en cas d'échec."""
    log.debug("Commande : %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout, creationflags=CREATE_NO_WINDOW)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace")[-2000:]
        raise FFmpegError(f"Échec ({proc.returncode}) : {' '.join(cmd[:3])}...\n{err}")
    return proc


def _parse_rate(rate: str | None) -> float:
    if not rate or rate in ("0/0", "N/A"):
        return 0.0
    try:
        return float(Fraction(rate))
    except (ValueError, ZeroDivisionError):
        return 0.0


def probe(path: str | Path, ffmpeg_path: str = "") -> VideoInfo:
    """Lit les métadonnées d'une vidéo. Lève ``FFmpegError`` si le fichier est invalide."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Vidéo introuvable : {path}")
    cmd = [
        find_binary("ffprobe", ffmpeg_path), "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    data = json.loads(run(cmd, timeout=60).stdout.decode("utf-8", errors="replace"))
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video" and s.get("disposition", {}).get("attached_pic", 0) == 0), None)
    if video is None:
        raise FFmpegError(f"Aucun flux vidéo dans {path.name}")
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    rotation = 0
    for sd in video.get("side_data_list", []) or []:
        if "rotation" in sd:
            rotation = int(round(float(sd["rotation"]))) % 360
    if "rotate" in video.get("tags", {}):
        rotation = int(video["tags"]["rotate"]) % 360
    width, height = int(video["width"]), int(video["height"])
    if rotation in (90, 270):
        width, height = height, width
    duration = float(video.get("duration") or data.get("format", {}).get("duration") or 0.0)
    if duration <= 0:
        raise FFmpegError(f"Durée invalide pour {path.name}")
    fps = _parse_rate(video.get("avg_frame_rate")) or _parse_rate(video.get("r_frame_rate")) or 30.0
    n_frames = int(video["nb_frames"]) if str(video.get("nb_frames", "")).isdigit() else None
    return VideoInfo(
        path=str(path), duration=duration, width=width, height=height, fps=fps,
        has_audio=audio is not None, video_codec=video.get("codec_name", ""),
        audio_codec=(audio or {}).get("codec_name", ""), rotation=rotation, n_frames=n_frames,
    )
