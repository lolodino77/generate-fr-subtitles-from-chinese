"""Regroupement temporel des observations OCR en segments de sous-titres.

Précision : les bornes sont estimées au milieu de l'intervalle entre la dernière image où le
texte est absent et la première où il est présent (et inversement pour la fin). L'incertitude
est donc la demi-distance entre ces deux images (≈ 1/(2 × dense_fps) avec l'affinage activé,
≈ ocr_interval/2 sans). Elle est enregistrée dans ``timing_uncertainty_s`` ; les horodatages
ne sont pas exacts à l'image près.
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field

from video_ocr.config import AppConfig
from video_ocr.models import FrameObservation, Segment
from video_ocr.ocr.lines import envelope_bbox, median_bbox
from video_ocr.ocr.text_utils import count_cjk, normalize_text, similarity, to_simplified

log = logging.getLogger(__name__)


@dataclass
class _Group:
    obs: list[FrameObservation] = field(default_factory=list)

    @property
    def first(self) -> float:
        return self.obs[0].t

    @property
    def last(self) -> float:
        return self.obs[-1].t

    def representative(self) -> str:
        counts = Counter(o.subtitle_text for o in self.obs)
        best = max(counts.values())
        tied = [t for t, c in counts.items() if c == best]
        if len(tied) == 1:
            return tied[0]
        return max(tied, key=lambda t: max(o.subtitle_score for o in self.obs if o.subtitle_text == t))


def _scan(observations: list[FrameObservation], thr: float, max_gap: float) -> list[_Group]:
    """Parcours chronologique : un groupe continue tant que le texte reste similaire et sans trou trop long."""
    groups: list[_Group] = []
    current: _Group | None = None
    for obs in observations:
        if not obs.subtitle_text:
            continue
        if current is not None and obs.t - current.last <= max_gap and similarity(obs.subtitle_text, current.representative()) >= thr:
            current.obs.append(obs)
            continue
        current = _Group([obs])
        groups.append(current)
    return groups


def _merge_pass(groups: list[_Group], thr: float, max_gap: float, glitch_max_obs: int) -> list[_Group]:
    """Fusionne les doublons proches et les détections isolées (images de transition)."""
    merged = True
    while merged and len(groups) > 1:
        merged = False
        for i in range(len(groups) - 1):
            a, b = groups[i], groups[i + 1]
            gap = b.first - a.last
            sim = similarity(a.representative(), b.representative())
            glitch = min(len(a.obs), len(b.obs)) <= glitch_max_obs and sim >= 0.5 and gap <= max_gap
            if (sim >= thr and gap <= max_gap) or glitch:
                groups[i] = _Group(sorted(a.obs + b.obs, key=lambda o: o.t))
                del groups[i + 1]
                merged = True
                break
    return groups


def _bounds(group: _Group, all_times: list[float], duration: float) -> tuple[float, float, float]:
    """Début, fin et incertitude d'un groupe à partir des images voisines sans ce texte."""
    times_in = {o.t for o in group.obs}
    before = [t for t in all_times if t < group.first and t not in times_in]
    after = [t for t in all_times if t > group.last and t not in times_in]
    t_prev = before[-1] if before else None
    t_next = after[0] if after else None
    start = 0.0 if t_prev is None else (t_prev + group.first) / 2
    end = duration if t_next is None else (group.last + t_next) / 2
    unc_start = 0.0 if t_prev is None else (group.first - t_prev) / 2
    unc_end = (duration - group.last) / 2 if t_next is None else (t_next - group.last) / 2
    if t_next is None and duration - group.last < 1.0:
        unc_end = 0.0  # texte visible jusqu'à la fin de la vidéo
    return start, end, max(unc_start, unc_end)


