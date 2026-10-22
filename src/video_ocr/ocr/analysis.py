"""Analyse au niveau de la vidéo : distinguer les sous-titres des autres textes visibles.

Heuristiques (toutes configurables) :
1. Les textes chinois présents sur presque toute la vidéo (titre, filigrane) sont écartés.
2. La zone verticale où apparaît le plus souvent du chinois est la zone des sous-titres.
3. Dans chaque image, le bloc chinois le plus proche de cette zone est le sous-titre ;
   son rectangle est étendu aux lignes voisines non chinoises (ex. thaï) pour ne pas les masquer.
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from video_ocr.config import OcrConfig
from video_ocr.models import BBox, FrameObservation, TextLine
from video_ocr.ocr.lines import expand_with_neighbours, group_blocks, union_bbox
from video_ocr.ocr.text_utils import comparison_key, count_cjk

log = logging.getLogger(__name__)


@dataclass
class ZoneAnalysis:
    zone_center: float | None  # centre vertical de la zone des sous-titres (fraction de hauteur)
    static_keys: set[str] = field(default_factory=set)
    static_texts: list[str] = field(default_factory=list)
    frames_with_subtitle: int = 0
    frames_total: int = 0


def find_static_lines(observations: list[FrameObservation], cfg: OcrConfig) -> tuple[set[str], list[str]]:
    """Lignes chinoises présentes dans une proportion d'images >= ``static_presence_ratio``."""
    if not cfg.remove_static_text or len(observations) < 6:
        return set(), []
    counter: Counter[str] = Counter()
    sample: dict[str, str] = {}
    for obs in observations:
        keys = {comparison_key(ln.text) for ln in obs.lines if ln.is_chinese}
        for key in keys:
            if key:
                counter[key] += 1
                sample.setdefault(key, next(ln.text for ln in obs.lines if ln.is_chinese and comparison_key(ln.text) == key))
    n = len(observations)
    static = {k for k, c in counter.items() if c / n >= cfg.static_presence_ratio}
    if not static:
        return set(), []
    # Garde-fou : s'il n'existe aucun autre texte chinois, ce texte permanent est le sous-titre lui-même
    # (vidéo d'une seule phrase). Une seule phrase courte ailleurs suffit à le considérer comme fixe.
    remaining = sum(
        1 for obs in observations
        if any(ln.is_chinese and comparison_key(ln.text) not in static for ln in obs.lines)
    )
    if remaining == 0:
        return set(), []
    return static, [sample[k] for k in static]


def _is_centered(box: BBox, width: int | None, tolerance: float) -> bool:
    """Bloc centré horizontalement (les sous-titres le sont ; les enseignes de la scène rarement)."""
    if width is None or tolerance <= 0:
        return True
    return abs((box[0] + box[2]) / 2 - width / 2) <= tolerance * width


def dominant_zone(
    observations: list[FrameObservation], height: int, static: set[str], width: int | None = None, center_tolerance: float = 0.0
) -> tuple[float | None, float | None]:
    """Centre vertical (fraction) le plus fréquent des lignes chinoises centrées, et hauteur de ligne typique (px)."""
    centers: list[float] = []
    weights: list[float] = []
    heights: list[float] = []
    for obs in observations:
        for ln in obs.lines:
            if ln.is_chinese and comparison_key(ln.text) not in static and _is_centered(ln.bbox, width, center_tolerance):
                centers.append(((ln.bbox[1] + ln.bbox[3]) / 2) / height)
                weights.append(float(count_cjk(ln.text)))
                heights.append(float(ln.bbox[3] - ln.bbox[1]))
    if not centers:
        return None, None
    hist, edges = np.histogram(centers, bins=40, range=(0.0, 1.0), weights=weights)
    smooth = np.convolve(hist, np.ones(3) / 3, mode="same")
    peak = int(np.argmax(smooth))
    lo, hi = edges[max(0, peak - 1)], edges[min(len(edges) - 1, peak + 2)]
    in_peak = [(c, w, h) for c, w, h in zip(centers, weights, heights) if lo <= c <= hi]
    zone = float(sum(c * w for c, w, _ in in_peak) / sum(w for _, w, _ in in_peak))
    # Médiane haute pondérée par le nombre de caractères (en cas d'égalité, le texte le plus grand l'emporte)
    hs = np.array([h for _, _, h in in_peak])
    ws = np.array([w for _, w, _ in in_peak])
    order = np.argsort(hs)
    cum = np.cumsum(ws[order])
    idx = min(len(hs) - 1, int(np.searchsorted(cum, cum[-1] / 2, side="right")))
    return zone, float(hs[order][idx])


