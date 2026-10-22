"""Vérification des vidéos réellement exportées (pas seulement de leur existence).

Pour chaque vidéo traitée : validité du MP4, durée / fréquence d'images / résolution, audio copié
à l'identique (synchronisation préservée), source inchangée, SRT valides, et planche d'images
extraites du fichier exporté au milieu de plusieurs segments (inspection visuelle).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw

from video_ocr.models import Segment
from video_ocr.pipeline.state import VideoState, file_fingerprint, from_portable
from video_ocr.rendering.layout import load_font
from video_ocr.subtitles.srt import validate_srt
from video_ocr.video.ffmpeg_tools import find_binary, probe, run
from video_ocr.video.sampler import grab_frame


@dataclass
class VerifyResult:
    video: str
    ok: bool = True
    checks: dict[str, str] = field(default_factory=dict)
    contact_sheet: str = ""

    def check(self, name: str, passed: bool, detail: str) -> None:
        self.checks[name] = ("OK — " if passed else "ÉCHEC — ") + detail
        self.ok &= passed


def stream_md5(path: Path, selector: str, ffmpeg_path: str = "") -> str:
    """Empreinte MD5 des paquets d'un flux (copie, sans décodage)."""
    out = run([find_binary("ffmpeg", ffmpeg_path), "-v", "error", "-i", str(path), "-map", selector, "-c", "copy", "-f", "md5", "-"])
    return out.stdout.decode().strip()


def contact_sheet(output: Path, segments: list[Segment], dest: Path, n: int = 6, ffmpeg_path: str = "") -> Path:
    """Planche : images du fichier exporté au milieu de ``n`` segments, avec le texte attendu en légende."""
    info = probe(output, ffmpeg_path)
    chosen = [s for s in segments if s.translation]
    if len(chosen) > n:
        step = len(chosen) / n
        chosen = [chosen[int(i * step)] for i in range(n)]
    thumb_w = 300
    thumb_h = int(info.height * thumb_w / info.width)
    caption_h = 110
    sheet = Image.new("RGB", (thumb_w * max(1, len(chosen)), thumb_h + caption_h), "white")
    font = load_font("msjh.ttc", 15)  # Microsoft JhengHei (chinois) ; repli automatique sinon
    draw = ImageDraw.Draw(sheet)
    for i, seg in enumerate(chosen):
        t = (seg.start + seg.end) / 2
        frame = grab_frame(info, t, None, ffmpeg_path)[:, :, ::-1]
        img = Image.fromarray(frame).resize((thumb_w, thumb_h))
        sheet.paste(img, (i * thumb_w, 0))
        lines = [f"#{seg.index} t={t:.2f}s", seg.text_raw.replace("\n", " ")[:18], (seg.translation or "")[:34], (seg.translation or "")[34:68]]
        for j, line in enumerate(lines):
            draw.text((i * thumb_w + 6, thumb_h + 4 + j * 26), line, font=font, fill="black")
    dest.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(dest)
    return dest


def verify_output_dir(out_dir: Path, ffmpeg_path: str = "") -> VerifyResult:
    """Vérifie un dossier de résultats ``<sortie>/<nom_video>/``."""
    state = VideoState.load(out_dir / "state.json")
    stem = out_dir.name
    res = VerifyResult(video=stem)
    if state is None:
        res.check("état", False, "state.json absent")
        return res
    src = from_portable(state.source, out_dir)  # chemin relatif au dossier de résultats
    out = out_dir / f"{stem}_bilingue.mp4"
    res.check("statut", state.status == "complete", state.status)
    if src.exists():
        res.check("source inchangée", file_fingerprint(src) == state.fingerprint, "SHA-256 identique à celui mesuré avant traitement")
    else:
        res.check("source inchangée", False, f"source introuvable : {src}")
    if not out.exists():
        res.check("vidéo exportée", False, "absente")
        return res
    try:
        si, oi = probe(src, ffmpeg_path), probe(out, ffmpeg_path)
    except Exception as exc:  # noqa: BLE001
        res.check("vidéo exportée", False, f"illisible : {exc}")
        return res
    res.check("vidéo exportée", oi.video_codec == "h264", f"{oi.width}×{oi.height}, {oi.fps:.3f} i/s, {oi.duration:.3f} s, {oi.video_codec}/{oi.audio_codec or 'sans audio'}")
    res.check("durée", abs(oi.duration - si.duration) <= max(0.1, 1.5 / si.fps), f"source {si.duration:.3f} s / sortie {oi.duration:.3f} s")
    res.check("fréquence d'images", abs(oi.fps - si.fps) < 0.05, f"source {si.fps:.3f} / sortie {oi.fps:.3f}")
    payload = json.loads((out_dir / f"{stem}.segments.json").read_text(encoding="utf-8"))
    band = payload.get("analysis", {}).get("render", {}).get("band_height", 0)
    res.check("résolution", oi.width == si.width and oi.height == si.height + band, f"source {si.width}×{si.height} / sortie {oi.width}×{oi.height} (bande {band})")
    if si.has_audio:
        same = stream_md5(src, "0:a:0", ffmpeg_path) == stream_md5(out, "0:a:0", ffmpeg_path)
        res.check("audio / synchronisation", same or payload["analysis"]["render"]["audio"] == "aac",
                  "flux audio copié à l'identique (même MD5)" if same else "audio réencodé en AAC")
    for lang in ("zh", "fr"):
        srt = out_dir / f"{stem}.{lang}.srt"
        problems = validate_srt(srt.read_text(encoding="utf-8")) if srt.exists() else ["absent"]
        res.check(f"SRT {lang}", not problems, "valide" if not problems else "; ".join(problems[:3]))
    segments = [Segment.from_dict(d) for d in payload["segments"]]
    if segments:
        res.contact_sheet = str(contact_sheet(out, segments, out_dir / "verification_frames.png", ffmpeg_path=ffmpeg_path))
    return res


def verify_batch(out_root: Path, ffmpeg_path: str = "") -> list[VerifyResult]:
    results = [verify_output_dir(d, ffmpeg_path) for d in sorted(out_root.iterdir()) if (d / "state.json").exists()]
    (out_root / "verification.json").write_text(json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2), encoding="utf-8")
    return results
