"""Génération de vidéos de test avec sous-titres chinois incrustés à des instants connus.

Imite la mise en page observée sur les Reels cibles : texte chinois vert à contour noir,
ligne thaïe en dessous, filigrane fixe, fond animé, et un bip audio au début de chaque
sous-titre (contrôle de la synchronisation audio-vidéo).
"""
from __future__ import annotations

import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from video_ocr.fonts import first_font
from video_ocr.video.ffmpeg_tools import CREATE_NO_WINDOW, FFmpegError, find_binary

CJK_FONT = "msjhbd.ttc"  # Microsoft JhengHei (traditionnel), cherché via video_ocr.fonts
THAI_FONT = "LeelaUIb.ttf"


@dataclass
class SubCue:
    start: float
    end: float
    text: str  # lignes séparées par \n
    thai: str = ""


# Caractères traditionnels distincts du simplifié : 這 個 問 題 難 決 們 該 麼 辦 錢 萬 謝 幫 對
DEFAULT_CUES = [
    SubCue(0.5, 2.5, "這個問題很難解決", "ปัญหานี้แก้ยาก"),
    SubCue(2.5, 4.2, "我們應該怎麼辦？", "เราควรทำอย่างไร"),
    SubCue(4.8, 5.4, "對！"),
    SubCue(6.0, 9.0, "錢不是萬能的\n但沒有錢是萬萬不能的", "เงินไม่ใช่ทุกอย่าง"),
    SubCue(9.6, 11.6, "謝謝你們的幫助", "ขอบคุณ"),
]


def _font(name: str, size: int, fallback: str = "arialbd.ttf") -> ImageFont.FreeTypeFont:
    path = first_font(name, fallback)
    if path is None:
        raise FileNotFoundError(f"Police introuvable : {name}")
    return ImageFont.truetype(str(path), size)


def _background(t: float, w: int, h: int) -> np.ndarray:
    """Fond animé (dégradé qui défile + disque mobile) pour simuler une vidéo filmée."""
    x = np.linspace(0, 1, w)[None, :]
    y = np.linspace(0, 1, h)[:, None]
    r = 90 + 70 * np.sin(2 * np.pi * (x + 0.1 * t))
    g = 110 + 60 * np.cos(2 * np.pi * (y + 0.07 * t))
    b = 140 + 50 * np.sin(2 * np.pi * (x + y + 0.05 * t))
    img = np.stack([np.broadcast_to(r, (h, w)), np.broadcast_to(g, (h, w)), np.broadcast_to(b, (h, w))], axis=-1)
    cx, cy = int(w * (0.5 + 0.3 * np.sin(t))), int(h * 0.55)
    yy, xx = np.ogrid[:h, :w]
    img[(xx - cx) ** 2 + (yy - cy) ** 2 < (w // 6) ** 2] = (230, 200, 170)
    return img.astype(np.uint8)


def draw_frame(t: float, cues: list[SubCue], w: int, h: int, sub_y: float, watermark: str) -> Image.Image:
    img = Image.fromarray(_background(t, w, h))
    d = ImageDraw.Draw(img)
    size = int(w * 0.07)
    f_cn, f_th, f_wm = _font(CJK_FONT, size), _font(THAI_FONT, int(size * 0.8)), _font(CJK_FONT, int(size * 0.5))
    if watermark:
        d.text((int(w * 0.04), int(h * 0.92)), watermark, font=f_wm, fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))
    for cue in cues:
        if cue.start <= t < cue.end:
            y = int(h * sub_y)
            lines = cue.text.split("\n") + ([cue.thai] if cue.thai else [])
            for i, line in enumerate(lines):
                font = f_cn if i < len(cue.text.split("\n")) else f_th
                tw = d.textlength(line, font=font)
                d.text(((w - tw) / 2, y), line, font=font, fill=(40, 255, 40), stroke_width=max(2, size // 12), stroke_fill=(0, 0, 0))
                y += int(size * 1.25)
    return img


def _write_beeps(path: Path, duration: float, times: list[float], rate: int = 48000) -> None:
    n = int(duration * rate)
    audio = np.zeros(n, dtype=np.float32)
    beep = np.sin(2 * np.pi * 1000 * np.arange(int(0.1 * rate)) / rate).astype(np.float32) * 0.5
    for t in times:
        i = int(t * rate)
        audio[i:i + len(beep)] += beep[: max(0, min(len(beep), n - i))]
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes((audio * 32767).astype(np.int16).tobytes())


def make_video(
    out: str | Path, cues: list[SubCue] | None = None, duration: float = 12.0, size: tuple[int, int] = (720, 1280),
    fps: int = 30, sub_y: float = 0.15, watermark: str = "@測試頻道", ffmpeg_path: str = "",
) -> Path:
    """Crée une vidéo MP4 H.264/AAC de test et renvoie son chemin."""
    cues = DEFAULT_CUES if cues is None else cues
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    w, h = size
    wav = out.with_suffix(".wav")
    _write_beeps(wav, duration, [c.start for c in cues])
    cmd = [
        find_binary("ffmpeg", ffmpeg_path), "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{w}x{h}", "-r", str(fps), "-i", "pipe:0", "-i", str(wav), "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-shortest", str(out),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=CREATE_NO_WINDOW)
    assert proc.stdin is not None
    for i in range(int(duration * fps)):
        proc.stdin.write(draw_frame(i / fps, cues, w, h, sub_y, watermark).tobytes())
    proc.stdin.close()
    err = proc.stderr.read() if proc.stderr else b""
    proc.wait()
    wav.unlink(missing_ok=True)
    if proc.returncode != 0:
        raise FFmpegError(err.decode("utf-8", "replace"))
    return out
