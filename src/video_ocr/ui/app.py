"""Interface Streamlit locale. Lancement : ``streamlit run src/video_ocr/ui/app.py`` (ou scripts/launch.ps1)."""
from __future__ import annotations

import json
import os
import time
from dataclasses import replace
from pathlib import Path

import streamlit as st

from video_ocr.config import PROJECT_ROOT, AppConfig, load_config
from video_ocr.export.writers import flag_label
from video_ocr.ingestion.discover import discover_videos
from video_ocr.logging_setup import setup_logging
from video_ocr.models import Segment
from video_ocr.ocr.engines import create_engine
from video_ocr.pipeline.processor import output_paths
from video_ocr.ui.jobs import JobManager, native_dialog
from video_ocr.ui.preview import frame_from_output, preview_bilingual, preview_ocr_frames

st.set_page_config(page_title="Sous-titres bilingues 中文 → FR", page_icon="🎬", layout="wide")
setup_logging(PROJECT_ROOT / "data" / "logs" / "app.log")


@st.cache_resource
def job_manager() -> JobManager:
    return JobManager()


@st.cache_resource
def preview_ocr_engine(engine: str, version: str, model_type: str):  # type: ignore[no-untyped-def]
    cfg = AppConfig()
    cfg.ocr = replace(cfg.ocr, engine=engine, rapid_ocr_version=version, rapid_model_type=model_type)
    return create_engine(cfg.ocr)


def _init_state() -> None:
    ss = st.session_state
    ss.setdefault("inputs", [])
    ss.setdefault("out_dir", str(PROJECT_ROOT / "data" / "output"))


def sidebar_settings(base: AppConfig) -> AppConfig:
    """Réglages exposés à l'utilisateur ; renvoie une configuration complète."""
    cfg = base
    sb = st.sidebar
    sb.header("Réglages")
    with sb.expander("Échantillonnage et OCR", expanded=True):
        cfg.sampling.ocr_interval_s = st.slider("Une image analysée toutes les (s)", 0.25, 2.0, cfg.sampling.ocr_interval_s, 0.25,
                                                help="Plus petit = phrases courtes mieux captées, traitement plus long.")
        cfg.sampling.refine_boundaries = st.checkbox("Affiner débuts/fins des phrases", cfg.sampling.refine_boundaries)
        use_roi = st.checkbox("Limiter l'OCR à une zone (ROI)", cfg.ocr.roi is not None,
                              help="Par défaut toute l'image est analysée et la zone des sous-titres est détectée automatiquement.")
        if use_roi:
            roi = cfg.ocr.roi or [0.0, 0.0, 1.0, 0.5]
            y = st.slider("Zone verticale (% de la hauteur)", 0, 100, (int(roi[1] * 100), int(roi[3] * 100)))
            x = st.slider("Zone horizontale (% de la largeur)", 0, 100, (int(roi[0] * 100), int(roi[2] * 100)))
            cfg.ocr.roi = [x[0] / 100, y[0] / 100, x[1] / 100, y[1] / 100]
        else:
            cfg.ocr.roi = None
        cfg.ocr.remove_static_text = st.checkbox("Ignorer les textes fixes (titre, filigrane)", cfg.ocr.remove_static_text)
    with sb.expander("Traduction"):
        engines = ["browser", "llm", "nllb", "argos", "none"]
        labels = {"browser": "LLM en ligne gratuit via Chrome (Gemini, ChatGPT) — recommandé",
                  "llm": "Qwen3-4B, LLM local (hors ligne, plus lent)", "nllb": "NLLB-200 (rapide)",
                  "argos": "Argos Translate (léger)", "none": "Aucune traduction"}
        cfg.translation.engine = st.selectbox("Moteur local", engines, engines.index(cfg.translation.engine), format_func=labels.get)
    with sb.expander("Rendu du français", expanded=True):
        strategies = ["inline", "band"]
        cfg.render.strategy = st.radio("Stratégie", strategies, strategies.index(cfg.render.strategy),
                                       format_func={"inline": "A — dans l'image, sous le chinois", "band": "B — bande ajoutée en bas"}.get)
        if cfg.render.strategy == "inline":
            positions = ["below", "above", "bottom"]
            cfg.render.position = st.selectbox("Position", positions, positions.index(cfg.render.position),
                                               format_func={"below": "Sous le chinois", "above": "Au-dessus du chinois", "bottom": "Bas de l'image"}.get)
        else:
            cfg.render.band_height_ratio = st.slider("Hauteur de la bande (% de la hauteur)", 8, 35, int(cfg.render.band_height_ratio * 100)) / 100
        cfg.render.font_size_ratio = st.slider("Taille du texte (% de la largeur)", 2.5, 7.0, cfg.render.font_size_ratio * 100, 0.1) / 100
        cfg.render.font_path = st.text_input("Police (.ttf)", cfg.render.font_path)
        c1, c2 = st.columns(2)
        cfg.render.text_color = c1.color_picker("Texte", cfg.render.text_color)
        cfg.render.outline_color = c2.color_picker("Contour", cfg.render.outline_color)
        cfg.render.background_color = c1.color_picker("Fond", cfg.render.background_color)
        cfg.render.outline_width_ratio = c2.slider("Contour", 0.0, 0.2, cfg.render.outline_width_ratio, 0.01)
        cfg.render.background_opacity = st.slider("Opacité du fond", 0.0, 1.0, cfg.render.background_opacity, 0.05)
        cfg.render.line_spacing = st.slider("Interligne", 1.0, 1.8, cfg.render.line_spacing, 0.05)
        cfg.render.margin_ratio = st.slider("Marges latérales (%)", 0, 15, int(cfg.render.margin_ratio * 100)) / 100
        cfg.render.max_lines = st.slider("Lignes maximum", 1, 5, cfg.render.max_lines)
    return cfg


