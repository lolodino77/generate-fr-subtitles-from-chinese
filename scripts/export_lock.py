"""Fige l'environnement Conda « video_ocr » réellement installé, pour le reproduire à l'identique.

Usage (environnement video_ocr activé) :
    python scripts/export_lock.py

Produit à la racine du projet :
    requirements-lock.txt     toutes les bibliothèques Python installées par pip, versions exactes
    environment-lock.yml      paquets Conda exacts (Python, FFmpeg…) + requirements-lock.txt
    conda-lock-win-64.txt     liste Conda explicite (URL + empreintes) pour Windows 64 bits

Les paquets fournis par Conda (pip, setuptools, wheel, packaging…) sont exclus du verrou pip,
ainsi que l'installation éditable du projet lui-même (réinstallée par « -e . »).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_NAME = "video_ocr"
PIP_HEADER = """# Verrou EXACT de l'environnement video_ocr (généré par scripts/export_lock.py — ne pas éditer à la main).
# Installation : python -m pip install -r requirements-lock.txt
--extra-index-url https://download.pytorch.org/whl/cpu
--extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
--only-binary=llama-cpp-python
"""


def run(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=True, encoding="utf-8").stdout


def conda_packages() -> set[str]:
    """Noms des paquets installés par Conda (canal != pypi)."""
    names = set()
    for line in run(["conda", "list", "-n", ENV_NAME]).splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split()
        if len(parts) >= 3 and parts[-1] != "pypi":
            names.add(parts[0].lower().replace("_", "-"))
    return names


def export_pip(conda_names: set[str]) -> list[str]:
    kept = []
    for line in run([sys.executable, "-m", "pip", "freeze", "--all"]).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-e "):
            continue
        name = line.split("==")[0].split(" @ ")[0].strip().lower().replace("_", "-")
        if name in conda_names or " @ file:" in line or name == "video-ocr":
            continue
        kept.append(line)
    return sorted(kept, key=str.lower)


def export_conda() -> list[str]:
    deps = []
    in_deps = False
    for line in run(["conda", "env", "export", "-n", ENV_NAME, "--no-builds"]).splitlines():
        if line.startswith("dependencies:"):
            in_deps = True
            continue
        if in_deps:
            stripped = line.strip()
            if stripped.startswith("- pip:") or line.startswith("prefix:") or not line.startswith("  "):
                break
            if stripped.startswith("- "):
                deps.append(stripped[2:])
    return deps


def main() -> int:
    if Path(sys.prefix).name != ENV_NAME:
        print(f"À lancer dans l'environnement {ENV_NAME} (actuel : {sys.prefix})", file=sys.stderr)
        return 1
    conda_names = conda_packages()
    pip_lines = export_pip(conda_names)
    (ROOT / "requirements-lock.txt").write_text(PIP_HEADER + "\n".join(pip_lines) + "\n", encoding="utf-8")
    deps = export_conda()
    yml = [
        "# Verrou EXACT de l'environnement video_ocr (généré par scripts/export_lock.py).",
        "# Création : conda env create -f environment-lock.yml",
        f"name: {ENV_NAME}",
        "channels:",
        "  - conda-forge",
        "  - nodefaults",
        "dependencies:",
        *[f"  - {d}" for d in deps],
        "  - pip:",
        "      - -r requirements-lock.txt",
        "      - -e .",
    ]
    (ROOT / "environment-lock.yml").write_text("\n".join(yml) + "\n", encoding="utf-8")
    explicit = run(["conda", "list", "-n", ENV_NAME, "--explicit", "--md5"])
    (ROOT / "conda-lock-win-64.txt").write_text(explicit, encoding="utf-8")
    print(f"requirements-lock.txt : {len(pip_lines)} paquets pip")
    print(f"environment-lock.yml  : {len(deps)} paquets conda")
    print("conda-lock-win-64.txt : liste explicite Windows 64 bits")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
