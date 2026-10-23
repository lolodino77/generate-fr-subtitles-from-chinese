"""Écart anticipé des vidéos sans sous-titres incrustés (sonde de ~20 images)."""
from pathlib import Path

import pytest

from conftest import FakeTranslator
from video_ocr.config import AppConfig, OcrConfig
from video_ocr.export.verify import verify_output_dir
from video_ocr.models import FrameObservation, TextLine
from video_ocr.ocr.analysis import SampleIndicators, likely_no_subtitles, sample_indicators
from video_ocr.pipeline.processor import Engines, process_video
from video_ocr.synthetic import make_video

# Indicateurs réellement mesurés le 2026-10-23 par la sonde (relevés dans data/logs/probe_all.json) sur des vidéos
# d'un même compte, avec la vraie situation constatée à l'œil.
# Colonnes : images analysées, part d'images « type sous-titre », caractères chinois par ligne,
# True = la vidéo n'a PAS de sous-titres chinois incrustés.
MEASURED = {
    # --- sans sous-titres chinois incrustés
    "Dd3UkvwCsYL": (16, 0.00, 0.0, True),    # sous-titres en thaï uniquement
    "DeitFdGkrYJ": (21, 0.00, 0.0, True),
    "Deql7rCjNsx": (20, 0.05, 21.9, True),
    "Dd0Wy1kgahR": (20, 0.05, 8.8, True),    # texte chinois d'un film projeté, filmé par la caméra
    "De0pkdiGNao": (20, 0.10, 14.2, True),
    "DegxcfClRwU": (21, 0.10, 13.1, True),
    "DeoUfUNgWJV": (20, 0.10, 9.4, True),
    "DeYtWIolGAa": (20, 0.15, 6.7, True),    # pile sur le seuil : n'est PAS écartée (limite connue)
    "Devm500DwjZ": (20, 0.20, 7.6, True),    # limite connue : non écartée, attrapée après l'OCR
    "DetCsEFCqkB": (21, 0.24, 7.0, True),    # idem
    # --- avec sous-titres chinois incrustés
    "DeAzmhqAThH": (21, 0.24, 2.2, False),
    "Del8z_ziYQH": (21, 0.29, 6.1, False),   # sous-titres en phrases : écartée à tort par l'ancienne règle
    "DermDTjgqrz": (18, 0.44, 2.1, False),   # sous-titres clairsemés
    "Des3v1LDJIa": (21, 0.52, 3.5, False),
    "DeqaVjljIVb": (21, 0.52, 1.1, False),
    "DeyYW7qDQiZ": (21, 0.71, 4.9, False),
    "Detr9vXCpnB": (21, 0.71, 1.9, False),
    "DewaCrmHFcM": (20, 0.80, 2.6, False),
    "Dd-mj6Jj48R": (17, 0.82, 5.0, False),
    "DerIojFALtk": (19, 0.84, 4.7, False),
    "De0izbCD9oy": (20, 0.85, 6.0, False),
    "DeS37izE5lk": (21, 0.90, 11.6, False),  # sous-titres en phrases longues
}
SKIPPED = {"Dd3UkvwCsYL", "DeitFdGkrYJ", "Deql7rCjNsx", "Dd0Wy1kgahR", "De0pkdiGNao", "DegxcfClRwU", "DeoUfUNgWJV"}


def _skips(video: str) -> bool:
    frames, like, cjk, _ = MEASURED[video]
    ind = SampleIndicators(frames, 1, 0.5, 0.8, like, cjk)
    return bool(likely_no_subtitles(ind, OcrConfig()))


@pytest.mark.parametrize("video", [v for v, m in MEASURED.items() if not m[3]])
def test_a_video_with_subtitles_is_never_skipped(video: str) -> None:
    """Le point essentiel : une vidéo qui a de vrais sous-titres (dont des phrases longues) n'est jamais écartée."""
    assert not _skips(video)


def test_rule_skips_exactly_the_clear_cases() -> None:
    assert {v for v in MEASURED if _skips(v)} == SKIPPED
    # Limite connue, assumée : 3 vidéos sans sous-titres ne sont pas écartées par le test rapide
    assert not any(_skips(v) for v in ("DeYtWIolGAa", "Devm500DwjZ", "DetCsEFCqkB"))


def test_small_sample_never_decides() -> None:
    ind = SampleIndicators(frames=5, zones=0, centered_frames=0.0, concentration=0.0, subtitle_like_frames=0.0, avg_cjk_per_line=0.0)
    assert likely_no_subtitles(ind, OcrConfig()) == ""


