"""Génération de la vidéo bilingue : un seul réencodage vidéo, audio copié sans réencodage.

Principe : chaque segment traduit est dessiné dans une image PNG transparente de la taille de
sortie. Ces images forment une séquence ``ffconcat`` (durées = périodes d'affichage, images vides
entre les segments) superposée à la vidéo par le filtre ``overlay``. Les sous-titres chinois
incrustés dans l'image source sont donc conservés tels quels.
"""
from __future__ import annotations

import logging
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from video_ocr.config import RenderConfig
from video_ocr.models import Segment, VideoInfo
from video_ocr.rendering.layout import OutputGeometry, Placement, output_geometry, place
from video_ocr.rendering.overlay import render_overlay
from video_ocr.video.ffmpeg_tools import CREATE_NO_WINDOW, FFmpegError, find_binary

log = logging.getLogger(__name__)

AUDIO_COPY_OK = {"aac", "mp3", "alac", "opus", "ac3", "eac3", "flac"}


@dataclass
class RenderResult:
    output: Path
    geometry: OutputGeometry
    placements: dict[int, Placement] = field(default_factory=dict)
    audio_mode: str = ""
    seconds: float = 0.0


def compute_placements(segments: list[Segment], info: VideoInfo, cfg: RenderConfig) -> tuple[OutputGeometry, dict[int, Placement]]:
    """Placement de chaque segment possédant une traduction."""
    geo = output_geometry(info.width, info.height, cfg)
    placements = {
        seg.index: place(seg.translation, geo, seg.block_bbox or seg.bbox, cfg)
        for seg in segments if seg.translation
    }
    return geo, placements


def _quote(name: str) -> str:
    return "'" + name.replace("'", "'\\''") + "'"


def write_overlay_sequence(
    segments: list[Segment], info: VideoInfo, cfg: RenderConfig, work_dir: Path
) -> tuple[Path, OutputGeometry, dict[int, Placement]]:
    """Écrit les PNG et le fichier ``overlay.ffconcat`` (chemins relatifs, UTF-8)."""
    work_dir.mkdir(parents=True, exist_ok=True)
    geo, placements = compute_placements(segments, info, cfg)
    blank = render_overlay(work_dir / "blank.png", geo, None, cfg).name
    entries: list[tuple[str, float]] = []
    cursor = 0.0
    for seg in sorted(segments, key=lambda s: s.start):
        if seg.index not in placements:
            continue
        start, end = max(seg.start, cursor), min(seg.end, info.duration)
        if end - start < 0.01:
            continue
        if start - cursor >= 0.001:
            entries.append((blank, start - cursor))
        name = render_overlay(work_dir / f"seg_{seg.index:04d}.png", geo, placements[seg.index], cfg).name
        entries.append((name, end - start))
        cursor = end
    entries.append((blank, max(0.04, info.duration - cursor + 1.0)))
    lines = ["ffconcat version 1.0"]
    for name, dur in entries:
        lines += [f"file {_quote(name)}", f"duration {dur:.3f}"]
    lines.append(f"file {_quote(entries[-1][0])}")  # le dernier fichier doit être répété pour que sa durée soit prise en compte
    concat = work_dir / "overlay.ffconcat"
    concat.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return concat, geo, placements


def _build_cmd(info: VideoInfo, concat: Path, geo: OutputGeometry, cfg: RenderConfig, out: Path, audio: str, ffmpeg: str) -> list[str]:
    pad = f"pad={geo.width}:{geo.height}:0:0:color=black," if geo.band_height else ""
    fc = (
        f"[0:v]{pad}format=yuv420p[base];[1:v]format=rgba[ov];"
        f"[base][ov]overlay=0:0:eof_action=pass:format=auto,format=yuv420p[v]"
    )
    cmd = [
        ffmpeg, "-y", "-nostdin", "-v", "error", "-progress", "pipe:1", "-i", info.path,
        "-f", "concat", "-safe", "0", "-i", str(concat), "-filter_complex", fc,
        "-map", "[v]", "-c:v", "libx264", "-preset", cfg.preset, "-crf", str(cfg.crf),
        "-pix_fmt", "yuv420p", "-fps_mode", "passthrough", "-movflags", "+faststart",
    ]
    if info.has_audio:
        cmd += ["-map", "0:a:0"]
        cmd += ["-c:a", "copy"] if audio == "copy" else ["-c:a", "aac", "-b:a", "160k"]
    cmd += ["-t", f"{info.duration:.3f}", str(out)]
    return cmd


def _run_ffmpeg(cmd: list[str], duration: float, progress: Callable[[float, str], None] | None, cancel: threading.Event | None) -> None:
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=CREATE_NO_WINDOW)
    assert proc.stdout is not None
    stderr_chunks: list[bytes] = []
    reader = threading.Thread(target=lambda: stderr_chunks.append(proc.stderr.read() if proc.stderr else b""), daemon=True)
    reader.start()
    for raw in proc.stdout:
        if cancel is not None and cancel.is_set():
            proc.kill()
            proc.wait()
            raise InterruptedError("Rendu annulé")
        line = raw.decode("utf-8", "replace").strip()
        if line.startswith("out_time_us=") and progress is not None and duration > 0:
            try:
                t = int(line.split("=", 1)[1]) / 1e6
                progress(min(1.0, t / duration), f"Encodage {t:.1f}/{duration:.1f} s")
            except ValueError:
                pass
    proc.wait()
    reader.join(timeout=5)
    if proc.returncode != 0:
        err = b"".join(stderr_chunks).decode("utf-8", "replace")[-2000:]
        raise FFmpegError(f"Échec du rendu FFmpeg ({proc.returncode}) :\n{err}")


def render_bilingual_video(
    segments: list[Segment],
    info: VideoInfo,
    cfg: RenderConfig,
    output: str | Path,
    work_dir: str | Path,
    ffmpeg_path: str = "",
    progress: Callable[[float, str], None] | None = None,
    cancel: threading.Event | None = None,
) -> RenderResult:
    """Produit la vidéo finale dans un fichier temporaire puis le renomme (jamais de fichier final partiel)."""
    t0 = time.perf_counter()
    output = Path(output)
    if output.resolve() == Path(info.path).resolve():
        raise ValueError("Le fichier de sortie ne peut pas être la vidéo source")
    concat, geo, placements = write_overlay_sequence(segments, info, cfg, Path(work_dir))
    ffmpeg = find_binary("ffmpeg", ffmpeg_path)
    tmp = output.with_name(output.stem + ".partial" + output.suffix)
    audio = "copy" if info.audio_codec in AUDIO_COPY_OK else "aac"
    try:
        _run_ffmpeg(_build_cmd(info, concat, geo, cfg, tmp, audio, ffmpeg), info.duration, progress, cancel)
    except FFmpegError:
        if not info.has_audio or audio == "aac":
            raise
        log.warning("Copie audio impossible, réencodage AAC")
        audio = "aac"
        _run_ffmpeg(_build_cmd(info, concat, geo, cfg, tmp, audio, ffmpeg), info.duration, progress, cancel)
    tmp.replace(output)
    return RenderResult(output, geo, placements, audio if info.has_audio else "none", time.perf_counter() - t0)
