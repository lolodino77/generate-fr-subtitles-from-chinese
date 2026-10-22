"""Traitement complet d'une vidéo : OCR -> segments -> traduction -> rendu -> exports."""
from __future__ import annotations

import json
import logging
import shutil
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from video_ocr import __version__
from video_ocr.config import AppConfig
from video_ocr.export.writers import write_bilingual_md, write_json, write_report_md
from video_ocr.models import FrameObservation, Segment, TextLine, VideoInfo
from video_ocr.ocr.analysis import analyse_observations
from video_ocr.ocr.engines import OcrEngine, create_engine as create_ocr_engine
from video_ocr.ocr.text_utils import detect_script
from video_ocr.ocr.video_ocr import Cancelled, run_video_ocr
from video_ocr.pipeline.state import STEPS, VideoState, file_fingerprint, step_hashes, to_portable
from video_ocr.rendering.video_render import render_bilingual_video
from video_ocr.segments.grouping import build_segments, looks_without_subtitles
from video_ocr.subtitles.srt import write_srt
from video_ocr.translation.cache import TranslationCache
from video_ocr.translation.engines import TranslationEngine, create_engine as create_mt_engine
from video_ocr.translation.translator import translate_segments
from video_ocr.video.ffmpeg_tools import probe

log = logging.getLogger(__name__)

ProgressCb = Callable[[float, str], None]
STEP_WEIGHTS = {"ocr": 0.6, "segments": 0.02, "translation": 0.08, "render": 0.28, "export": 0.02}


@dataclass
class OutputPaths:
    root: Path
    stem: str

    def file(self, suffix: str) -> Path:
        return self.root / f"{self.stem}{suffix}"

    @property
    def video(self) -> Path:
        return self.file("_bilingue.mp4")

    @property
    def state(self) -> Path:
        return self.root / "state.json"

    @property
    def observations(self) -> Path:
        return self.root / "observations.json"

    @property
    def segments(self) -> Path:
        return self.file(".segments.json")

    @property
    def work(self) -> Path:
        return self.root / "_work"


@dataclass
class VideoResult:
    source: str
    status: str
    output_dir: str
    video: str = ""
    segments: int = 0
    translated: int = 0
    flagged: int = 0
    error: str = ""
    warnings: list[str] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)
    duration: float = 0.0
    skipped: bool = False
    steps_run: list[str] = field(default_factory=list)  # étapes réellement exécutées lors de cet appel


class Engines:
    """Chargement paresseux et partagé des moteurs pour tout un lot."""

    def __init__(self, cfg: AppConfig, ocr: OcrEngine | None = None, mt: TranslationEngine | None = None) -> None:
        self.cfg = cfg
        self._ocr: OcrEngine | None = ocr
        self._mt: TranslationEngine | None = mt
        self._mt_loaded = mt is not None
        self._cache: TranslationCache | None = None
        self._lock = threading.Lock()

    @property
    def ocr(self) -> OcrEngine:
        with self._lock:
            if self._ocr is None:
                self._ocr = create_ocr_engine(self.cfg.ocr)
            return self._ocr

    @property
    def mt(self) -> TranslationEngine | None:
        with self._lock:
            if not self._mt_loaded:
                self._mt = create_mt_engine(self.cfg.translation, self.cfg.cache_dir)
                self._mt_loaded = True
            return self._mt

    @property
    def cache(self) -> TranslationCache:
        with self._lock:
            if self._cache is None:
                self._cache = TranslationCache(Path(self.cfg.cache_dir) / "translation_cache.sqlite")
            return self._cache


def observations_to_json(obs: list[FrameObservation]) -> list[dict[str, Any]]:
    return [o.to_dict() for o in obs]


def observations_from_json(data: list[dict[str, Any]]) -> list[FrameObservation]:
    result = []
    for d in data:
        lines = [TextLine(ln["text"], ln["score"], tuple(ln["bbox"]), ln["is_chinese"]) for ln in d.get("lines", [])]
        o = FrameObservation(t=d["t"], lines=lines, reused=d.get("reused", False), refined=d.get("refined", False))
        result.append(o)
    return result


def output_paths(video: Path, out_root: Path) -> OutputPaths:
    return OutputPaths(out_root / video.stem, video.stem)