def test_threshold_sits_between_the_two_groups() -> None:
    """Le seuil doit rester dans l'écart mesuré : écartements justes ≤ 10 %, vidéos à sous-titres ≥ 24 %."""
    c = OcrConfig()
    skipped_max = max(MEASURED[v][1] for v in SKIPPED)
    subtitles_min = min(m[1] for m in MEASURED.values() if not m[3])
    assert skipped_max < c.no_subtitle_clear_ratio < subtitles_min


def _line(text: str, cx: int, cy: int, w: int = 300, h: int = 60) -> TextLine:
    return TextLine(text, 0.95, (cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2), True)


def test_sample_indicators_subtitles_vs_signage() -> None:
    c = OcrConfig()
    subtitles = [FrameObservation(i * 2.0, [_line("谢谢你们", 540, 300)] if i % 4 else []) for i in range(20)]
    signs = [FrameObservation(i * 2.0, [_line("潮汕小炒炒田螺炒牛河特色小吃", 540, 200 + 90 * (i % 7), w=800)] if i % 3 == 0 else []) for i in range(20)]
    a = sample_indicators(subtitles, 1080, 1920, c)
    b = sample_indicators(signs, 1080, 1920, c)
    assert a.subtitle_like_frames >= 0.7 and not likely_no_subtitles(a, c)
    assert b.subtitle_like_frames < a.subtitle_like_frames and b.avg_cjk_per_line > 10  # enseignes : lignes très longues


class NoTextOcr:
    """OCR factice : aucune ligne détectée (vidéo sans texte)."""

    name = "fake-empty"

    def recognize(self, image):  # type: ignore[no-untyped-def]
        return []


@pytest.fixture(scope="module")
def silent_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return make_video(tmp_path_factory.mktemp("nosub") / "sans_soustitres.mp4", cues=[], duration=24.0,
                      size=(180, 320), watermark="")


def test_pipeline_skips_video_without_subtitles(silent_video: Path, tmp_path: Path, cfg: AppConfig) -> None:
    mt = FakeTranslator()
    eng = Engines(cfg, ocr=NoTextOcr(), mt=mt)
    res = process_video(silent_video, tmp_path, cfg, eng)
    out = tmp_path / res.output_dir
    assert res.status == "partial" and not res.skipped and res.video == ""
    assert any(w.startswith("Aucun sous-titre probable") for w in res.warnings)
    assert not list(out.glob("*_bilingue.mp4")) and mt.calls == []  # ni rendu, ni traduction
    assert (out / "sans_soustitres.rapport.md").exists()
    assert "sonde" in res.timings and "ocr" not in res.timings
    # La vidéo source est intacte et `verify` accepte ce cas
    check = verify_output_dir(out)
    assert check.ok, check.checks
    # Reprise : paramètres inchangés -> déjà constaté, aucune nouvelle sonde
    again = process_video(silent_video, tmp_path, cfg, eng)
    assert again.skipped and again.status == "partial"


def test_switch_off_processes_the_whole_video(silent_video: Path, tmp_path: Path, cfg: AppConfig) -> None:
    cfg.ocr.skip_when_no_subtitles = False
    res = process_video(silent_video, tmp_path, cfg, Engines(cfg, ocr=NoTextOcr(), mt=FakeTranslator()))
    assert not any("Aucun sous-titre probable (sonde" in w for w in res.warnings)
    assert "ocr" in res.timings


def test_skipped_then_processed_leaves_a_consistent_state(silent_video: Path, tmp_path: Path, cfg: AppConfig) -> None:
    """Bug réel (Del8z_ziYQH) : après un écartement puis un retraitement, l'ancien indicateur restait à vrai
    et `verify` échouait (« vidéo non produite ») alors que la vidéo existait."""
    eng = Engines(cfg, ocr=NoTextOcr(), mt=FakeTranslator())
    first = process_video(silent_video, tmp_path, cfg, eng)
    assert first.status == "partial" and not list((tmp_path / first.output_dir).glob("*_bilingue.mp4"))
    cfg.ocr.skip_when_no_subtitles = False
    second = process_video(silent_video, tmp_path, cfg, eng)
    out = tmp_path / second.output_dir
    assert list(out.glob("*_bilingue.mp4"))
    assert verify_output_dir(out).ok, verify_output_dir(out).checks
    state = (out / "state.json").read_text(encoding="utf-8")
    assert '"no_subtitles": false' in state
    # Un état incohérent déjà écrit sur le disque (ancienne version) est corrigé à la reprise suivante
    (out / "state.json").write_text(state.replace('"no_subtitles": false', '"no_subtitles": true'), encoding="utf-8")
    third = process_video(silent_video, tmp_path, cfg, eng)
    assert third.skipped and third.status == "partial"  # statut de l'état : cette vidéo n'a vraiment aucun sous-titre
    assert '"no_subtitles": false' in (out / "state.json").read_text(encoding="utf-8")