def input_panel() -> list[Path]:
    ss = st.session_state
    st.subheader("1. Vidéos et dossier de sortie")
    c1, c2, c3 = st.columns([1, 1, 2])
    if c1.button("📄 Choisir des vidéos…"):
        ss.inputs = sorted(set(ss.inputs) | set(native_dialog("files")))
    if c2.button("📁 Choisir un dossier…"):
        ss.inputs = sorted(set(ss.inputs) | set(native_dialog("dir")))
    typed = c3.text_input("…ou coller un chemin (fichier ou dossier) puis Entrée", "")
    if typed and typed.strip('"') not in ss.inputs:
        ss.inputs = sorted(set(ss.inputs) | {typed.strip('"')})
    uploads = st.file_uploader("…ou déposer des fichiers (copiés dans data/input)", type=["mp4", "mov", "mkv", "m4v"], accept_multiple_files=True)
    if uploads:
        dest = PROJECT_ROOT / "data" / "input"
        dest.mkdir(parents=True, exist_ok=True)
        for up in uploads:
            target = dest / Path(up.name).name
            if not target.exists():
                target.write_bytes(up.getbuffer())
            ss.inputs = sorted(set(ss.inputs) | {str(target)})
    videos, problems = discover_videos(ss.inputs) if ss.inputs else ([], [])
    for p in problems:
        st.warning(p)
    if videos:
        st.write(f"**{len(videos)} vidéo(s)** : " + ", ".join(v.name for v in videos))
        if st.button("Vider la sélection"):
            ss.inputs = []
            st.rerun()
    o1, o2 = st.columns([3, 1])
    ss.out_dir = o1.text_input("Dossier de sortie", ss.out_dir)
    if o2.button("📁 Parcourir…", key="out_browse"):
        chosen = native_dialog("dir", ss.out_dir)
        if chosen:
            ss.out_dir = chosen[0]
            st.rerun()
    return videos


def ocr_preview_tab(videos: list[Path], cfg: AppConfig) -> None:
    st.caption("Vérifiez sur quelques images que les sous-titres chinois sont bien détectés (vert = chinois, orange = autre texte, bleu = zone analysée).")
    if not videos:
        st.info("Sélectionnez d'abord une vidéo.")
        return
    video = st.selectbox("Vidéo", videos, format_func=lambda p: p.name, key="prev_video")
    times = st.text_input("Instants (secondes, séparés par des espaces)", "1 3 5 8")
    if st.button("Lancer l'aperçu OCR"):
        engine = preview_ocr_engine(cfg.ocr.engine, cfg.ocr.rapid_ocr_version, cfg.ocr.rapid_model_type)
        try:
            ts = [float(x) for x in times.replace(",", " ").split()]
            cols = st.columns(min(4, len(ts)) or 1)
            with st.spinner("OCR en cours…"):
                for i, (t, img, lines) in enumerate(preview_ocr_frames(video, cfg, ts, engine)):
                    with cols[i % len(cols)]:
                        st.image(img, caption=f"t = {t:.1f} s", use_container_width=True)
                        for ln in lines:
                            st.write(("🟩 " if ln.is_chinese else "🟧 ") + f"{ln.text} ({ln.score:.2f})")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Aperçu impossible : {exc}")


