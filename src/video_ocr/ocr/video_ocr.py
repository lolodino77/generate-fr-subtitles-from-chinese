"""OCR d'une vidéo : échantillonnage, saut des images inchangées et affinage des changements de texte."""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

import cv2
import numpy as np

from video_ocr.config import AppConfig
from video_ocr.models import FrameObservation, TextBox, TextLine, VideoInfo
from video_ocr.ocr.engines import OcrEngine
from video_ocr.ocr.lines import boxes_to_lines, union_bbox
from video_ocr.ocr.text_utils import similarity
from video_ocr.video.sampler import FrameGeometry, decode_geometry, iter_frames

log = logging.getLogger(__name__)

ProgressCb = Callable[[float, str], None]


class Cancelled(Exception):
    """Traitement annulé par l'utilisateur."""


@dataclass
class OcrStats:
    sampled: int = 0
    ocr_calls: int = 0
    reused: int = 0
    refined: int = 0
    seconds: float = 0.0
    engine: str = ""
    extra: dict[str, float] = field(default_factory=dict)


def roi_pixels(roi: list[float] | None, w: int, h: int) -> tuple[int, int, int, int]:
    """Convertit une ROI fractionnaire [x0, y0, x1, y1] en pixels (image entière si None)."""
    if not roi:
        return 0, 0, w, h
    x0, y0, x1, y1 = roi
    px = (int(max(0.0, x0) * w), int(max(0.0, y0) * h), int(min(1.0, x1) * w), int(min(1.0, y1) * h))
    if px[2] - px[0] < 16 or px[3] - px[1] < 16:
        raise ValueError(f"Région OCR trop petite : {roi}")
    return px


class FrameOcr:
    """OCR d'une image (ROI, remise à l'échelle des coordonnées vers la vidéo d'origine)."""

    def __init__(self, engine: OcrEngine, cfg: AppConfig, geometry: FrameGeometry, roi: list[float] | None = None) -> None:
        self.engine = engine
        self.cfg = cfg
        self.geometry = geometry
        self.roi = roi_pixels(roi if roi is not None else cfg.ocr.roi, geometry.width, geometry.height)
        self.calls = 0

    def __call__(self, frame: np.ndarray, t: float) -> FrameObservation:
        x0, y0, x1, y1 = self.roi
        boxes = self.engine.recognize(np.ascontiguousarray(frame[y0:y1, x0:x1]))
        self.calls += 1
        s = self.geometry.scale
        scaled = [
            TextBox(b.text, b.score, (
                int((b.bbox[0] + x0) * s), int((b.bbox[1] + y0) * s),
                int((b.bbox[2] + x0) * s), int((b.bbox[3] + y0) * s),
            ))
            for b in boxes
        ]
        lines = boxes_to_lines(scaled, self.cfg.ocr.min_score, self.cfg.ocr.min_cjk_ratio)
        return FrameObservation(t=round(t, 3), lines=lines)


def chinese_text(obs: FrameObservation) -> str:
    """Texte chinois brut d'une observation (toutes lignes chinoises, de haut en bas)."""
    return "\n".join(ln.text for ln in obs.lines if ln.is_chinese)


def same_text(a: FrameObservation, b: FrameObservation, threshold: float) -> bool:
    """Vrai si chaque ligne chinoise de l'une a un équivalent dans l'autre (et réciproquement).

    La comparaison ligne à ligne évite qu'un texte fixe (filigrane) masque l'apparition d'une phrase courte.
    """
    la = [ln.text for ln in a.lines if ln.is_chinese]
    lb = [ln.text for ln in b.lines if ln.is_chinese]
    if len(la) != len(lb):
        return False
    remaining = list(lb)
    for text in la:
        best = max(remaining, key=lambda other: similarity(text, other), default=None)
        if best is None or similarity(text, best) < threshold:
            return False
        remaining.remove(best)
    return True


