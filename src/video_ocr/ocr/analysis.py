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
    zone_center: float | None  # centre vertical de la zone principale des sous-titres (fraction de hauteur)
    zones: list[float] = field(default_factory=list)  # toutes les zones retenues (principale en premier)
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
    """Zone principale des sous-titres (centre vertical en fraction) et hauteur de ligne typique (px)."""
    zones, line_height = dominant_zones(observations, height, static, width, center_tolerance)
    return (zones[0] if zones else None), line_height


def dominant_zones(
    observations: list[FrameObservation], height: int, static: set[str], width: int | None = None,
    center_tolerance: float = 0.0, secondary_ratio: float = 0.15, max_zones: int = 3,
) -> tuple[list[float], float | None]:
    """Zones verticales des sous-titres, de la plus fréquente à la moins fréquente, et hauteur de ligne typique.

    Une vidéo peut placer ses sous-titres à plusieurs hauteurs (cas réel : haut de l'image pour certaines
    phrases, bas pour d'autres). Toute zone secondaire pesant au moins ``secondary_ratio`` de la zone
    principale (en caractères chinois centrés) est conservée.
    """
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
        return [], None
    hist, edges = np.histogram(centers, bins=40, range=(0.0, 1.0), weights=weights)
    smooth = np.convolve(hist, np.ones(3) / 3, mode="same")
    zones: list[float] = []
    main_weight = float(smooth.max())
    in_peak: list[tuple[float, float, float]] = []
    remaining = smooth.copy()
    while len(zones) < max_zones and remaining.max() > 0 and remaining.max() >= secondary_ratio * main_weight:
        peak = int(np.argmax(remaining))
        lo, hi = edges[max(0, peak - 1)], edges[min(len(edges) - 1, peak + 2)]
        members = [(c, w, h) for c, w, h in zip(centers, weights, heights) if lo <= c <= hi]
        if members:
            zones.append(float(sum(c * w for c, w, _ in members) / sum(w for _, w, _ in members)))
            if not in_peak:
                in_peak = members  # la hauteur typique est mesurée sur la zone principale
        remaining[max(0, peak - 3):peak + 4] = 0  # zones distantes d'au moins ≈ 0,1 de hauteur
    if not zones:
        return [], None
    # Médiane haute pondérée par le nombre de caractères (en cas d'égalité, le texte le plus grand l'emporte)
    hs = np.array([h for _, _, h in in_peak])
    ws = np.array([w for _, w, _ in in_peak])
    order = np.argsort(hs)
    cum = np.cumsum(ws[order])
    idx = min(len(hs) - 1, int(np.searchsorted(cum, cum[-1] / 2, side="right")))
    return zones, float(hs[order][idx])


def select_subtitle(
    obs: FrameObservation, zone: float | list[float] | None, height: int, static: set[str], cfg: OcrConfig,
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

    zones = [zone] if isinstance(zone, (int, float)) else list(zone or [])
    if zones:
        def distance(b: list[TextLine]) -> float:
            return min(abs(center(b) - z) for z in zones)

        candidates = [b for b in blocks if distance(b) <= cfg.zone_tolerance]
        if not candidates:
            return
        block = min(candidates, key=distance)
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
    zones, line_height = dominant_zones(
        observations, height, static, width, cfg.center_tolerance, cfg.secondary_zone_ratio, cfg.max_zones
    )
    for obs in observations:
        select_subtitle(obs, zones, height, static, cfg, width, line_height)
    _apply_typical_extension(observations, height, line_height)
    result = ZoneAnalysis(
        zone_center=zones[0] if zones else None, zones=zones, static_keys=static, static_texts=static_texts,
        frames_with_subtitle=sum(1 for o in observations if o.subtitle_text), frames_total=len(observations),
    )
    log.info("Zones des sous-titres : %s ; textes statiques écartés : %s", zones, static_texts)
    return result


@dataclass
class SampleIndicators:
    """Indicateurs « sous-titres présents ? » calculés sur un échantillon d'images réparti sur la vidéo."""

    frames: int  # images analysées
    zones: int  # zones verticales de sous-titres trouvées
    centered_frames: float  # part d'images avec au moins une ligne chinoise centrée
    concentration: float  # part des lignes centrées situées dans une zone de sous-titres
    subtitle_like_frames: float  # part d'images avec une ligne centrée, dans une zone, de hauteur typique
    avg_cjk_per_line: float  # caractères chinois par ligne centrée (enseignes : lignes longues ; sous-titres : courtes)
    line_height: float | None = None  # hauteur de ligne typique (px)

    def to_dict(self) -> dict[str, float | int | None]:
        return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in self.__dict__.items()}


def sample_indicators(observations: list[FrameObservation], width: int, height: int, cfg: OcrConfig) -> SampleIndicators:
    """Calcule les indicateurs sur des observations d'images entières (lignes chinoises centrées uniquement)."""
    static, _ = find_static_lines(observations, cfg) if len(observations) >= 6 else (set(), [])
    zones, line_height = dominant_zones(
        observations, height, static, width, cfg.center_tolerance, cfg.secondary_zone_ratio, cfg.max_zones
    )
    n = max(1, len(observations))
    per_frame = [
        [ln for ln in o.lines if ln.is_chinese and comparison_key(ln.text) not in static
         and _is_centered(ln.bbox, width, cfg.center_tolerance)]
        for o in observations
    ]

    def in_zone(ln: TextLine) -> bool:
        cy = (ln.bbox[1] + ln.bbox[3]) / 2 / height
        return bool(zones) and min(abs(cy - z) for z in zones) <= 0.06

    lines = [ln for frame in per_frame for ln in frame]
    typical = lambda ln: bool(line_height) and 0.6 * line_height <= ln.bbox[3] - ln.bbox[1] <= 1.6 * line_height  # noqa: E731
    return SampleIndicators(
        frames=len(observations), zones=len(zones),
        centered_frames=sum(1 for f in per_frame if f) / n,
        concentration=(sum(1 for ln in lines if in_zone(ln)) / len(lines)) if lines else 0.0,
        subtitle_like_frames=sum(1 for f in per_frame if any(in_zone(ln) and typical(ln) for ln in f)) / n,
        avg_cjk_per_line=float(np.mean([count_cjk(ln.text) for ln in lines])) if lines else 0.0,
        line_height=line_height,
    )


def likely_no_subtitles(ind: SampleIndicators, cfg: OcrConfig) -> str:
    """Raison pour laquelle la vidéo n'a probablement pas de sous-titres incrustés, ou « » si elle en a.

    Règle (voir TEST_REPORT.md §6.7) : moins de ``no_subtitle_clear_ratio`` des images ont une ligne chinoise
    « de type sous-titre ». Un échantillon trop petit ne décide jamais.

    Un critère « lignes longues = enseignes » a été retiré : il écartait à tort des vidéos dont les sous-titres
    sont des phrases entières (`Del8z_ziYQH`). En contrepartie, des vlogs à 20-24 % d'images « type sous-titre »
    ne sont plus écartés par ce test rapide, mais seulement après l'OCR complète (`looks_without_subtitles`).
    La longueur moyenne des lignes reste calculée (``avg_cjk_per_line``) à titre de diagnostic.
    """
    if ind.frames < cfg.no_subtitle_min_frames:
        return ""
    if ind.subtitle_like_frames < cfg.no_subtitle_clear_ratio:
        return (f"{ind.subtitle_like_frames:.0%} des images ont une ligne chinoise de type sous-titre "
                f"(seuil {cfg.no_subtitle_clear_ratio:.0%})")
    return ""
