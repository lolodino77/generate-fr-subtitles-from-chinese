"""Construction des lignes de texte et des blocs de sous-titres à partir des boîtes OCR."""
from __future__ import annotations

from collections.abc import Iterable, Sequence

import numpy as np

from video_ocr.models import BBox, TextBox, TextLine
from video_ocr.ocr.text_utils import cjk_ratio, count_cjk

OTHER_MIN_SCORE = 0.0  # lignes non chinoises (ex. thaï, illisibles pour le modèle chinois) : gardées pour ne pas les masquer


def union_bbox(boxes: Iterable[BBox]) -> BBox | None:
    """Rectangle englobant d'une liste de rectangles."""
    boxes = list(boxes)
    if not boxes:
        return None
    return (
        min(b[0] for b in boxes), min(b[1] for b in boxes),
        max(b[2] for b in boxes), max(b[3] for b in boxes),
    )


def median_bbox(boxes: Sequence[BBox]) -> BBox | None:
    """Rectangle médian (robuste aux détections aberrantes)."""
    if not boxes:
        return None
    arr = np.asarray(boxes, dtype=float)
    return tuple(int(round(v)) for v in np.median(arr, axis=0))  # type: ignore[return-value]


def envelope_bbox(boxes: Sequence[BBox], q: float = 90.0) -> BBox | None:
    """Rectangle « enveloppe » robuste : percentiles 100-q / q des bords (une ligne voisine détectée
    sur une partie seulement des images reste incluse, une détection aberrante isolée est ignorée)."""
    if not boxes:
        return None
    arr = np.asarray(boxes, dtype=float)
    lo, hi = np.percentile(arr[:, :2], 100 - q, axis=0), np.percentile(arr[:, 2:], q, axis=0)
    return int(round(lo[0])), int(round(lo[1])), int(round(hi[0])), int(round(hi[1]))


def _same_row(a: BBox, b: BBox) -> bool:
    """Deux boîtes côte à côte sur la même ligne (pas deux lignes empilées qui se chevauchent).

    Les diacritiques thaïs agrandissent les boîtes verticalement : un simple chevauchement
    vertical fusionnerait la ligne chinoise et la ligne thaïe placée juste dessous.
    """
    h = min(a[3] - a[1], b[3] - b[1])
    w = min(a[2] - a[0], b[2] - b[0])
    centers_close = abs((a[1] + a[3]) / 2 - (b[1] + b[3]) / 2) <= 0.4 * h
    h_overlap = min(a[2], b[2]) - max(a[0], b[0])
    return centers_close and h_overlap <= 0.3 * w


def _join(left: str, right: str) -> str:
    """Concatène deux fragments ; espace seulement entre deux fragments non chinois."""
    if left and right and left[-1].isascii() and left[-1].isalnum() and right[0].isascii() and right[0].isalnum():
        return f"{left} {right}"
    return left + right


def boxes_to_lines(boxes: Sequence[TextBox], min_score: float, min_cjk_ratio: float) -> list[TextLine]:
    """Regroupe les boîtes alignées horizontalement en lignes, triées de haut en bas."""
    kept = [b for b in boxes if b.score >= OTHER_MIN_SCORE]  # texte vide conservé : zone de texte illisible à ne pas masquer
    kept.sort(key=lambda b: (b.cy, b.bbox[0]))
    rows: list[list[TextBox]] = []
    for box in kept:
        for row in rows:
            if any(_same_row(r.bbox, box.bbox) for r in row):
                row.append(box)
                break
        else:
            rows.append([box])
    lines: list[TextLine] = []
    for row in rows:
        row.sort(key=lambda b: b.bbox[0])
        text = ""
        for b in row:
            text = _join(text, b.text.strip())
        n_chars = sum(max(1, len(b.text)) for b in row)
        score = sum(b.score * max(1, len(b.text)) for b in row) / n_chars
        is_cn = count_cjk(text) > 0 and cjk_ratio(text) >= min_cjk_ratio and score >= min_score
        bbox = union_bbox(b.bbox for b in row)
        assert bbox is not None
        lines.append(TextLine(text=text, score=score, bbox=bbox, is_chinese=is_cn))
    lines.sort(key=lambda ln: ln.bbox[1])
    return lines


def _adjacent(a: BBox, b: BBox, max_gap_ratio: float) -> bool:
    """Deux lignes voisines verticalement et qui se chevauchent horizontalement."""
    h = max(a[3] - a[1], b[3] - b[1])
    gap = max(b[1] - a[3], a[1] - b[3])
    h_overlap = min(a[2], b[2]) - max(a[0], b[0])
    return gap <= max_gap_ratio * h and h_overlap > -0.1 * h


def group_blocks(lines: Sequence[TextLine], max_gap_ratio: float = 0.9) -> list[list[TextLine]]:
    """Regroupe des lignes voisines en blocs (sous-titre sur plusieurs lignes)."""
    blocks: list[list[TextLine]] = []
    for line in sorted(lines, key=lambda ln: ln.bbox[1]):
        for block in blocks:
            if any(_adjacent(other.bbox, line.bbox, max_gap_ratio) for other in block):
                block.append(line)
                break
        else:
            blocks.append([line])
    return blocks


def expand_with_neighbours(
    block: BBox, others: Sequence[TextLine], line_height: float, max_gap_ratio: float = 1.0
) -> BBox:
    """Étend le bloc chinois aux lignes non chinoises voisines (ex. transcription thaïe) pour ne pas les masquer.

    Seules les lignes de hauteur comparable aux lignes chinoises (0,4× à 2×) sont retenues : un objet
    de la scène reconnu à tort comme du texte (ex. un disque lu « O ») ne doit pas agrandir le bloc.
    """
    current = block
    changed = True
    remaining = [ln for ln in others if 0.4 * line_height <= ln.bbox[3] - ln.bbox[1] <= 2.0 * line_height]
    while changed:
        changed = False
        for line in list(remaining):
            gap = max(line.bbox[1] - current[3], current[1] - line.bbox[3])
            h_overlap = min(current[2], line.bbox[2]) - max(current[0], line.bbox[0])
            if gap <= max_gap_ratio * line_height and h_overlap > 0:
                merged = union_bbox([current, line.bbox])
                assert merged is not None
                current = merged
                remaining.remove(line)
                changed = True
    return current
