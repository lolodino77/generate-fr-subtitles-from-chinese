"""Structures de données partagées entre les étapes du pipeline."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

BBox = tuple[int, int, int, int]  # x0, y0, x1, y1 en pixels de l'image d'origine


@dataclass
class TextBox:
    """Une zone de texte reconnue par l'OCR."""

    text: str
    score: float
    bbox: BBox

    @property
    def height(self) -> int:
        return self.bbox[3] - self.bbox[1]

    @property
    def cy(self) -> float:
        return (self.bbox[1] + self.bbox[3]) / 2


@dataclass
class TextLine:
    """Une ligne de texte (une ou plusieurs boîtes alignées horizontalement)."""

    text: str
    score: float
    bbox: BBox
    is_chinese: bool


@dataclass
class FrameObservation:
    """Résultat OCR d'une image échantillonnée."""

    t: float
    lines: list[TextLine] = field(default_factory=list)
    reused: bool = False  # True si l'OCR a été réutilisé (image inchangée)
    refined: bool = False  # True si l'image provient de l'affinage des bornes
    # Renseignés après analyse au niveau de la vidéo :
    subtitle_text: str = ""
    subtitle_score: float = 0.0
    subtitle_bbox: BBox | None = None  # lignes chinoises du sous-titre
    block_bbox: BBox | None = None  # bloc complet (chinois + lignes voisines, ex. thaï) à ne pas masquer

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Segment:
    """Un sous-titre affiché pendant une période continue."""

    index: int
    start: float
    end: float
    text_raw: str
    text_normalized: str = ""
    text_simplified: str = ""
    translation: str | None = None
    translation_status: str = "pending"  # pending | ok | failed | skipped
    score: float = 0.0
    min_score: float = 0.0
    n_observations: int = 0
    variants: list[str] = field(default_factory=list)
    bbox: BBox | None = None
    block_bbox: BBox | None = None
    timing_uncertainty_s: float = 0.0
    flags: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["duration"] = round(self.duration, 3)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Segment":
        data = {k: v for k, v in data.items() if k != "duration"}
        for key in ("bbox", "block_bbox"):
            if data.get(key) is not None:
                data[key] = tuple(data[key])
        return cls(**data)


@dataclass
class VideoInfo:
    """Métadonnées d'une vidéo (ffprobe)."""

    path: str
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool
    video_codec: str = ""
    audio_codec: str = ""
    rotation: int = 0
    n_frames: int | None = None
