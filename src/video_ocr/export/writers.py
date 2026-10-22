"""Fichiers de sortie par vidéo : JSON, tableau bilingue Markdown et rapport de traitement."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from video_ocr.models import Segment
from video_ocr.subtitles.srt import format_timestamp

FLAG_LABELS = {
    "low_confidence": "confiance OCR faible",
    "single_observation": "vu sur une seule image",
    "timing_uncertain": "horodatage incertain",
    "ocr_variants": "lectures OCR divergentes",
    "short": "segment très court",
    "translation_failed": "traduction manquante",
    "overlap_risk": "le français peut chevaucher du texte",
}


def flag_label(flag: str) -> str:
    if flag.startswith("translation_suspect:"):
        return "traduction douteuse (" + flag.split(":", 1)[1] + ")"
    return FLAG_LABELS.get(flag, flag)


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _md_cell(text: str | None) -> str:
    return (text or "").replace("|", "\\|").replace("\n", "<br>")


def write_bilingual_md(path: Path, title: str, segments: list[Segment]) -> Path:
    rows = [
        f"# {title}", "", "| # | Début | Fin | Chinois (original OCR) | Français | Remarques |",
        "|---|---|---|---|---|---|",
    ]
    for s in segments:
        fr = s.translation if s.translation else "**[traduction indisponible]**"
        notes = ", ".join(flag_label(f) for f in s.flags)
        rows.append(
            f"| {s.index} | {format_timestamp(s.start)} | {format_timestamp(s.end)} | {_md_cell(s.text_raw)} | {_md_cell(fr)} | {notes} |"
        )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def write_report_md(path: Path, title: str, summary: dict[str, Any], segments: list[Segment], warnings: list[str]) -> Path:
    """Rapport : statistiques, incertitudes OCR, traductions manquantes, synchronisation."""
    lines = [f"# Rapport de traitement — {title}", ""]
    for key, value in summary.items():
        lines.append(f"- **{key}** : {value}")
    lines += ["", "## Avertissements", ""]
    lines += [f"- {w}" for w in warnings] or ["- Aucun"]
    flagged = [s for s in segments if s.flags]
    lines += ["", f"## Segments signalés ({len(flagged)}/{len(segments)})", ""]
    if flagged:
        lines += ["| # | Temps | Chinois | Français | Problèmes | Score OCR | Incertitude (s) |", "|---|---|---|---|---|---|---|"]
        for s in flagged:
            lines.append(
                f"| {s.index} | {format_timestamp(s.start)} → {format_timestamp(s.end)} | {_md_cell(s.text_raw)} | "
                f"{_md_cell(s.translation or '—')} | {', '.join(flag_label(f) for f in s.flags)} | {s.score:.2f} | {s.timing_uncertainty_s:.2f} |"
            )
    else:
        lines.append("Aucun segment signalé.")
    variants = [s for s in segments if s.variants]
    if variants:
        lines += ["", "## Lectures OCR alternatives (diagnostic)", ""]
        for s in variants:
            lines.append(f"- #{s.index} retenu « {s.text_raw.replace(chr(10), ' / ')} » ; autres : " + " ; ".join(
                f"« {v.replace(chr(10), ' / ')} »" for v in s.variants[:5]))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