def process_video(
    video: str | Path,
    out_root: str | Path,
    cfg: AppConfig,
    engines: Engines,
    progress: ProgressCb | None = None,
    cancel: threading.Event | None = None,
    force: bool = False,
    redo_from: str | None = None,
) -> VideoResult:
    """Traite une vidéo. Les erreurs sont capturées et reportées dans le résultat (le lot continue)."""
    video = Path(video)
    paths = output_paths(video, Path(out_root))
    paths.root.mkdir(parents=True, exist_ok=True)
    hashes = step_hashes(cfg)
    state = VideoState.load(paths.state) if not force else None
    out_base = Path(out_root)  # chemins du récapitulatif relatifs au dossier de sortie (portables)
    result = VideoResult(source=to_portable(video, out_base), status="failed", output_dir=to_portable(paths.root, out_base))
    done_weight = 0.0

    def report(step: str) -> ProgressCb:
        def cb(frac: float, msg: str) -> None:
            if progress is not None:
                progress(min(1.0, done_weight + STEP_WEIGHTS[step] * frac), msg)
        return cb

    try:
        fingerprint = file_fingerprint(video)
        info = probe(video, cfg.ffmpeg_path)
        result.duration = info.duration
        if state is None or state.fingerprint != fingerprint:
            state = VideoState(source=to_portable(video, paths.root), fingerprint=fingerprint)
        if redo_from:  # recalcul demandé à partir d'une étape (les étapes précédentes sont réutilisées)
            for step in STEPS[STEPS.index(redo_from):]:
                state.steps.pop(step, None)
        start_step = state.first_invalid_step(hashes)
        if start_step is None and paths.video.exists():
            result.status, result.skipped = "complete", True
            result.video = to_portable(paths.video, out_base)
            segs = [Segment.from_dict(d) for d in json.loads(paths.segments.read_text(encoding="utf-8"))["segments"]]
            _fill_counts(result, segs)
            result.warnings = state.warnings
            if progress:
                progress(1.0, "Déjà traité (contenu et paramètres inchangés)")
            return result
        start_idx = STEPS.index(start_step) if start_step else STEPS.index("render")
        for step in STEPS[start_idx:]:
            state.steps.pop(step, None)
        state.status, state.error, state.config = "running", "", cfg.to_dict()
        state.warnings = [] if start_idx == 0 else state.warnings
        state.save(paths.state)
        for i, step in enumerate(STEPS[:start_idx]):
            done_weight += STEP_WEIGHTS[step]

        observations: list[FrameObservation] = []
        segments: list[Segment] = []
        extra: dict[str, Any] = {}
        if start_idx > 0:
            observations = observations_from_json(json.loads(paths.observations.read_text(encoding="utf-8"))["observations"])
        if start_idx > 1:
            payload = json.loads(paths.segments.read_text(encoding="utf-8"))
            segments = [Segment.from_dict(d) for d in payload["segments"]]
            extra = payload.get("analysis", {})

        for step in STEPS[start_idx:]:
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            t0 = time.perf_counter()
            if step == "ocr":
                observations, stats = run_video_ocr(info, cfg, engines.ocr, report("ocr"), cancel)
                write_json(paths.observations, {"video": {**info.__dict__, "path": to_portable(info.path, paths.root)}, "stats": stats.__dict__, "observations": observations_to_json(observations)})
            elif step == "segments":
                analysis = analyse_observations(observations, info.height, cfg.ocr, info.width)
                segments = build_segments(observations, info.duration, cfg)
                no_subtitles = looks_without_subtitles(segments, cfg)
                if no_subtitles:
                    msg = (f"Aucun sous-titre probable : {len(segments)} textes très brefs et instables "
                           "(enseignes ou texte de scène), pas de sous-titres incrustés.")
                    if cfg.segments.drop_when_no_subtitles:
                        segments = []
                        msg += " Ils ne sont ni traduits ni incrustés."
                    state.warnings.append(msg)
                extra = {
                    "zone_center": analysis.zone_center, "static_texts": analysis.static_texts,
                    "frames_with_subtitle": analysis.frames_with_subtitle, "frames_total": analysis.frames_total,
                }
                if not segments and not no_subtitles:
                    state.warnings.append("Aucun sous-titre chinois détecté dans la vidéo.")
                if analysis.static_texts:
                    state.warnings.append("Textes fixes écartés (titre/filigrane) : " + " ; ".join(analysis.static_texts))
                _save_segments(paths, info, segments, extra, cfg)
            elif step == "translation":
                mt_stats = translate_segments(segments, engines.mt, cfg.translation, engines.cache, report("translation"))
                extra["translation_stats"] = mt_stats.__dict__
                if mt_stats.failed:
                    state.warnings.append(f"{mt_stats.failed} segment(s) sans traduction.")
                _save_segments(paths, info, segments, extra, cfg)
            elif step == "render":
                if not any(s.translation for s in segments):
                    state.warnings.append("Aucune traduction : la vidéo de sortie est identique visuellement à la source.")
                res = render_bilingual_video(segments, info, cfg.render, paths.video, paths.work, cfg.ffmpeg_path, report("render"), cancel)
                for seg in segments:
                    pl = res.placements.get(seg.index)
                    if pl is not None and pl.overlap_risk and "overlap_risk" not in seg.flags:
                        seg.flags.append("overlap_risk")
                extra["render"] = {
                    "output": res.output.name, "width": res.geometry.width, "height": res.geometry.height,
                    "band_height": res.geometry.band_height, "audio": res.audio_mode,
                    "placements": {str(k): {"mode": p.mode, "box": p.box, "font_size": p.font_size, "lines": p.lines} for k, p in res.placements.items()},
                }
                _save_segments(paths, info, segments, extra, cfg)
                shutil.rmtree(paths.work, ignore_errors=True)
            elif step == "export":
                _export(paths, video, info, segments, extra, state, fingerprint)
            state.timings[step] = round(time.perf_counter() - t0, 2)
            state.steps[step] = hashes[step]
            result.steps_run.append(step)
            state.save(paths.state)
            done_weight += STEP_WEIGHTS[step]

        if file_fingerprint(video) != fingerprint:
            raise RuntimeError("La vidéo source a été modifiée pendant le traitement !")
        state.status = "complete" if segments else "partial"
        state.save(paths.state)
        result.status = state.status
        result.video = to_portable(paths.video, out_base)
        _fill_counts(result, segments)
    except Cancelled:
        if state is not None:
            state.status = "interrupted"
            state.save(paths.state)
        result.status = "interrupted"
        result.error = "Annulé par l'utilisateur"
    except InterruptedError:
        if state is not None:
            state.status = "interrupted"
            state.save(paths.state)
        result.status, result.error = "interrupted", "Annulé par l'utilisateur"
    except Exception as exc:  # noqa: BLE001 - une vidéo en échec ne bloque pas le lot
        log.exception("Échec du traitement de %s", video)
        result.status, result.error = "failed", f"{type(exc).__name__}: {exc}"
        if state is not None:
            state.status, state.error = "failed", result.error
            state.save(paths.state)
    if state is not None:
        result.warnings = list(state.warnings)
        result.timings = dict(state.timings)
    return result


