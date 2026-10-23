"""Interface en ligne de commande.

Exemples :
    python -m video_ocr process data\\instagram -o data\\sorties
    python -m video_ocr process clip.mp4 --strategy band --interval 0.5
    python -m video_ocr preview clip.mp4 --times 1 3 5 -o apercus
    python -m video_ocr login          # une seule fois : connexion à Gemini / ChatGPT (traduction en ligne)
    python -m video_ocr check
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from video_ocr.config import PROJECT_ROOT, load_config
from video_ocr.ingestion.discover import discover_videos
from video_ocr.logging_setup import setup_logging

log = logging.getLogger("video_ocr")


def _overrides(args: argparse.Namespace) -> dict:
    o: dict = {}
    if getattr(args, "interval", None):
        o.setdefault("sampling", {})["ocr_interval_s"] = args.interval
    if getattr(args, "strategy", None):
        o.setdefault("render", {})["strategy"] = args.strategy
    if getattr(args, "engine", None):
        o.setdefault("translation", {})["engine"] = args.engine
    if getattr(args, "roi", None):
        o.setdefault("ocr", {})["roi"] = args.roi
    return o


def cmd_process(args: argparse.Namespace) -> int:
    from video_ocr.pipeline.batch import run_batch

    cfg = load_config(args.config, _overrides(args))
    videos, problems = discover_videos(args.inputs, recursive=args.recursive)
    for p in problems:
        log.warning(p)
    if not videos:
        log.error("Aucune vidéo à traiter")
        return 2
    out = Path(args.output)
    setup_logging(out / "video_ocr.log")

    def progress(i: int, n: int, frac: float, msg: str) -> None:
        print(f"\r[{i + 1}/{n}] {frac:6.1%} {msg[:60]:<60}", end="", file=sys.stderr, flush=True)

    batch = run_batch(videos, out, cfg, progress, force=args.force, redo_from=args.redo_from)
    print(file=sys.stderr)
    for r in batch.results:
        print(f"{r.status:12s} {Path(r.source).name}  segments={r.segments} traduits={r.translated} {r.error}")
    print(f"Rapport : {out / 'batch_report.md'}")
    return 0 if all(r.status in ("complete", "partial") for r in batch.results) else 1


def cmd_preview(args: argparse.Namespace) -> int:
    from video_ocr.ui.preview import preview_ocr_frames

    cfg = load_config(args.config, _overrides(args))
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    for t, img, lines in preview_ocr_frames(Path(args.video), cfg, args.times):
        path = out / f"ocr_{t:06.2f}.png"
        img.save(path)
        print(path, json.dumps([(ln.text, round(ln.score, 3), ln.is_chinese) for ln in lines], ensure_ascii=False))
    return 0


def cmd_login(args: argparse.Namespace) -> int:
    """Ouvre Chrome (profil dédié) sur les sites de traduction pour une connexion manuelle, une seule fois."""
    from video_ocr.translation.browser_llm import BrowserSession, TranslationUnavailable, default_profile_dir

    cfg = load_config(args.config)
    t = cfg.translation
    profile = default_profile_dir(cfg.cache_dir, t.browser_profile)
    sites = args.sites or t.browser_sites
    print(f"Profil du navigateur : {profile}")
    session = BrowserSession(profile, t.browser_channel, headless=False)
    try:
        session.login(sites)
    except TranslationUnavailable as exc:
        print(f"Impossible d'ouvrir le navigateur : {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()
    print("Session enregistrée dans le profil. Vous pouvez lancer « process ».")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    from video_ocr.envcheck import run_checks

    ok = True
    for name, status, detail in run_checks(load_config(args.config)):
        ok &= status != "ÉCHEC"
        print(f"[{status:^7}] {name}: {detail}")
    return 0 if ok else 1


def cmd_verify(args: argparse.Namespace) -> int:
    from video_ocr.export.verify import verify_batch

    results = verify_batch(Path(args.output))
    for r in results:
        print(f"{'OK   ' if r.ok else 'ÉCHEC'} {r.video}")
        for name, detail in r.checks.items():
            print(f"    {name}: {detail}")
        if r.contact_sheet:
            print(f"    planche : {r.contact_sheet}")
    return 0 if results and all(r.ok for r in results) else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="video_ocr", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default=None, help="Fichier YAML de configuration (défaut : config/default.yaml)")
    sub = p.add_subparsers(dest="command", required=True)
    pr = sub.add_parser("process", help="Traiter des vidéos ou dossiers")
    pr.add_argument("inputs", nargs="+")
    pr.add_argument("-o", "--output", default=str(PROJECT_ROOT / "data" / "output"))
    pr.add_argument("--recursive", action="store_true")
    pr.add_argument("--force", action="store_true", help="Ignorer les résultats existants")
    pr.add_argument("--redo-from", choices=["segments", "translation", "render", "export"],
                    help="Recalculer à partir de cette étape (l'OCR déjà faite est réutilisée)")
    pr.add_argument("--interval", type=float, help="Intervalle d'OCR en secondes")
    pr.add_argument("--strategy", choices=["inline", "band"])
    pr.add_argument("--engine", choices=["browser", "llm", "nllb", "argos", "none"])
    pr.add_argument("--roi", type=float, nargs=4, metavar=("X0", "Y0", "X1", "Y1"))
    pr.set_defaults(func=cmd_process)
    pv = sub.add_parser("preview", help="Prévisualiser l'OCR sur quelques images")
    pv.add_argument("video")
    pv.add_argument("--times", type=float, nargs="+", default=[1.0, 3.0, 5.0])
    pv.add_argument("-o", "--output", default=str(PROJECT_ROOT / "data" / "preview"))
    pv.add_argument("--roi", type=float, nargs=4, metavar=("X0", "Y0", "X1", "Y1"))
    pv.set_defaults(func=cmd_preview)
    vf = sub.add_parser("verify", help="Vérifier les vidéos exportées d'un dossier de sortie")
    vf.add_argument("output")
    vf.set_defaults(func=cmd_verify)
    lg = sub.add_parser("login", help="Se connecter une fois à Gemini / ChatGPT dans le navigateur piloté")
    lg.add_argument("--sites", nargs="+", choices=["gemini", "gpt"], help="Sites à ouvrir (défaut : configuration)")
    lg.set_defaults(func=cmd_login)
    ck = sub.add_parser("check", help="Vérifier l'environnement (Conda, FFmpeg, modèles)")
    ck.set_defaults(func=cmd_check)
    return p


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
