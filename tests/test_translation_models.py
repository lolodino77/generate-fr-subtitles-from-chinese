"""Tests des vrais moteurs de traduction (modèles téléchargés requis, exécution hors ligne).

Ces tests vérifient la réussite technique et quelques repères linguistiques simples ;
ils ne mesurent pas la qualité de traduction (voir TEST_REPORT.md pour l'évaluation humaine).
"""
import os

import pytest

from video_ocr.config import load_config
from video_ocr.envcheck import _cached_hf_file
from video_ocr.models import Segment
from video_ocr.translation.engines import create_engine, ct2_model_path
from video_ocr.translation.translator import translate_segments

pytestmark = pytest.mark.models
os.environ["HF_HUB_OFFLINE"] = "1"  # prouve le fonctionnement hors ligne


def _segments() -> list[Segment]:
    texts = ["謝謝你們的幫助", "我們應該怎麼辦？", "錢不是萬能的"]
    from video_ocr.ocr.text_utils import to_simplified

    return [Segment(i + 1, i * 2.0, i * 2.0 + 2, t, t, to_simplified(t)) for i, t in enumerate(texts)]


@pytest.fixture(scope="module")
def cfg():  # type: ignore[no-untyped-def]
    return load_config()


@pytest.mark.parametrize("engine", ["llm", "nllb", "argos"])
def test_engine_translates_offline(cfg, engine: str) -> None:  # type: ignore[no-untyped-def]
    cfg.translation.engine = engine
    if engine == "llm" and not _cached_hf_file(cfg.cache_dir, cfg.translation.llm_repo, cfg.translation.llm_file):
        pytest.skip("modèle LLM non téléchargé")
    if engine == "nllb" and not (ct2_model_path(cfg.cache_dir, cfg.translation.nllb_model) / "model.bin").exists():
        pytest.skip("modèle NLLB non téléchargé")
    if engine == "argos":
        pytest.importorskip("argostranslate")
    eng = create_engine(cfg.translation, cfg.cache_dir, offline=True)
    segs = _segments()
    stats = translate_segments(segs, eng, cfg.translation, cache=None)
    assert stats.failed == 0
    assert all(s.translation and s.translation_status == "ok" for s in segs)
    assert "merci" in segs[0].translation.lower()
    assert "argent" in segs[2].translation.lower()
    assert all(not any("一" <= c <= "鿿" for c in s.translation) for s in segs)
