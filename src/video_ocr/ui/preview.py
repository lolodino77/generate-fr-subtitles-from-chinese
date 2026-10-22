"""Aperçus : détections OCR sur quelques images et rendu bilingue à un instant donné."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from PIL import Image, ImageDraw

from video_ocr.config import AppConfig
from video_ocr.models import Segment, TextLine
from video_ocr.ocr.engines import OcrEngine, create_engine
from video_ocr.ocr.video_ocr import FrameOcr, roi_pixels
from video_ocr.rendering.layout import output_geometry, place
from video_ocr.rendering.overlay import compose_preview
from video_ocr.video.ffmpeg_tools import probe
from video_ocr.video.sampler import decode_geometry, grab_frame


def _to_pil(frame_bgr) -> Image.Image:  # type: ignore[no-untyped-def]
    return Image.fromarray(frame_bgr[:, :, ::-1])


def preview_ocr_frames(
    video: Path, cfg: AppConfig, times: list[float], engine: OcrEngine | None = None
) -> Iterator[tuple[float, Image.Image, list[TextLine]]]:
    """Image annotée (vert = ligne chinoise, orange = autre texte, bleu = ROI) pour chaque instant."""
    info = probe(video, cfg.ffmpeg_path)
    engine = engine or create_engine(cfg.ocr)
    geometry = decode_geometry(info, cfg.sampling.max_ocr_width)
    ocr = FrameOcr(engine, cfg, geometry)
    for t in times:
        if t > info.duration:
            continue
        frame = grab_frame(info, t, geometry, cfg.ffmpeg_path)
        obs = ocr(frame, t)
        full = _to_pil(grab_frame(info, t, None, cfg.ffmpeg_path))
        draw = ImageDraw.Draw(full)
        x0, y0, x1, y1 = roi_pixels(cfg.ocr.roi, info.width, info.height)
        draw.rectangle((x0, y0, x1 - 1, y1 - 1), outline=(60, 120, 255), width=3)
        for ln in obs.lines:
            draw.rectangle(ln.bbox, outline=(0, 230, 0) if ln.is_chinese else (255, 150, 0), width=3)
        yield t, full, obs.lines


def preview_bilingual(video: Path, cfg: AppConfig, segment: Segment) -> Image.Image:
    """Aperçu du rendu final au milieu d'un segment (avant export)."""
    info = probe(video, cfg.ffmpeg_path)
    t = (segment.start + segment.end) / 2
    frame = _to_pil(grab_frame(info, t, None, cfg.ffmpeg_path))
    geo = output_geometry(info.width, info.height, cfg.render)
    placement = place(segment.translation, geo, segment.block_bbox or segment.bbox, cfg.render) if segment.translation else None
    return compose_preview(frame, geo, placement, cfg.render)


def frame_from_output(video: Path, t: float, ffmpeg_path: str = "") -> Image.Image:
    """Image extraite de la vidéo exportée (vérification du fichier réel)."""
    info = probe(video, ffmpeg_path)
    return _to_pil(grab_frame(info, t, None, ffmpeg_path))
