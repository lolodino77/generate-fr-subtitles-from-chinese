"""Tests d'intégration du pipeline complet (OCR RapidOCR réel, modèles inclus dans le paquet ; traduction factice)."""
import hashlib
import json
import threading
from pathlib import Path

import pytest

from conftest import FakeTranslator
from video_ocr.config import AppConfig
from video_ocr.ocr.engines import create_engine
from video_ocr.ocr.text_utils import similarity
from video_ocr.pipeline.batch import run_batch
from video_ocr.pipeline.processor import Engines, process_video
from video_ocr.subtitles.srt import parse_srt, validate_srt
from video_ocr.synthetic import DEFAULT_CUES

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def ocr_engine():  # type: ignore[no-untyped-def]
    return create_engine(AppConfig().ocr)


def engines(cfg: AppConfig, ocr, mt=None) -> Engines:  # type: ignore[no-untyped-def]
    return Engines(cfg, ocr=ocr, mt=mt or FakeTranslator())


def test_traditional_chinese_ocr_on_frame(synthetic_video: Path, ocr_engine) -> None:  # type: ignore[no-untyped-def]
    from video_ocr.video.ffmpeg_tools import probe
    from video_ocr.video.sampler import grab_frame

    frame = grab_frame(probe(synthetic_video), 7.0)
    texts = [b.text for b in ocr_engine.recognize(frame)]
    assert "錢不是萬能的" in texts and "但沒有錢是萬萬不能的" in texts  # traditionnel préservé (錢, 萬)


def test_full_pipeline_accuracy_and_outputs(synthetic_video: Path, tmp_path: Path, cfg: AppConfig, ocr_engine) -> None:  # type: ignore[no-untyped-def]
    src_hash = hashlib.sha256(synthetic_video.read_bytes()).hexdigest()
    res = process_video(synthetic_video, tmp_path, cfg, engines(cfg, ocr_engine))
    assert res.status == "complete", res.error
    assert hashlib.sha256(synthetic_video.read_bytes()).hexdigest() == src_hash
    out = (tmp_path / res.output_dir)
    stem = synthetic_video.stem
    payload = json.loads((out / f"{stem}.segments.json").read_text(encoding="utf-8"))
    segs = payload["segments"]
    # Critères mesurés : détection, exactitude du texte, erreur temporelle
    assert len(segs) == len(DEFAULT_CUES)
    for seg, cue in zip(segs, DEFAULT_CUES):
        assert seg["text_raw"] == cue.text  # texte exact, lignes comprises
        assert abs(seg["start"] - cue.start) <= 0.15, (seg, cue)
        assert abs(seg["end"] - cue.end) <= 0.15, (seg, cue)
    # Le filigrane fixe ne doit jamais devenir un sous-titre : soit il est hors de la zone d'OCR
    # automatique (cas actuel, bande des sous-titres en haut), soit il est écarté comme texte fixe.
    assert all("測試頻道" not in s["text_raw"] for s in segs)
    assert payload["analysis"]["static_texts"] in ([], ["@測試頻道"])
    for suffix in (".zh.srt", ".fr.srt"):
        content = (out / f"{stem}{suffix}").read_text(encoding="utf-8")
        assert validate_srt(content) == []
    assert parse_srt((out / f"{stem}.zh.srt").read_text(encoding="utf-8"))[3].text == "錢不是萬能的\n但沒有錢是萬萬不能的"
    assert (out / f"{stem}_bilingue.mp4").stat().st_size > 10_000
    assert "Segments" in (out / f"{stem}.rapport.md").read_text(encoding="utf-8")
    # Le français est placé sous le bloc (chinois + thaï) sans le chevaucher
    for p in payload["analysis"]["render"]["placements"].values():
        assert p["mode"] == "below"
    for seg in segs:
        p = payload["analysis"]["render"]["placements"][str(seg["index"])]
        assert p["box"][1] >= seg["block_bbox"][3]
        # … et reste juste sous le chinois (bloc chinois + ligne thaïe ≈ 2 lignes), pas ailleurs dans l'image
        assert p["box"][1] - seg["bbox"][3] < 0.12 * 1280, (seg["text_raw"], p["box"], seg["bbox"])
    # Vérité terrain : la ligne thaïe dessinée sous le chinois ne doit pas être recouverte
    size, top = int(720 * 0.07), int(1280 * 0.15)
    for seg, cue in zip(segs, DEFAULT_CUES):
        if cue.thai:
            thai_top = top + len(cue.text.splitlines()) * int(size * 1.25)
            box = payload["analysis"]["render"]["placements"][str(seg["index"])]["box"]
            assert box[1] >= thai_top + int(size * 0.8), (cue.text, box, thai_top)


