"""Écriture et lecture de fichiers SRT (UTF-8)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from video_ocr.models import Segment

_TIME_RE = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})")


@dataclass
class SrtEntry:
    index: int
    start: float
    end: float
    text: str


def format_timestamp(seconds: float) -> str:
    """Secondes -> ``HH:MM:SS,mmm``."""
    ms = int(round(max(0.0, seconds) * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def parse_timestamp(value: str) -> float:
    h, m, rest = value.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def segments_to_srt(segments: list[Segment], field: str) -> str:
    """Construit le contenu SRT pour ``field`` = « chinese » ou « french ».

    Les traductions manquantes sont explicitement marquées au lieu d'être vides.
    """
    blocks = []
    n = 0
    for seg in segments:
        if seg.end <= seg.start:
            continue
        if field == "chinese":
            text = seg.text_raw
        elif field == "french":
            text = seg.translation if seg.translation else "[traduction indisponible]"
        else:
            raise ValueError(field)
        n += 1
        blocks.append(f"{n}\n{format_timestamp(seg.start)} --> {format_timestamp(seg.end)}\n{text.strip()}\n")
    return "\n".join(blocks)


def write_srt(path: str | Path, segments: list[Segment], field: str) -> Path:
    path = Path(path)
    path.write_text(segments_to_srt(segments, field), encoding="utf-8")
    return path


def parse_srt(content: str) -> list[SrtEntry]:
    """Lecture simple d'un SRT (utilisée pour la validation des exports)."""
    entries: list[SrtEntry] = []
    for block in re.split(r"\n\s*\n", content.strip().replace("\r\n", "\n")):
        lines = block.strip().split("\n")
        if len(lines) < 3:
            raise ValueError(f"Bloc SRT invalide : {block!r}")
        match = _TIME_RE.match(lines[1])
        if not match:
            raise ValueError(f"Horodatage SRT invalide : {lines[1]!r}")
        start = parse_timestamp(lines[1].split("-->")[0].strip())
        end = parse_timestamp(lines[1].split("-->")[1].strip())
        entries.append(SrtEntry(int(lines[0]), start, end, "\n".join(lines[2:])))
    return entries


def validate_srt(content: str) -> list[str]:
    """Retourne la liste des problèmes (vide = valide) : ordre, chevauchements, durées."""
    problems = []
    entries = parse_srt(content) if content.strip() else []
    for i, e in enumerate(entries):
        if e.index != i + 1:
            problems.append(f"Numérotation incorrecte au bloc {i + 1}")
        if e.end <= e.start:
            problems.append(f"Durée nulle ou négative au bloc {e.index}")
        if i and e.start < entries[i - 1].end - 1e-3:
            problems.append(f"Chevauchement entre les blocs {entries[i - 1].index} et {e.index}")
    return problems
