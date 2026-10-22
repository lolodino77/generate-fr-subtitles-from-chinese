"""Mesure d'un traitement par lot : durée totale, temps par minute de vidéo, mémoire vive maximale.

Usage : python scripts/measure_run.py <entrées…> -o <sortie> [options de « video_ocr process »]
Le traitement est lancé dans un sous-processus dont la mémoire (RSS) est échantillonnée toutes les 0,5 s.
Résultat : <sortie>/measurements.json
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import psutil


def main() -> int:
    args = sys.argv[1:]
    out = Path(args[args.index("-o") + 1]) if "-o" in args else Path("data/output")
    cmd = [sys.executable, "-m", "video_ocr", "process", *args]
    t0 = time.perf_counter()
    proc = subprocess.Popen(cmd)
    ps = psutil.Process(proc.pid)
    peak = 0
    while proc.poll() is None:
        try:
            rss = ps.memory_info().rss + sum(c.memory_info().rss for c in ps.children(recursive=True))
            peak = max(peak, rss)
        except psutil.Error:
            pass
        time.sleep(0.5)
    elapsed = time.perf_counter() - t0
    summary = json.loads((out / "batch_summary.json").read_text(encoding="utf-8"))
    video_s = sum(r["duration"] for r in summary["results"])
    steps: dict[str, float] = {}
    for r in summary["results"]:
        for k, v in r["timings"].items():
            steps[k] = steps.get(k, 0.0) + v
    result = {
        "command": cmd[3:], "exit_code": proc.returncode, "elapsed_s": round(elapsed, 1),
        "videos": len(summary["results"]), "video_duration_s": round(video_s, 1),
        "seconds_per_video_minute": round(elapsed / (video_s / 60), 1) if video_s else None,
        "peak_rss_mb": round(peak / 1e6), "step_seconds": {k: round(v, 1) for k, v in steps.items()},
    }
    (out / "measurements.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
