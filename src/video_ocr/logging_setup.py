"""Configuration des logs (console + fichier UTF-8)."""
from __future__ import annotations

import logging
import sys
from pathlib import Path


def setup_logging(log_file: str | Path | None = None, level: int = logging.INFO) -> None:
    """Initialise les logs une seule fois ; ajoute un fichier si demandé."""
    root = logging.getLogger()
    root.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
    if not any(getattr(h, "_video_ocr", False) for h in root.handlers):
        stream = logging.StreamHandler(sys.stderr)
        stream.setFormatter(fmt)
        stream._video_ocr = True  # type: ignore[attr-defined]
        root.addHandler(stream)
    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not any(isinstance(h, logging.FileHandler) and Path(h.baseFilename) == path.resolve() for h in root.handlers):
            fh = logging.FileHandler(path, encoding="utf-8")
            fh.setFormatter(fmt)
            root.addHandler(fh)
    for noisy in ("RapidOCR", "httpx", "urllib3", "stanza", "huggingface_hub", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
