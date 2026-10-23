"""Remet à jour les empreintes de configuration des résultats existants, sans rien recalculer.

À lancer après un changement de réglages qui n'affecte pas le contenu produit (ex. suppression d'un champ de la
sonde) : pour chaque étape, l'empreinte est réécrite seulement si la configuration enregistrée dans state.json,
débarrassée des champs supprimés, donne la même empreinte que la configuration actuelle. Une étape dont un
réglage a réellement changé reste périmée et sera recalculée au prochain ``process``.

    python scripts/migrate_hashes.py data/output_instagram_v2 [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import fields
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from video_ocr.config import AppConfig, OcrConfig, config_from_dict, load_config  # noqa: E402
from video_ocr.pipeline.state import step_hashes  # noqa: E402


def _drop_unknown(data: dict) -> dict:
    """Retire d'une configuration enregistrée les champs qui n'existent plus."""
    out = {}
    for sec_field in fields(AppConfig):
        if sec_field.name not in data:
            continue
        value = data[sec_field.name]
        if isinstance(value, dict):
            known = {f.name for f in fields(type(getattr(AppConfig(), sec_field.name)))}
            value = {k: v for k, v in value.items() if k in known}
        out[sec_field.name] = value
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out_root")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()
    current = step_hashes(load_config(args.config))
    for sp in sorted(Path(args.out_root).glob("*/state.json")):
        st = json.loads(sp.read_text(encoding="utf-8"))
        if not st.get("config") or not st.get("steps"):
            print(f"{sp.parent.name}: pas de configuration enregistrée, ignoré")
            continue
        try:
            stored = step_hashes(config_from_dict(_drop_unknown(st["config"])))
        except Exception as exc:  # noqa: BLE001
            print(f"{sp.parent.name}: configuration enregistrée illisible ({exc}), ignoré")
            continue
        kept, stale = [], []
        for step in list(st["steps"]):
            if stored.get(step) == current.get(step):
                st["steps"][step] = current[step]
                kept.append(step)
            else:
                stale.append(step)
        print(f"{sp.parent.name}: conservé {','.join(kept) or '-'} ; à recalculer {','.join(stale) or '-'}")
        if kept and not args.dry_run:
            sp.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
