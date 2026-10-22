"""Vérification de l'environnement : Conda video_ocr, FFmpeg, dépendances, modèles, police."""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

from video_ocr.config import AppConfig
from video_ocr.translation.engines import ct2_model_path, models_dir

Check = tuple[str, str, str]  # (nom, statut OK/ATTENTION/ÉCHEC, détail)


def _cached_hf_file(cache_dir: str, repo: str, filename: str) -> Path | None:
    """Chemin du fichier dans le cache Hugging Face local, sans accès réseau."""
    snapshots = models_dir(cache_dir) / "hf" / "hub" / ("models--" + repo.replace("/", "--")) / "snapshots"
    found = sorted(snapshots.glob(f"*/{filename}")) if snapshots.exists() else []
    return found[0] if found else None


def run_checks(cfg: AppConfig) -> list[Check]:
    checks: list[Check] = []
    prefix = Path(sys.prefix)
    env_name = os.environ.get("CONDA_DEFAULT_ENV", "")
    in_env = prefix.name == "video_ocr"
    checks.append(("Environnement Conda", "OK" if in_env else "ÉCHEC",
                   f"sys.prefix={prefix} (CONDA_DEFAULT_ENV={env_name or '—'})"))
    checks.append(("Python", "OK" if sys.version_info[:2] == (3, 11) else "ATTENTION", sys.version.split()[0]))
    try:
        from video_ocr.video.ffmpeg_tools import find_binary, run

        ff = find_binary("ffmpeg", cfg.ffmpeg_path)
        ver = run([ff, "-version"]).stdout.decode("utf-8", "replace").splitlines()[0]
        checks.append(("FFmpeg", "OK" if str(prefix) in ff else "ATTENTION", f"{ff} — {ver}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(("FFmpeg", "ÉCHEC", str(exc)))
    for mod in ["numpy", "cv2", "PIL", "rapidocr", "onnxruntime", "opencc", "llama_cpp", "huggingface_hub", "streamlit", "yaml"]:
        try:
            m = importlib.import_module(mod)
            checks.append((f"Module {mod}", "OK", getattr(m, "__version__", "")))
        except Exception as exc:  # noqa: BLE001
            checks.append((f"Module {mod}", "ÉCHEC", str(exc)))
    for mod in ["ctranslate2", "transformers", "argostranslate", "paddleocr"]:
        try:
            importlib.import_module(mod)
            checks.append((f"Module optionnel {mod}", "OK", ""))
        except Exception:  # noqa: BLE001
            checks.append((f"Module optionnel {mod}", "ATTENTION", "non installé (optionnel)"))
    llm = _cached_hf_file(cfg.cache_dir, cfg.translation.llm_repo, cfg.translation.llm_file)
    needed = cfg.translation.engine == "llm"
    checks.append((f"Modèle LLM {cfg.translation.llm_file}", "OK" if llm else ("ÉCHEC" if needed else "ATTENTION"),
                   str(llm) if llm else "absent — lancez scripts/download_models.py"))
    ct2 = ct2_model_path(cfg.cache_dir, cfg.translation.nllb_model)
    needed = cfg.translation.engine == "nllb"
    checks.append(("Modèle NLLB (CTranslate2 int8)", "OK" if (ct2 / "model.bin").exists() else ("ÉCHEC" if needed else "ATTENTION"),
                   f"{ct2} — optionnel : scripts/download_models.py --only nllb"))
    tok = models_dir(cfg.cache_dir) / "hf"
    checks.append(("Cache Hugging Face (tokenizer)", "OK" if tok.exists() else "ATTENTION", str(tok)))
    from video_ocr.fonts import find_font

    font = find_font(cfg.render.font_path)
    checks.append(("Police française", "OK" if font else "ATTENTION",
                   f"{cfg.render.font_path} -> {font or 'introuvable (police de repli utilisée)'}"))
    return checks
