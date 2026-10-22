"""Exécution du lot dans un thread de fond (l'interface reste réactive), avec annulation."""
from __future__ import annotations

import logging
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from video_ocr.config import AppConfig
from video_ocr.pipeline.batch import BatchResult, run_batch
from video_ocr.pipeline.processor import Engines

log = logging.getLogger(__name__)


@dataclass
class JobState:
    running: bool = False
    videos: list[str] = field(default_factory=list)
    current: int = 0
    video_progress: float = 0.0
    message: str = ""
    started: float = 0.0
    result: BatchResult | None = None
    error: str = ""
    out_root: str = ""

    @property
    def overall(self) -> float:
        if not self.videos:
            return 0.0
        return min(1.0, (self.current + self.video_progress) / len(self.videos))


class JobManager:
    """Un seul lot à la fois ; partagé entre les rafraîchissements de page."""

    def __init__(self) -> None:
        self.state = JobState()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._engines: tuple[str, Engines] | None = None

    def _engines_for(self, cfg: AppConfig) -> Engines:
        key = repr((cfg.ocr, cfg.translation, cfg.cache_dir))
        if self._engines is None or self._engines[0] != key:
            self._engines = (key, Engines(cfg))
        else:
            self._engines[1].cfg = cfg
        return self._engines[1]

    def start(self, videos: list[Path], out_root: Path, cfg: AppConfig, force: bool = False) -> None:
        if self.state.running:
            raise RuntimeError("Un traitement est déjà en cours")
        self._cancel.clear()
        self.state = JobState(running=True, videos=[str(v) for v in videos], started=time.time(), out_root=str(out_root))
        engines = self._engines_for(cfg)

        def progress(i: int, n: int, frac: float, msg: str) -> None:
            self.state.current, self.state.video_progress, self.state.message = i, frac, msg

        def target() -> None:
            try:
                self.state.result = run_batch(videos, out_root, cfg, progress, self._cancel, force, engines)
                if not self.state.result.cancelled:
                    self.state.current, self.state.video_progress = len(videos) - 1, 1.0
                    self.state.message = "Terminé"
            except Exception as exc:  # noqa: BLE001
                log.exception("Échec du lot")
                self.state.error = f"{type(exc).__name__}: {exc}"
            finally:
                self.state.running = False

        self._thread = threading.Thread(target=target, name="video_ocr-batch", daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self._cancel.set()


def native_dialog(kind: str, initial: str = "") -> list[str]:
    """Boîte de dialogue Windows (tkinter) lancée dans un sous-processus pour ne pas bloquer Streamlit."""
    code = (
        "import tkinter as tk, sys, json\nfrom tkinter import filedialog as fd\n"
        "r = tk.Tk(); r.withdraw(); r.attributes('-topmost', True)\n"
        f"kind = {kind!r}; init = {initial!r}\n"
        "if kind == 'files':\n"
        "    res = list(fd.askopenfilenames(initialdir=init or None, filetypes=[('Vidéos', '*.mp4 *.mov *.mkv *.m4v *.webm'), ('Tous', '*.*')]))\n"
        "else:\n"
        "    d = fd.askdirectory(initialdir=init or None); res = [d] if d else []\n"
        "sys.stdout.write(json.dumps(res))\n"
    )
    try:
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, timeout=600)
        import json

        return list(json.loads(out.stdout.decode("utf-8") or "[]"))
    except Exception:  # noqa: BLE001
        log.exception("Boîte de dialogue indisponible")
        return []
