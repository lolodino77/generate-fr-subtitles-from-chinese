"""Dessin des sous-titres français (images RGBA transparentes) avec Pillow."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageColor, ImageDraw

from video_ocr.config import RenderConfig
from video_ocr.rendering.layout import OutputGeometry, Placement, load_font, text_block_size


def _rgba(color: str, alpha: float = 1.0) -> tuple[int, int, int, int]:
    r, g, b = ImageColor.getrgb(color)[:3]
    return r, g, b, int(round(255 * max(0.0, min(1.0, alpha))))


def draw_placement(canvas: Image.Image, placement: Placement, cfg: RenderConfig) -> None:
    """Dessine fond semi-transparent + texte contouré sur ``canvas`` (RGBA)."""
    draw = ImageDraw.Draw(canvas)
    font = load_font(cfg.font_path, placement.font_size)
    x0, y0, x1, y1 = placement.box
    if cfg.background_opacity > 0:
        draw.rounded_rectangle(
            placement.box, radius=int(placement.font_size * 0.3),
            fill=_rgba(cfg.background_color, cfg.background_opacity),
        )
    _, _, _, pad_y = text_block_size(placement.lines, placement.font_size, cfg)
    line_h = int(placement.font_size * cfg.line_spacing)
    stroke = max(0, int(round(placement.font_size * cfg.outline_width_ratio)))
    for i, line in enumerate(placement.lines):
        w = font.getlength(line)
        x = x0 + ((x1 - x0) - w) / 2
        y = y0 + pad_y + i * line_h + (line_h - placement.font_size) / 2
        draw.text(
            (x, y), line, font=font, fill=_rgba(cfg.text_color), stroke_width=stroke,
            stroke_fill=_rgba(cfg.outline_color),
        )


def render_overlay(path: str | Path, geo: OutputGeometry, placement: Placement | None, cfg: RenderConfig) -> Path:
    """Enregistre une image PNG transparente de la taille de sortie (vide si ``placement`` est None)."""
    canvas = Image.new("RGBA", (geo.width, geo.height), (0, 0, 0, 0))
    if placement is not None:
        draw_placement(canvas, placement, cfg)
    path = Path(path)
    canvas.save(path, optimize=False, compress_level=6)
    return path


def compose_preview(frame_rgb: Image.Image, geo: OutputGeometry, placement: Placement | None, cfg: RenderConfig) -> Image.Image:
    """Aperçu : image source (+ bande noire éventuelle) avec le français dessiné."""
    base = Image.new("RGBA", (geo.width, geo.height), (0, 0, 0, 255))
    base.paste(frame_rgb.convert("RGBA"), (0, 0))
    if placement is not None:
        layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
        draw_placement(layer, placement, cfg)
        base = Image.alpha_composite(base, layer)
    return base.convert("RGB")