def _fill_counts(result: VideoResult, segments: list[Segment]) -> None:
    result.segments = len(segments)
    result.translated = sum(1 for s in segments if s.translation)
    result.flagged = sum(1 for s in segments if s.flags)


def _save_segments(paths: OutputPaths, info: VideoInfo, segments: list[Segment], extra: dict[str, Any], cfg: AppConfig) -> None:
    write_json(paths.segments, {
        "app_version": __version__, "source": to_portable(info.path, paths.root),
        "video": {**info.__dict__, "path": to_portable(info.path, paths.root)}, "analysis": extra,
        "parameters": cfg.to_dict(), "segments": [s.to_dict() for s in segments],
    })


def _export(paths: OutputPaths, video: Path, info: VideoInfo, segments: list[Segment], extra: dict[str, Any], state: VideoState, fingerprint: str) -> None:
    write_srt(paths.file(".zh.srt"), segments, "chinese")
    write_srt(paths.file(".fr.srt"), segments, "french")
    write_bilingual_md(paths.file(".bilingue.md"), video.name, segments)
    scripts = {detect_script(s.text_raw) for s in segments} - {"none"}
    mt = extra.get("translation_stats", {})
    summary = {
        "Vidéo source": f"{video.name} (inchangée, SHA-256 {fingerprint[:16]}…)",
        "Durée": f"{info.duration:.2f} s, {info.width}×{info.height}, {info.fps:.2f} i/s",
        "Vidéo bilingue": paths.video.name,
        "Segments": len(segments),
        "Traductions présentes": sum(1 for s in segments if s.translation),
        "Traductions manquantes": sum(1 for s in segments if not s.translation),
        "Traductions douteuses": mt.get("suspect", 0),
        "Segments signalés": sum(1 for s in segments if s.flags),
        "Écriture chinoise détectée": ", ".join(sorted(scripts)) or "—",
        "Zone des sous-titres (centre vertical)": f"{extra['zone_center']:.0%}" if extra.get("zone_center") is not None else "—",
        "Images avec sous-titre / analysées": f"{extra.get('frames_with_subtitle', 0)}/{extra.get('frames_total', 0)}",
        "Placement du français": ", ".join(sorted({p['mode'] for p in extra.get('render', {}).get('placements', {}).values()})) or "—",
        "Durées des étapes (s)": json.dumps(state.timings, ensure_ascii=False),
    }
    write_report_md(paths.file(".rapport.md"), video.name, summary, segments, state.warnings)