def build_segments(observations: list[FrameObservation], duration: float, cfg: AppConfig) -> list[Segment]:
    """Construit les segments chronologiques, sans chevauchement, avec indicateurs d'incertitude."""
    sc = cfg.segments
    observations = sorted(observations, key=lambda o: o.t)
    groups = _scan(observations, sc.similarity_threshold, sc.max_gap_s)
    groups = _merge_pass(groups, sc.similarity_threshold, sc.max_gap_s, sc.merge_glitch_max_obs)
    all_times = [o.t for o in observations]
    segments: list[Segment] = []
    for group in groups:
        rep = group.representative()
        start, end, unc = _bounds(group, all_times, duration)
        scores = [o.subtitle_score for o in group.obs]
        variants = sorted({o.subtitle_text for o in group.obs} - {rep})
        normalized = normalize_text(rep.replace("\n", ""))
        seg = Segment(
            index=len(segments) + 1, start=round(start, 3), end=round(end, 3), text_raw=rep,
            text_normalized=normalized, text_simplified=to_simplified(normalized),
            score=round(sum(scores) / len(scores), 4), min_score=round(min(scores), 4),
            n_observations=len(group.obs), variants=variants,
            bbox=median_bbox([o.subtitle_bbox for o in group.obs if o.subtitle_bbox]),
            block_bbox=envelope_bbox([o.block_bbox for o in group.obs if o.block_bbox]),
            timing_uncertainty_s=round(unc, 3),
        )
        segments.append(seg)
    segments = drop_single_char_artifacts(segments, sc.single_char_min_s, sc.recurring_single_char)
    for i, seg in enumerate(segments, start=1):
        seg.index = i
    _fix_timing(segments, duration, sc.min_duration_s)
    _flag(segments, cfg)
    log.info("%d segments construits à partir de %d observations", len(segments), len(observations))
    return segments


def looks_without_subtitles(segments: list[Segment], cfg: AppConfig) -> bool:
    """Vrai si les « segments » ressemblent à du texte de scène (enseignes, menus) et non à des sous-titres.

    Un sous-titre reste lisible plusieurs secondes ; du texte filmé défile en une fraction de seconde,
    donne des segments très courts, à une seule observation ou à lecture instable.
    """
    sc = cfg.segments
    if len(segments) < sc.no_subtitle_min_segments:
        return False
    durations = sorted(s.duration for s in segments)
    median = (durations[(len(durations) - 1) // 2] + durations[len(durations) // 2]) / 2
    flagged = sum(1 for s in segments if s.flags) / len(segments)
    return median < sc.no_subtitle_median_s and flagged >= sc.no_subtitle_flagged_ratio


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    inter_w = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    inter_h = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = inter_w * inter_h
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def drop_single_char_artifacts(segments: list[Segment], min_s: float, recurring: int) -> list[Segment]:
    """Écarte les « sous-titres » d'un seul caractère qui sont des artefacts (cas réels) :

    - fragment très bref (< ``min_s`` avant allongement) : image de transition lue comme un caractère ;
    - objet de la scène : le même caractère au même endroit dans au moins ``recurring`` segments
      distincts (ex. un boîtier carré lu « 口 » chaque fois qu'aucun sous-titre ne le recouvre).
    Les sous-titres de plusieurs caractères ne sont jamais concernés.
    """
    single = [s for s in segments if count_cjk(s.text_raw) <= 1]
    drop: set[int] = set()
    for seg in single:
        if seg.end - seg.start < min_s:
            drop.add(id(seg))
    if recurring > 0:
        for seg in single:
            same = [o for o in single if o.text_raw == seg.text_raw and o.bbox and seg.bbox and _iou(o.bbox, seg.bbox) > 0.7]
            if len(same) >= recurring:
                drop.update(id(o) for o in same)
    kept = [s for s in segments if id(s) not in drop]
    if len(kept) < len(segments):
        log.info("%d artefact(s) d'un seul caractère écarté(s) : %s", len(segments) - len(kept),
                 sorted({s.text_raw for s in segments if id(s) in drop}))
    return kept


def _fix_timing(segments: list[Segment], duration: float, min_duration: float) -> None:
    """Supprime les chevauchements et allonge les segments trop courts quand la place le permet."""
    for i, seg in enumerate(segments):
        nxt = segments[i + 1] if i + 1 < len(segments) else None
        if nxt is not None and seg.end > nxt.start:
            mid = round((seg.end + nxt.start) / 2, 3)
            seg.end, nxt.start = mid, mid
        if seg.duration < min_duration:
            seg.flags.append("short")
            limit = nxt.start if nxt is not None else duration
            seg.end = round(min(limit, seg.start + min_duration), 3)
            if seg.duration < min_duration:
                prev_end = segments[i - 1].end if i > 0 else 0.0
                seg.start = round(max(prev_end, seg.end - min_duration), 3)


def _flag(segments: list[Segment], cfg: AppConfig) -> None:
    for seg in segments:
        if seg.score < cfg.ocr.uncertain_score:
            seg.flags.append("low_confidence")
        if seg.n_observations == 1:
            seg.flags.append("single_observation")
        if seg.timing_uncertainty_s > 0.3:
            seg.flags.append("timing_uncertain")
        if any(similarity(v, seg.text_raw) < 0.95 for v in seg.variants):
            seg.flags.append("ocr_variants")
