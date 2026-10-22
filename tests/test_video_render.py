"""Tests d'intégration FFmpeg (sans modèle) : extraction, rendu bilingue, source intacte, sync A/V."""
import hashlib
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from video_ocr.config import AppConfig, RenderConfig
from video_ocr.models import Segment
from video_ocr.rendering.layout import load_font, output_geometry, place, wrap_text
from video_ocr.rendering.video_render import render_bilingual_video
from video_ocr.video.ffmpeg_tools import FFmpegError, find_binary, probe, run
from video_ocr.video.sampler import decode_geometry, grab_frame, iter_frames

FR = "Merci beaucoup pour votre aide, élève très appliqué à l'école"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stream_md5(path: Path, selector: str) -> str:
    """Empreinte des paquets d'un flux copié (sans décodage)."""
    out = run([find_binary("ffmpeg"), "-v", "error", "-i", str(path), "-map", selector, "-c", "copy", "-f", "md5", "-"])
    return out.stdout.decode().strip()


def test_probe_and_frame_extraction(short_video: Path) -> None:
    info = probe(short_video)
    assert (info.width, info.height, round(info.fps)) == (360, 640, 30)
    assert info.has_audio and abs(info.duration - 4.0) < 0.05
    geo = decode_geometry(info, 180)
    frames = list(iter_frames(info, 4, geo))
    times = [t for t, _ in frames]
    assert 14 <= len(frames) <= 18
    assert times[0] == pytest.approx(0.0)
    # horodatages = images source réelles (multiples de 1/30 s), espacées d'environ 1/4 s
    assert all(abs(t * 30 - round(t * 30)) < 1e-3 for t in times)
    assert all(0.2 <= b - a <= 0.3 for a, b in zip(times, times[1:]))
    assert frames[0][1].shape == (geo.height, geo.width, 3)
    assert grab_frame(info, 2.0).shape == (640, 360, 3)


def test_invalid_file_raises(tmp_path: Path) -> None:
    bad = tmp_path / "cassé.mp4"
    bad.write_bytes(b"pas une video")
    with pytest.raises(FFmpegError):
        probe(bad)
    with pytest.raises(FileNotFoundError):
        probe(tmp_path / "absent.mp4")


def test_french_font_has_accents() -> None:
    font = load_font(RenderConfig().font_path, 40)
    for ch in "éèêàçùôœÉ":
        assert font.getmask(ch).getbbox() is not None, ch


def test_wrap_and_placement() -> None:
    cfg = RenderConfig()
    geo = output_geometry(720, 1280, cfg)
    font = load_font(cfg.font_path, 30)
    lines = wrap_text(FR, font, 300)
    assert len(lines) > 1 and all(font.getlength(ln) <= 300 for ln in lines)
    below = place(FR, geo, (100, 180, 620, 300), cfg)
    assert below.mode == "below" and below.box[1] > 300 and not below.overlap_risk
    low_block = place(FR, geo, (100, 1100, 620, 1230), cfg)
    assert low_block.mode == "above" and low_block.box[3] < 1100
    band_cfg = RenderConfig(strategy="band")
    bgeo = output_geometry(720, 1280, band_cfg)
    assert bgeo.height % 2 == 0 and bgeo.height > 1280
    band = place(FR, bgeo, (100, 180, 620, 300), band_cfg)
    assert band.mode == "band" and band.box[1] >= 1280


def _segments() -> list[Segment]:
    return [Segment(1, 1.0, 3.0, "謝謝你們的幫助", translation=FR, block_bbox=(40, 450, 320, 500))]


@pytest.mark.parametrize("strategy", ["inline", "band"])
def test_render_bilingual_video(short_video: Path, tmp_path: Path, strategy: str) -> None:
    cfg = AppConfig()
    cfg.render.strategy = strategy
    cfg.render.preset = "ultrafast"
    src_hash = sha(short_video)
    info = probe(short_video)
    out = tmp_path / f"out_{strategy}.mp4"
    res = render_bilingual_video(_segments(), info, cfg.render, out, tmp_path / "work")
    assert sha(short_video) == src_hash  # source intacte
    o = probe(out)
    assert o.width == 360 and round(o.fps) == 30 and abs(o.duration - info.duration) < 0.05
    if strategy == "inline":
        assert o.height == 640  # résolution conservée (stratégie A)
    else:
        assert o.height > 640
    # Audio copié tel quel : mêmes paquets -> synchronisation audio-vidéo préservée
    assert res.audio_mode == "copy"
    assert stream_md5(out, "0:a:0") == stream_md5(short_video, "0:a:0")
    # Le français est visible pendant le segment, absent en dehors
    box = res.placements[1].box
    src_frame = grab_frame(info, 2.0).astype(int)
    during, before = grab_frame(o, 2.0).astype(int), grab_frame(o, 0.5).astype(int)
    x0, y0, x1, y1 = box
    if strategy == "inline":
        assert np.abs(during[y0:y1, x0:x1] - src_frame[y0:y1, x0:x1]).mean() > 30
        assert np.abs(before[y0:y1, x0:x1] - grab_frame(info, 0.5).astype(int)[y0:y1, x0:x1]).mean() < 6
        # le bloc chinois (au-dessus du français) n'est pas modifié
        assert np.abs(during[450:500, 40:320] - src_frame[450:500, 40:320]).mean() < 6
    else:
        assert during[y0:y1, x0:x1].mean() > before[y0:y1, x0:x1].mean() + 20
        assert np.abs(during[:640] - src_frame).mean() < 6
    Image.fromarray(during[:, :, ::-1].astype(np.uint8)).save(tmp_path / f"frame_{strategy}.png")
