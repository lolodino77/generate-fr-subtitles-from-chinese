"""Mesure d'indicateurs « sous-titres présents ? » sur un échantillon d'images (calibrage de l'écart anticipé).

Usage : python scripts/probe_samples.py data/instagram/*.mp4 [--frames 20]

Pour chaque vidéo : même sonde que le pipeline (OCR de N images réparties sur toute la durée, image entière),
indicateurs et décision. Sert à vérifier qu'un seuil sépare bien des vidéos connues ; n'écrit rien.
"""
from __future__ import annotations

import argparse
import os
import time

from video_ocr.config import load_config
from video_ocr.ocr.engines import create_engine
from video_ocr.ocr.video_ocr import probe_subtitles
from video_ocr.video.ffmpeg_tools import probe
from video_ocr.video.sampler import decode_geometry


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("videos", nargs="+")
    ap.add_argument("--frames", type=int, default=20)
    args = ap.parse_args()
    cfg = load_config()
    engine = create_engine(cfg.ocr)
    for path in args.videos:
        info = probe(path)
        t0 = time.perf_counter()
        result = probe_subtitles(info, cfg, engine, decode_geometry(info, cfg.sampling.max_ocr_width), args.frames)
        verdict = f"ÉCARTÉE ({result.no_subtitles_reason})" if result.no_subtitles_reason else "traitée"
        print(f"{os.path.basename(path):18s} {time.perf_counter() - t0:5.1f}s  {verdict}  {result.indicators.to_dict()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