@st.fragment(run_every=1.0)
def process_tab(videos: list[Path], cfg: AppConfig) -> None:
    """Commandes et progression ; rafraîchi chaque seconde sans recharger la page."""
    jm = job_manager()
    js = jm.state
    c1, c2, c3 = st.columns(3)
    force = c3.checkbox("Tout recalculer (ignorer les résultats existants)")
    if c1.button("▶️ Lancer / reprendre", type="primary", disabled=js.running or not videos):
        jm.start(videos, Path(st.session_state.out_dir), cfg, force)
        js = jm.state
    if c2.button("⏹️ Annuler", disabled=not js.running):
        jm.cancel()
    st.caption("La reprise réutilise automatiquement les étapes déjà calculées si la vidéo et les réglages n'ont pas changé.")
    if not js.videos:
        st.info("Aucun traitement lancé.")
        return
    name = Path(js.videos[min(js.current, len(js.videos) - 1)]).name
    st.progress(js.overall, text=f"Lot : {js.overall:.0%} — vidéo {min(js.current + 1, len(js.videos))}/{len(js.videos)}")
    st.progress(js.video_progress, text=f"{name} : {js.message}")
    st.caption(f"Temps écoulé : {time.time() - js.started:.0f} s" + (" — en cours…" if js.running else " — terminé"))
    if js.error:
        st.error(js.error)
    if js.result is not None and js.result.cancelled:
        st.warning("Traitement annulé. « Lancer / reprendre » reprendra là où il s'est arrêté (étapes terminées conservées).")
    if js.result is not None:
        rows = [{
            "Vidéo": Path(r.source).name, "Statut": r.status + (" (déjà traité)" if r.skipped else ""),
            "Segments": r.segments, "Traduits": r.translated, "Signalés": r.flagged,
            "Erreur / avertissements": r.error or " ; ".join(r.warnings),
        } for r in js.result.results]
        st.dataframe(rows, use_container_width=True, hide_index=True)
        for r in js.result.results:
            if r.status == "failed":
                st.error(f"{Path(r.source).name} : {r.error}")
        if not js.running:
            st.success(f"Rapport du lot : {Path(js.out_root) / 'batch_report.md'}")


def results_tab(videos: list[Path], cfg: AppConfig) -> None:
    out_root = Path(st.session_state.out_dir)
    done = [v for v in videos if output_paths(v, out_root).segments.exists()]
    if not done:
        st.info("Aucun résultat pour les vidéos sélectionnées.")
        return
    video = st.selectbox("Vidéo traitée", done, format_func=lambda p: p.name, key="res_video")
    paths = output_paths(video, out_root)
    if st.button("📂 Ouvrir le dossier des résultats"):
        os.startfile(str(paths.root))  # type: ignore[attr-defined]  # Windows
    payload = json.loads(paths.segments.read_text(encoding="utf-8"))
    segs = [Segment.from_dict(d) for d in payload["segments"]]
    left, right = st.columns([3, 2])
    with left:
        st.markdown("**Segments OCR et traductions**")
        st.dataframe([{
            "#": s.index, "Début": f"{s.start:.2f}", "Fin": f"{s.end:.2f}", "Chinois": s.text_raw.replace("\n", " / "),
            "Français": s.translation or "⚠️ indisponible", "Score OCR": round(s.score, 2),
            "Remarques": ", ".join(flag_label(f) for f in s.flags),
        } for s in segs], use_container_width=True, hide_index=True, height=420)
    with right:
        if paths.video.exists():
            st.markdown("**Vidéo bilingue exportée**")
            st.video(str(paths.video))
    if segs:
        st.markdown("**Aperçu d'un segment** (rendu calculé et image extraite du fichier exporté)")
        idx = st.selectbox("Segment", [s.index for s in segs], format_func=lambda i: f"#{i} — {segs[i - 1].text_raw[:20]}")
        seg = segs[idx - 1]
        a, b = st.columns(2)
        a.image(preview_bilingual(video, cfg, seg), caption="Aperçu avec les réglages actuels", use_container_width=True)
        if paths.video.exists():
            b.image(frame_from_output(paths.video, (seg.start + seg.end) / 2, cfg.ffmpeg_path), caption="Image du fichier exporté", use_container_width=True)


def main() -> None:
    _init_state()
    st.title("🎬 Sous-titres chinois → français (local)")
    st.caption("OCR des sous-titres chinois incrustés, traduction locale et vidéo bilingue. Tout reste sur ce PC.")
    cfg = sidebar_settings(load_config())
    videos = input_panel()
    t1, t2, t3 = st.tabs(["2. Aperçu OCR", "3. Traitement", "4. Résultats"])
    with t1:
        ocr_preview_tab(videos, cfg)
    with t2:
        process_tab(videos, cfg)
    with t3:
        results_tab(videos, cfg)


main()