def test_resume_skip_and_partial_rerun(short_video: Path, tmp_path: Path, cfg: AppConfig, ocr_engine) -> None:  # type: ignore[no-untyped-def]
    mt = FakeTranslator()
    eng = engines(cfg, ocr_engine, mt)
    first = process_video(short_video, tmp_path, cfg, eng)
    assert first.status == "complete" and not first.skipped
    second = process_video(short_video, tmp_path, cfg, eng)
    assert second.skipped  # contenu et paramètres inchangés
    cfg.render.font_size_ratio = 0.05
    third = process_video(short_video, tmp_path, cfg, eng)
    assert third.status == "complete" and not third.skipped
    assert third.steps_run == ["render", "export"]  # OCR, segments et traduction réutilisés


def test_cancel_then_resume(short_video: Path, tmp_path: Path, cfg: AppConfig, ocr_engine) -> None:  # type: ignore[no-untyped-def]
    cancel = threading.Event()

    def progress(frac: float, msg: str) -> None:
        if frac > 0.2:
            cancel.set()

    res = process_video(short_video, tmp_path, cfg, engines(cfg, ocr_engine), progress, cancel)
    assert res.status == "interrupted"
    state = json.loads(((tmp_path / res.output_dir) / "state.json").read_text(encoding="utf-8"))
    assert state["status"] == "interrupted"
    resumed = process_video(short_video, tmp_path, cfg, engines(cfg, ocr_engine))
    assert resumed.status == "complete"


def test_batch_continues_after_invalid_file(short_video: Path, tmp_path: Path, cfg: AppConfig, ocr_engine) -> None:  # type: ignore[no-untyped-def]
    bad = tmp_path / "corrompue.mp4"
    bad.write_bytes(b"\x00" * 1000)
    batch = run_batch([bad, short_video], tmp_path / "out", cfg, engines=engines(cfg, ocr_engine))
    assert [r.status for r in batch.results] == ["failed", "complete"]
    report = (tmp_path / "out" / "batch_report.md").read_text(encoding="utf-8")
    assert "corrompue.mp4" in report and "failed" in report


def test_translation_failure_does_not_block(short_video: Path, tmp_path: Path, cfg: AppConfig, ocr_engine) -> None:  # type: ignore[no-untyped-def]
    res = process_video(short_video, tmp_path, cfg, engines(cfg, ocr_engine, FakeTranslator(fail_on="谢")))
    assert res.status == "complete" and res.translated == 0
    fr = ((tmp_path / res.output_dir) / "short.fr.srt").read_text(encoding="utf-8")
    assert "[traduction indisponible]" in fr
    assert any("sans traduction" in w for w in res.warnings)


def test_roi_restricts_ocr(synthetic_video: Path, tmp_path: Path, cfg: AppConfig, ocr_engine) -> None:  # type: ignore[no-untyped-def]
    cfg.ocr.roi = [0.0, 0.5, 1.0, 1.0]  # moitié basse : les sous-titres (en haut) sont exclus
    cfg.sampling.ocr_interval_s = 1.0
    res = process_video(synthetic_video, tmp_path, cfg, engines(cfg, ocr_engine))
    payload = json.loads(((tmp_path / res.output_dir) / f"{synthetic_video.stem}.segments.json").read_text(encoding="utf-8"))
    assert all(similarity(s["text_raw"], "這個問題很難解決") < 0.5 for s in payload["segments"])


def test_probe_settings_and_number_type_do_not_change_step_hashes() -> None:
    """Ajuster la sonde ou écrire 8 au lieu de 8.0 ne doit pas rendre périmés des résultats déjà produits."""
    from video_ocr.config import AppConfig
    from video_ocr.pipeline.state import step_hashes

    a, b = AppConfig(), AppConfig()
    b.ocr.no_subtitle_clear_ratio, b.ocr.skip_when_no_subtitles = 0.3, False
    b.sampling.dense_fps = 8  # int au lieu de 8.0
    assert step_hashes(a) == step_hashes(b)
    b.ocr.min_score = 0.6  # un vrai réglage d'OCR, lui, invalide
    assert step_hashes(a)["ocr"] != step_hashes(b)["ocr"]