def select_subtitle(
    obs: FrameObservation, zone: float | None, height: int, static: set[str], cfg: OcrConfig,
    width: int | None = None, line_height: float | None = None,
) -> None:
    """Renseigne ``subtitle_text`` / ``subtitle_bbox`` / ``block_bbox`` de l'observation.

    Un bloc candidat doit être dans la zone dominante, centré horizontalement et avoir une hauteur
    de caractères proche de celle des sous-titres de la vidéo (rejette enseignes et menus filmés).
    """
    def plausible(ln: TextLine) -> bool:
        if not _is_centered(ln.bbox, width, cfg.center_tolerance):
            return False
        h = ln.bbox[3] - ln.bbox[1]
        return not line_height or cfg.line_height_range[0] * line_height <= h <= cfg.line_height_range[1] * line_height

    chinese = [ln for ln in obs.lines if ln.is_chinese and comparison_key(ln.text) not in static and plausible(ln)]
    others = [ln for ln in obs.lines if not ln.is_chinese]
    obs.subtitle_text, obs.subtitle_score, obs.subtitle_bbox, obs.block_bbox = "", 0.0, None, None
    if not chinese:
        return
    blocks = group_blocks(chinese)

    def center(block: list[TextLine]) -> float:
        box = union_bbox(ln.bbox for ln in block)
        assert box is not None
        return ((box[1] + box[3]) / 2) / height

    if zone is not None:
        candidates = [b for b in blocks if abs(center(b) - zone) <= cfg.zone_tolerance]
        if not candidates:
            return
        block = min(candidates, key=lambda b: abs(center(b) - zone))
    else:
        block = max(blocks, key=lambda b: sum(count_cjk(ln.text) for ln in b))
    block.sort(key=lambda ln: ln.bbox[1])
    # Une ligne « chinoise » nettement moins sûre que la meilleure du bloc est en général une autre
    # écriture (ex. thaï) lue à tort comme des idéogrammes : elle est traitée comme ligne non chinoise.
    best = max(ln.score for ln in block)
    dropped = [ln for ln in block if ln.score < best - cfg.block_score_drop]
    block = [ln for ln in block if ln not in dropped]
    others = others + dropped
    obs.subtitle_text = "\n".join(ln.text for ln in block)
    n = sum(max(1, len(ln.text)) for ln in block)
    obs.subtitle_score = sum(ln.score * max(1, len(ln.text)) for ln in block) / n
    obs.subtitle_bbox = union_bbox(ln.bbox for ln in block)
    assert obs.subtitle_bbox is not None
    block_line_height = float(np.median([ln.bbox[3] - ln.bbox[1] for ln in block]))
    obs.block_bbox = expand_with_neighbours(obs.subtitle_bbox, others, block_line_height)


def _apply_typical_extension(
    observations: list[FrameObservation], height: int, line_height: float | None, q: float = 75.0
) -> None:
    """La mise en page (chinois + lignes voisines, ex. 2 lignes thaïes) est constante dans une vidéo.

    L'extension du bloc sous le chinois, rapportée à la hauteur du chinois, est apprise sur toute la
    vidéo (percentile ``q``) et imposée comme minimum : une ligne voisine non détectée sur certaines
    images n'est ainsi pas recouverte par le français.
    """
    if not line_height:
        return
    ratios = [
        (o.block_bbox[3] - o.subtitle_bbox[3]) / line_height
        for o in observations if o.subtitle_bbox and o.block_bbox
    ]
    if len(ratios) < 5:
        return
    extension = float(np.percentile(ratios, q)) * line_height  # en pixels, hauteur de ligne typique de la vidéo
    for o in observations:
        if o.subtitle_bbox and o.block_bbox:
            min_bottom = min(height, int(o.subtitle_bbox[3] + extension))
            if o.block_bbox[3] < min_bottom:
                o.block_bbox = (o.block_bbox[0], o.block_bbox[1], o.block_bbox[2], min_bottom)


def analyse_observations(
    observations: list[FrameObservation], height: int, cfg: OcrConfig, width: int | None = None
) -> ZoneAnalysis:
    """Applique les heuristiques à toutes les observations (modifiées sur place)."""
    static, static_texts = find_static_lines(observations, cfg)
    zone, line_height = dominant_zone(observations, height, static, width, cfg.center_tolerance)
    for obs in observations:
        select_subtitle(obs, zone, height, static, cfg, width, line_height)
    _apply_typical_extension(observations, height, line_height)
    result = ZoneAnalysis(
        zone_center=zone, static_keys=static, static_texts=static_texts,
        frames_with_subtitle=sum(1 for o in observations if o.subtitle_text), frames_total=len(observations),
    )
    log.info("Zone des sous-titres : %s ; textes statiques écartés : %s", zone, static_texts)
    return result
