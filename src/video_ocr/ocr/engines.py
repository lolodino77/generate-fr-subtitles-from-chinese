"""Moteurs OCR locaux (RapidOCR par défaut, PaddleOCR en option)."""
from __future__ import annotations

import logging
import os
from typing import Protocol

import numpy as np

from video_ocr.config import OcrConfig
from video_ocr.models import TextBox

log = logging.getLogger(__name__)


class OcrEngine(Protocol):
    """Interface commune : image BGR -> boîtes de texte (coordonnées de l'image fournie)."""

    name: str

    def recognize(self, image: np.ndarray) -> list[TextBox]: ...


def _poly_to_bbox(poly: object) -> tuple[int, int, int, int]:
    pts = np.asarray(poly, dtype=float).reshape(-1, 2)
    return int(pts[:, 0].min()), int(pts[:, 1].min()), int(pts[:, 0].max()), int(pts[:, 1].max())


class RapidOcrEngine:
    """RapidOCR (ONNX Runtime) avec les modèles PP-OCR (chinois simplifié + traditionnel)."""

    name = "rapidocr"

    def __init__(self, cfg: OcrConfig) -> None:
        from rapidocr import ModelType, OCRVersion, RapidOCR

        params = {
            "Global.use_cls": False,  # sous-titres horizontaux : classification d'orientation inutile
            "Global.log_level": "error",
            "Global.text_score": 0.0,  # filtrage fait par l'application : les lignes illisibles (ex. thaï) servent au placement
            "Det.ocr_version": OCRVersion(cfg.rapid_ocr_version),
            "Rec.ocr_version": OCRVersion(cfg.rapid_ocr_version),
            "Det.model_type": ModelType(cfg.rapid_model_type),
            "Rec.model_type": ModelType(cfg.rapid_model_type),
        }
        self._engine = RapidOCR(params=params)
        self.label = f"RapidOCR {cfg.rapid_ocr_version} {cfg.rapid_model_type}"

    def recognize(self, image: np.ndarray) -> list[TextBox]:
        res = self._engine(image)
        if res is None or res.boxes is None or res.txts is None:
            return []
        out: list[TextBox] = []
        for b, t, s in zip(res.boxes, res.txts, res.scores):
            box = TextBox(text=str(t), score=float(s), bbox=_poly_to_bbox(b))
            out.extend(self._split_stacked(image, box))
        return out

    def _split_stacked(self, image: np.ndarray, box: TextBox) -> list[TextBox]:
        """Relit une boîte haute et étroite qui empile probablement plusieurs lignes.

        Cas réel : un caractère chinois au-dessus de mots thaïs courts est détecté comme une
        colonne de texte vertical et lu d'un bloc (短 + thaï -> « 短的品 »). Une seconde
        détection sur la zone découpée (avec marge) sépare généralement les lignes.
        """
        x0, y0, x1, y1 = box.bbox
        w, h = x1 - x0, y1 - y0
        if w <= 0 or h < 1.2 * w:
            return [box]
        m = 40
        cx0, cy0 = max(0, x0 - m), max(0, y0 - m)
        crop = np.ascontiguousarray(image[cy0:y1 + m, cx0:x1 + m])
        res = self._engine(crop)
        if res is None or res.boxes is None or res.txts is None or len(res.txts) < 2:
            return [box]
        out = []
        for b, t, s in zip(res.boxes, res.txts, res.scores):
            bx = _poly_to_bbox(b)
            out.append(TextBox(str(t), float(s), (bx[0] + cx0, bx[1] + cy0, bx[2] + cx0, bx[3] + cy0)))
        return out


class PaddleOcrEngine:
    """PaddleOCR 3.x (PP-OCRv5 mobile). oneDNN désactivé : bogue connu de Paddle 3.3 sous Windows."""

    name = "paddleocr"

    def __init__(self, cfg: OcrConfig) -> None:
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        from paddleocr import PaddleOCR

        self._engine = PaddleOCR(
            use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False,
            text_detection_model_name="PP-OCRv5_mobile_det", text_recognition_model_name="PP-OCRv5_mobile_rec",
            enable_mkldnn=False,
        )
        self.label = "PaddleOCR PP-OCRv5 mobile"

    def recognize(self, image: np.ndarray) -> list[TextBox]:
        out = self._engine.predict(image)
        if not out:
            return []
        r = out[0]
        return [
            TextBox(text=str(t), score=float(s), bbox=_poly_to_bbox(p))
            for p, t, s in zip(r["rec_polys"], r["rec_texts"], r["rec_scores"])
        ]


def create_engine(cfg: OcrConfig) -> OcrEngine:
    """Instancie le moteur demandé ; erreur explicite s'il n'est pas installé."""
    try:
        if cfg.engine == "rapidocr":
            return RapidOcrEngine(cfg)
        if cfg.engine == "paddleocr":
            return PaddleOcrEngine(cfg)
    except ImportError as exc:
        raise RuntimeError(f"Moteur OCR « {cfg.engine} » non installé : {exc}") from exc
    raise ValueError(f"Moteur OCR inconnu : {cfg.engine}")
