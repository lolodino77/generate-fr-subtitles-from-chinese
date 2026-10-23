"""Traitement d'un lot de vidéos, séquentiel, avec rapport récapitulatif."""
from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from video_ocr.config import AppConfig
from video_ocr.pipeline.processor import Engines, VideoResult, process_video

log = logging.getLogger(__name__)

BatchProgress = Callable[[int, int, float, str], None]  # (index vidéo, nb vidéos, fraction vidéo, message)


@dataclass
class BatchResult:
    started: str
    finished: str = ""
    out_root: str = ""
    results: list[VideoResult] = field(default_factory=list)
    cancelled: bool = False
    seconds: float = 0.0

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.results:
            out[r.status] = out.get(r.status, 0) + 1
        return out


def run_batch(
    videos: list[Path],
    out_root: str | Path,
    cfg: AppConfig,
    progress: BatchProgress | None = None,
    cancel: threading.Event | None = None,
    force: bool = False,
    engines: Engines | None = None,
    redo_from: str | None = None,
) -> BatchResult:
    """Traite les vidéos l'une après l'autre ; un échec n'arrête pas le lot."""
    out_root = Path(out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    engines = engines or Engines(cfg)
    t0 = time.perf_counter()
    batch = BatchResult(started=datetime.now().isoformat(timespec="seconds"), out_root=str(out_root))
    for i, video in enumerate(videos):
        if cancel is not None and cancel.is_set():
            batch.cancelled = True
            break
        log.info("[%d/%d] %s", i + 1, len(videos), video)

        def cb(frac: float, msg: str, i: int = i) -> None:
            if progress is not None:
                progress(i, len(videos), frac, msg)

        res = process_video(video, out_root, cfg, engines, cb, cancel, force, redo_from)
        batch.results.append(res)
        if res.status == "interrupted":
            batch.cancelled = True
            break
        write_batch_report(batch, out_root)
    engines.close()  # ferme le navigateur du moteur de traduction en ligne, le cas échéant
    batch.finished = datetime.now().isoformat(timespec="seconds")
    batch.seconds = round(time.perf_counter() - t0, 1)
    write_batch_report(batch, out_root)
    return batch


def write_batch_report(batch: BatchResult, out_root: Path) -> None:
    """``batch_summary.json`` + ``batch_report.md`` à la racine du dossier de sortie."""
    (out_root / "batch_summary.json").write_text(json.dumps(asdict(batch), ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Rapport du lot", "", f"- Début : {batch.started}", f"- Fin : {batch.finished or 'en cours'}",
        f"- Durée totale : {batch.seconds} s", f"- Statuts : {batch.counts()}",
        f"- Annulé : {'oui' if batch.cancelled else 'non'}", "",
        "| Vidéo | Statut | Durée (s) | Segments | Traduits | Signalés | Temps OCR (s) | Temps rendu (s) | Erreur / avertissements |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in batch.results:
        status = r.status + (" (déjà traité)" if r.skipped else "")
        notes = r.error or "; ".join(r.warnings)
        lines.append(
            f"| {Path(r.source).name} | {status} | {r.duration:.1f} | {r.segments} | {r.translated} | {r.flagged} | "
            f"{r.timings.get('ocr', '—')} | {r.timings.get('render', '—')} | {notes.replace('|', '/')} |"
        )
    (out_root / "batch_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
