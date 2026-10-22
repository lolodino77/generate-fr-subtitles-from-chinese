"""Calcul du placement du texte français (stratégie A « inline » ou B « band »)."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

from video_ocr.config import RenderConfig
from video_ocr.fonts import first_font
from video_ocr.models import BBox

FALLBACK_FONTS = ["segoeuib.ttf", "segoeui.ttf", "arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf"]


@lru_cache(maxsize=32)
def load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """Charge une police (nom de fichier ou chemin, cf. video_ocr.fonts) avec repli sur des polices courantes."""
    path = first_font(name, *FALLBACK_FONTS)
    if path is None:
        raise FileNotFoundError(f"Aucune police utilisable (demandée : {name})")
    return ImageFont.truetype(str(path), size)


@dataclass
class OutputGeometry:
    width: int
    height: int  # hauteur de sortie (vidéo + bande éventuelle)
    video_height: int
    band_height: int


@dataclass
class Placement:
    lines: list[str]
    font_size: int
    box: BBox  # rectangle de fond dans l'image de sortie
    mode: str  # below | above | bottom | band
    overlap_risk: bool = False


def output_geometry(width: int, height: int, cfg: RenderConfig) -> OutputGeometry:
    """Dimensions de sortie ; la bande (stratégie B) est ajoutée sous l'image, hauteur paire."""
    band = 0
    if cfg.strategy == "band":
        band = int(round(height * cfg.band_height_ratio / 2)) * 2
    return OutputGeometry(width, height + band, height, band)


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: float) -> list[str]:
    """Retour à la ligne glouton par mots (coupe les mots trop longs)."""
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        current = ""
        for word in paragraph.split():
            trial = f"{current} {word}".strip()
            if font.getlength(trial) <= max_width:
                current = trial
                continue
            if current:
                lines.append(current)
            while font.getlength(word) > max_width and len(word) > 1:
                cut = len(word)
                while cut > 1 and font.getlength(word[:cut]) > max_width:
                    cut -= 1
                lines.append(word[:cut])
                word = word[cut:]
            current = word
        if current:
            lines.append(current)
    return lines or [""]


def fit_text(text: str, width: int, cfg: RenderConfig, base_size: int) -> tuple[list[str], int]:
    """Réduit la police (jusqu'à 60 %) pour tenir dans ``max_lines`` lignes."""
    max_w = width * (1 - 2 * cfg.margin_ratio) - base_size * 0.7
    size = base_size
    while True:
        font = load_font(cfg.font_path, size)
        lines = wrap_text(text, font, max_w)
        if len(lines) <= cfg.max_lines or size <= base_size * 0.6:
            return lines, size
        size = max(int(base_size * 0.6), int(size * 0.9))


def text_block_size(lines: list[str], size: int, cfg: RenderConfig) -> tuple[int, int, int, int]:
    """Largeur et hauteur du fond, marges internes horizontale et verticale."""
    font = load_font(cfg.font_path, size)
    pad_x, pad_y = int(size * 0.35), int(size * 0.22)
    text_w = max(font.getlength(ln) for ln in lines)
    line_h = int(size * cfg.line_spacing)
    return int(text_w + 2 * pad_x), int(line_h * len(lines) + 2 * pad_y), pad_x, pad_y


def _overlaps(a: BBox, b: BBox) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def place(text: str, geo: OutputGeometry, block: BBox | None, cfg: RenderConfig) -> Placement:
    """Calcule les lignes et le rectangle du texte français pour un segment."""
    base = max(14, int(round(geo.width * cfg.font_size_ratio)))
    lines, size = fit_text(text, geo.width, cfg, base)
    box_w, box_h, _, _ = text_block_size(lines, size, cfg)
    margin_x = int(geo.width * cfg.margin_ratio)
    if cfg.strategy == "band":
        x0 = (geo.width - box_w) // 2
        y0 = geo.video_height + max(0, (geo.band_height - box_h) // 2)
        return Placement(lines, size, (x0, y0, x0 + box_w, y0 + box_h), "band", box_h > geo.band_height)

    gap = int(geo.video_height * cfg.gap_ratio)
    safe = int(geo.video_height * 0.03)
    cx = geo.width / 2 if block is None else (block[0] + block[2]) / 2
    x0 = int(min(max(margin_x, cx - box_w / 2), geo.width - margin_x - box_w))
    x0 = max(0, x0)
    order = {"below": ["below", "above", "bottom"], "above": ["above", "below", "bottom"]}.get(cfg.position, ["bottom"])
    for mode in order:
        if mode == "below" and block is not None:
            y0 = block[3] + gap
        elif mode == "above" and block is not None:
            y0 = block[1] - gap - box_h
        elif mode == "bottom":
            y0 = geo.video_height - safe - box_h
        else:
            continue
        box = (x0, y0, x0 + box_w, y0 + box_h)
        if y0 >= safe and y0 + box_h <= geo.video_height - safe:
            overlap = block is not None and _overlaps(box, block)
            if mode != "bottom" or not overlap:
                return Placement(lines, size, box, mode, overlap)
    # Aucun emplacement libre : bas de l'image, signalé
    y0 = max(0, geo.video_height - safe - box_h)
    box = (x0, y0, x0 + box_w, y0 + box_h)
    return Placement(lines, size, box, "bottom", block is not None and _overlaps(box, block))