def _small_gray(frame: np.ndarray) -> np.ndarray:
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.resize(g, (g.shape[1] // 4, g.shape[0] // 4), interpolation=cv2.INTER_AREA).astype(np.int16)


def _unchanged(prev: np.ndarray, cur: np.ndarray, lines: list[TextLine], scale: float, threshold: float) -> bool:
    """Image jugée identique si la zone de texte précédente ET l'image globale ont peu changé."""
    if float(np.mean(np.abs(prev - cur))) > threshold * 1.5:
        return False
    box = union_bbox(ln.bbox for ln in lines)
    if box is None:
        return True
    f = 4 * scale  # coordonnées d'origine -> image réduite
    x0, y0, x1, y1 = (int(box[0] / f), int(box[1] / f), int(np.ceil(box[2] / f)), int(np.ceil(box[3] / f)))
    region_prev, region_cur = prev[y0:y1, x0:x1], cur[y0:y1, x0:x1]
    if region_prev.size == 0:
        return True
    return float(np.mean(np.abs(region_prev - region_cur))) <= threshold


def detect_subtitle_band(
    info: VideoInfo, cfg: AppConfig, engine: OcrEngine, geometry: FrameGeometry, max_frames: int = 20
) -> list[float] | None:
    """Premier passage rapide : repère la zone des sous-titres sur quelques images de toute la vidéo.

    Renvoie une ROI [0, y0, 1, y1] (fractions) couvrant la ligne chinoise et les lignes voisines
    (ex. thaï dessous), ou None si aucun sous-titre plausible n'est trouvé (OCR de l'image entière).
    Limiter l'OCR à cette bande réduit fortement le coût sur les vidéos riches en texte de scène.
    """
    from video_ocr.ocr.analysis import dominant_zone, find_static_lines

    ocr = FrameOcr(engine, cfg, geometry, roi=[0.0, 0.0, 1.0, 1.0])
    fps = min(0.5, max_frames / max(info.duration, 1.0))
    sample = [ocr(frame, t) for t, frame in iter_frames(info, fps, geometry, cfg.ffmpeg_path)][:max_frames + 1]
    static, _ = find_static_lines(sample, cfg.ocr) if len(sample) >= 6 else (set(), [])
    zone, line_height = dominant_zone(sample, info.height, static, info.width, cfg.ocr.center_tolerance)
    if zone is None or not line_height:
        return None
    lh = line_height / info.height
    y0, y1 = max(0.0, zone - 2.5 * lh), min(1.0, zone + 5.0 * lh)
    if y1 - y0 < 0.2:  # bande minimale pour tolérer de petits déplacements des sous-titres
        mid = (y0 + y1) / 2
        y0, y1 = max(0.0, mid - 0.1), min(1.0, mid + 0.1)
    return [0.0, round(y0, 3), 1.0, round(y1, 3)]


def run_video_ocr(
    info: VideoInfo,
    cfg: AppConfig,
    engine: OcrEngine,
    progress: ProgressCb | None = None,
    cancel: threading.Event | None = None,
) -> tuple[list[FrameObservation], OcrStats]:
    """OCR de toute la vidéo. Retourne les observations triées par temps."""
    import time

    t_start = time.perf_counter()
    sc = cfg.sampling
    geometry = decode_geometry(info, sc.max_ocr_width)
    stats_roi: list[float] | None = cfg.ocr.roi
    if stats_roi is None and cfg.ocr.auto_roi:
        if progress is not None:
            progress(0.0, "Détection de la zone des sous-titres")
        stats_roi = detect_subtitle_band(info, cfg, engine, geometry)
        log.info("Zone d'OCR automatique : %s", stats_roi or "image entière")
    ocr = FrameOcr(engine, cfg, geometry, roi=stats_roi)
    dense_fps = max(sc.dense_fps, 1.0 / sc.ocr_interval_s)
    step = max(1, int(round(sc.ocr_interval_s * dense_fps)))
    stats = OcrStats(engine=getattr(engine, "label", engine.name))
    if stats_roi is not None:
        stats.extra.update({"roi_y0": stats_roi[1], "roi_y1": stats_roi[3]})
    observations: list[FrameObservation] = []
    buffer: list[tuple[float, np.ndarray]] = []  # images décodées depuis le dernier échantillon OCR
    last_obs: FrameObservation | None = None
    last_gray: np.ndarray | None = None
    thr = cfg.segments.similarity_threshold
    max_refine_calls = max(1, int(np.ceil(np.log2(step + 1)))) * 2

    def refine(frames: list[tuple[float, np.ndarray]], lo: FrameObservation, hi: FrameObservation, budget: list[int]) -> None:
        """Bissection entre deux observations dont le texte diffère (frames = images strictement entre les deux)."""
        if not frames or budget[0] <= 0:
            return
        mid = len(frames) // 2
        t_mid, f_mid = frames[mid]
        obs_mid = ocr(f_mid, t_mid)
        obs_mid.refined = True
        budget[0] -= 1
        stats.refined += 1
        observations.append(obs_mid)
        if same_text(lo, obs_mid, thr):
            refine(frames[mid + 1:], obs_mid, hi, budget)
        elif same_text(obs_mid, hi, thr):
            refine(frames[:mid], lo, obs_mid, budget)
        else:  # état intermédiaire (ex. phrase courte) : affiner des deux côtés
            refine(frames[:mid], lo, obs_mid, budget)
            refine(frames[mid + 1:], obs_mid, hi, budget)

    def frames_with_last_flag():  # type: ignore[no-untyped-def]
        """Marque la dernière image décodée pour qu'elle soit toujours analysée (fin du dernier sous-titre)."""
        prev = None
        for item in iter_frames(info, dense_fps, geometry, cfg.ffmpeg_path):
            if prev is not None:
                yield prev, False
            prev = item
        if prev is not None:
            yield prev, True

    next_sample = -1.0
    tolerance = 0.5 / max(info.fps, 1.0)
    for (t, frame), is_last in frames_with_last_flag():
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        buffer.append((t, frame))
        if t >= next_sample - tolerance or is_last:
            next_sample = t + sc.ocr_interval_s
            stats.sampled += 1
            gray = _small_gray(frame)
            if (
                sc.skip_unchanged and last_obs is not None and last_gray is not None
                and _unchanged(last_gray, gray, last_obs.lines, geometry.scale, sc.unchanged_threshold)
            ):
                obs = FrameObservation(t=round(t, 3), lines=list(last_obs.lines), reused=True)
                stats.reused += 1
            else:
                obs = ocr(frame, t)
                last_gray = gray
            if sc.refine_boundaries and last_obs is not None and not same_text(last_obs, obs, thr):
                between = [item for item in buffer[:-1] if last_obs.t < item[0] < t]
                refine(between, last_obs, obs, [max_refine_calls])
            observations.append(obs)
            last_obs = obs
            buffer = [(t, frame)]
            if progress is not None and info.duration > 0:
                progress(min(1.0, t / info.duration), f"OCR {t:.1f}/{info.duration:.1f} s")
    observations.sort(key=lambda o: o.t)
    stats.ocr_calls = ocr.calls
    stats.seconds = time.perf_counter() - t_start
    log.info(
        "OCR %s : %d échantillons, %d appels OCR, %d réutilisés, %d affinages, %.1f s",
        info.path, stats.sampled, stats.ocr_calls, stats.reused, stats.refined, stats.seconds,
    )
    return observations, stats
