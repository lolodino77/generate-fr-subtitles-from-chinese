"""Téléchargement unique des modèles (Internet requis une seule fois), puis tout fonctionne hors ligne.

Usage (dans l'environnement video_ocr) :
    python scripts/download_models.py            # modèle de traduction par défaut : Qwen3-4B GGUF (≈2,5 Go)
    python scripts/download_models.py --all      # + NLLB (converti CTranslate2 int8) + Argos/MiniSBD
    python scripts/download_models.py --only nllb

Les modèles OCR (PP-OCRv6) sont inclus dans le paquet rapidocr : rien à télécharger.

Les modèles sont stockés dans %LOCALAPPDATA%\\video_ocr\\models (ou VIDEO_OCR_CACHE).
Réseau d'entreprise / antivirus inspectant le TLS : définir REQUESTS_CA_BUNDLE et SSL_CERT_FILE
vers un fichier PEM contenant le certificat racine concerné (voir README, « Erreurs fréquentes »).
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from video_ocr.config import load_config
from video_ocr.translation.engines import configure_model_env, ct2_model_path, hf_cache, models_dir


def download_nllb(model: str, cache_dir: str) -> None:
    from huggingface_hub import snapshot_download

    out = ct2_model_path(cache_dir, model)
    print(f"[NLLB] Téléchargement de {model} (≈2,5 Go, une seule fois)…")
    snapshot_download(model, cache_dir=hf_cache(cache_dir), allow_patterns=["*.json", "*.model", "*.bin", "*.safetensors", "*.txt"])
    if (out / "model.bin").exists():
        print(f"[NLLB] Modèle CTranslate2 déjà présent : {out}")
        return
    import ctranslate2.converters

    print(f"[NLLB] Conversion CTranslate2 int8 -> {out}")
    tmp = out.with_name(out.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    ctranslate2.converters.TransformersConverter(snapshot_download(model, cache_dir=hf_cache(cache_dir))).convert(str(tmp), quantization="int8", force=True)
    tmp.rename(out)
    print("[NLLB] OK")


def download_argos(cache_dir: str) -> None:
    import argostranslate.package as P
    import minisbd.models

    print("[Argos] Mise à jour de l'index et installation zh->en, en->fr…")
    P.update_package_index()
    wanted = {("zh", "en"), ("en", "fr")}
    installed = {(p.from_code, p.to_code) for p in P.get_installed_packages()}
    for pkg in P.get_available_packages():
        if (pkg.from_code, pkg.to_code) in wanted - installed:
            P.install_from_path(pkg.download())
    print("[Argos] MiniSBD (découpage des phrases) zh…")
    minisbd.models.get_model_file("zh-hans")
    minisbd.models.get_model_file("en")
    print("[Argos] OK")


def download_llm(cache_dir: str, repo: str, filename: str) -> None:
    from huggingface_hub import hf_hub_download

    print(f"[LLM] Téléchargement {repo}/{filename}…")
    print("[LLM] OK :", hf_hub_download(repo, filename, cache_dir=hf_cache(cache_dir)))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", choices=["nllb", "argos", "llm"], help="Ne télécharger qu'un composant")
    ap.add_argument("--all", action="store_true", help="Télécharger aussi les moteurs alternatifs NLLB et Argos")
    args = ap.parse_args()
    cfg = load_config()
    configure_model_env(cfg.cache_dir)
    print(f"Répertoire des modèles : {models_dir(cfg.cache_dir)}")
    steps = [args.only] if args.only else ["llm"] + (["nllb", "argos"] if args.all else [])
    failures = []
    for step in steps:
        try:
            if step == "nllb":
                download_nllb(cfg.translation.nllb_model, cfg.cache_dir)
            elif step == "argos":
                download_argos(cfg.cache_dir)
            elif step == "llm":
                download_llm(cfg.cache_dir, cfg.translation.llm_repo, cfg.translation.llm_file)
        except Exception as exc:  # noqa: BLE001
            print(f"[{step}] ÉCHEC : {exc}", file=sys.stderr)
            failures.append(step)
    print("Terminé." if not failures else f"Échecs : {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
