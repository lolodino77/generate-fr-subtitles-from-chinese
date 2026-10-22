"""Décodage des images d'une vidéo via un tube FFmpeg (sans fichiers temporaires)."""
from __future__ import annotations

import logging
import queue
import re
import subprocess
import threading
from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np

from video_ocr.models import VideoInfo
from video_ocr.video.ffmpeg_tools import CREATE_NO_WINDOW, FFmpegError, find_binary, run

log = logging.getLogger(__name__)


@dataclass
class FrameGeometry:
    """Taille des images décodées et facteur pour revenir aux pixels d'origine."""

    width: int
    height: int
    scale: float  # coordonnée d'origine = coordonnée décodée * scale


def decode_geometry(info: VideoInfo, max_width: int) -> FrameGeometry:
    """Calcule la taille de décodage (largeur limitée, dimensions paires)."""
    if max_width and info.width > max_width:
        w = max_width - (max_width % 2)
        h = int(round(info.height * w / info.width / 2)) * 2
    else:
        w, h = info.width, info.height
    return FrameGeometry(w, h, info.width / w)


_PTS_RE = re.compile(rb"Parsed_showinfo.*?\bpts_time:\s*(-?[\d.]+)")


def iter_frames(
    info: VideoInfo, fps: float, geometry: FrameGeometry, ffmpeg_path: str = ""
) -> Iterator[tuple[float, np.ndarray]]:
    """Itère sur ``(t, image BGR)`` d'images source réelles espacées d'environ ``1/fps`` seconde.

    Les images sont sélectionnées (filtre ``select``, sans duplication ni interpolation) et ``t`` est
    l'horodatage de présentation exact de l'image source, lu via ``showinfo``.
    """
    min_gap = max(0.0, 1.0 / fps - 0.5 / max(info.fps, 1.0))
    vf = f"select='isnan(prev_selected_t)+gte(t-prev_selected_t,{min_gap:.6f})',showinfo"
    if geometry.scale != 1.0:
        vf += f",scale={geometry.width}:{geometry.height}:flags=area"
    cmd = [
        find_binary("ffmpeg", ffmpeg_path), "-v", "info", "-nostats", "-nostdin", "-i", info.path, "-vf", vf,
        "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "bgr24", "-an", "-sn", "pipe:1",
    ]
    frame_bytes = geometry.width * geometry.height * 3
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=CREATE_NO_WINDOW)
    times: queue.Queue[float] = queue.Queue()
    tail: list[bytes] = []

    def read_stderr() -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            m = _PTS_RE.search(line)
            if m:
                times.put(float(m.group(1)))
            else:
                tail.append(line)
                del tail[:-20]

    reader = threading.Thread(target=read_stderr, daemon=True)
    reader.start()
    n = 0
    try:
        assert proc.stdout is not None
        while True:
            buf = proc.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            frame = np.frombuffer(buf, dtype=np.uint8).reshape(geometry.height, geometry.width, 3)
            try:
                t = times.get(timeout=30)
            except queue.Empty:
                t = n / fps
                log.warning("Horodatage indisponible pour l'image %d, estimation %.3f s", n, t)
            yield t, frame
            n += 1
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        reader.join(timeout=5)
        if n == 0:
            raise FFmpegError(f"Aucune image décodée pour {info.path} : {b''.join(tail).decode('utf-8', 'replace')[-800:]}")


def grab_frame(info: VideoInfo, t: float, geometry: FrameGeometry | None = None, ffmpeg_path: str = "") -> np.ndarray:
    """Extrait une seule image (BGR) à l'instant ``t`` (recherche précise)."""
    geometry = geometry or FrameGeometry(info.width, info.height, 1.0)
    t = max(0.0, min(t, max(0.0, info.duration - 0.05)))
    cmd = [find_binary("ffmpeg", ffmpeg_path), "-v", "error", "-nostdin", "-ss", f"{t:.3f}", "-i", info.path, "-frames:v", "1"]
    if geometry.scale != 1.0:
        cmd += ["-vf", f"scale={geometry.width}:{geometry.height}:flags=area"]
    cmd += ["-f", "rawvideo", "-pix_fmt", "bgr24", "pipe:1"]
    buf = run(cmd, timeout=60).stdout
    expected = geometry.width * geometry.height * 3
    if len(buf) < expected:
        raise FFmpegError(f"Image introuvable à t={t:.2f}s")
    return np.frombuffer(buf[:expected], dtype=np.uint8).reshape(geometry.height, geometry.width, 3).copy()
