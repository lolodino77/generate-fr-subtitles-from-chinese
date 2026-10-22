"""Traduction des segments : déduplication, cache, isolation des erreurs, signalement des doutes."""
from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass

from video_ocr.config import TranslationConfig
from video_ocr.models import Segment
from video_ocr.ocr.text_utils import count_cjk
from video_ocr.translation.cache import TranslationCache
from video_ocr.translation.engines import TranslationEngine

log = logging.getLogger(__name__)

BATCH_SIZE = 8


@dataclass
class TranslationStats:
    unique_texts: int = 0
    cache_hits: int = 0
    translated: int = 0
    failed: int = 0
    suspect: int = 0


def source_text(seg: Segment, cfg: TranslationConfig) -> str:
    """Texte envoyé au traducteur (lignes du sous-titre jointes ; simplifié par défaut, meilleur pour NLLB/Argos)."""
    return seg.text_simplified if cfg.normalize_to == "simplified" else seg.text_normalized


def suspicious(source: str, target: str) -> str | None:
    """Raison pour laquelle une traduction semble douteuse, ou None."""
    if not target.strip():
        return "empty"
    if count_cjk(target) > 0:
        return "untranslated_chinese"
    words = re.findall(r"\w+", target.lower())
    if len(words) >= 6:
        half = len(words) // 2
        if words[:half] == words[half:2 * half]:
            return "repetition"
    sentences = [s.strip() for s in re.split(r"[.!?]", target) if s.strip()]
    if len(sentences) >= 2 and len(set(sentences)) < len(sentences):
        return "repetition"
    n_src = max(1, count_cjk(source))
    if len(target) > 12 * n_src + 40:
        return "too_long"
    return None


def translate_segments(
    segments: list[Segment],
    engine: TranslationEngine | None,
    cfg: TranslationConfig,
    cache: TranslationCache | None,
    progress: Callable[[float, str], None] | None = None,
) -> TranslationStats:
    """Traduit les segments sur place. Une erreur n'interrompt pas les autres segments."""
    stats = TranslationStats()
    if engine is None:
        for seg in segments:
            seg.translation, seg.translation_status = None, "skipped"
        return stats
    if getattr(engine, "supports_context", False):
        return _translate_with_context(segments, engine, cfg, cache, stats, progress)
    by_text: dict[str, list[Segment]] = {}
    for seg in segments:
        by_text.setdefault(source_text(seg, cfg), []).append(seg)
    stats.unique_texts = len(by_text)
    results: dict[str, str] = {}
    todo: list[str] = []
    for text in by_text:
        cached = cache.get(engine.name, text) if cache else None
        if cached is not None:
            results[text] = cached
            stats.cache_hits += 1
        else:
            todo.append(text)
    failures: dict[str, str] = {}
    for i in range(0, len(todo), BATCH_SIZE):
        batch = todo[i:i + BATCH_SIZE]
        try:
            outs = engine.translate_batch(batch)
        except Exception as exc:  # noqa: BLE001 - repli segment par segment
            log.warning("Échec du lot de traduction (%s), nouvel essai texte par texte", exc)
            outs = []
            for text in batch:
                try:
                    outs.append(engine.translate_batch([text])[0])
                except Exception as exc2:  # noqa: BLE001
                    log.error("Traduction impossible pour %r : %s", text, exc2)
                    failures[text] = str(exc2)
                    outs.append("")
        for text, out in zip(batch, outs):
            if text in failures:
                continue
            out = out.strip()
            results[text] = out
            if cache and out:
                cache.put(engine.name, text, out)
            stats.translated += 1
        if progress is not None:
            progress(min(1.0, (i + len(batch)) / max(1, len(todo))), "Traduction")
    for text, segs in by_text.items():
        for seg in segs:
            if text in failures:
                seg.translation, seg.translation_status = None, "failed"
                seg.flags.append("translation_failed")
                stats.failed += 1
                continue
            seg.translation = results.get(text) or None
            seg.translation_status = "ok" if seg.translation else "failed"
            if not seg.translation:
                seg.flags.append("translation_failed")
                stats.failed += 1
                continue
            reason = suspicious(text, seg.translation)
            if reason:
                seg.flags.append(f"translation_suspect:{reason}")
                stats.suspect += 1
    return stats


def _apply(seg: Segment, text: str, out: str | None, stats: TranslationStats) -> None:
    """Enregistre le résultat d'un segment et ses éventuels signalements."""
    seg.translation = out or None
    seg.translation_status = "ok" if seg.translation else "failed"
    if not seg.translation:
        seg.flags.append("translation_failed")
        stats.failed += 1
        return
    reason = suspicious(text, seg.translation)
    if reason:
        seg.flags.append(f"translation_suspect:{reason}")
        stats.suspect += 1


def _translate_with_context(
    segments: list[Segment], engine: TranslationEngine, cfg: TranslationConfig,
    cache: TranslationCache | None, stats: TranslationStats, progress: Callable[[float, str], None] | None,
) -> TranslationStats:
    """Moteurs contextuels (LLM) : chaque segment est traduit avec ses voisins comme contexte."""
    texts = [source_text(s, cfg) for s in segments]
    stats.unique_texts = len(set(texts))
    n_ctx = cfg.llm_context_segments
    for i, (seg, text) in enumerate(zip(segments, texts)):
        before, after = texts[max(0, i - n_ctx):i], texts[i + 1:i + 2]
        context = "\x01".join(before) + "\x02" + "\x01".join(after)
        out = cache.get(engine.name, text, context) if cache else None
        if out is not None:
            stats.cache_hits += 1
        else:
            try:
                out = engine.translate_with_context(text, before, after).strip()  # type: ignore[attr-defined]
                if not out or count_cjk(out):  # nouvel essai sans contexte
                    out = engine.translate_with_context(text, [], []).strip()  # type: ignore[attr-defined]
                stats.translated += 1
                if cache and out:
                    cache.put(engine.name, text, out, context)
            except Exception as exc:  # noqa: BLE001
                log.error("Traduction impossible pour %r : %s", text, exc)
                out = None
        _apply(seg, text, out, stats)
        if progress is not None:
            progress((i + 1) / max(1, len(segments)), "Traduction")
    return stats
