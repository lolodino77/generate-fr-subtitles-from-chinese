"""Fixtures partagées. Les vidéos synthétiques sont générées une fois par session de tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from video_ocr.config import AppConfig
from video_ocr.synthetic import DEFAULT_CUES, SubCue, make_video


class FakeTranslator:
    """Traducteur déterministe hors ligne (préfixe « FR: ») ; peut échouer sur un texte donné."""

    name = "fake"

    def __init__(self, fail_on: str | None = None) -> None:
        self.fail_on = fail_on
        self.calls: list[str] = []

    def translate_batch(self, texts: list[str]) -> list[str]:
        self.calls.extend(texts)
        if self.fail_on and any(self.fail_on in t for t in texts):
            raise RuntimeError("panne simulée")
        return [f"FR: élève ça {len(t)}" for t in texts]


@pytest.fixture(scope="session")
def synth_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("synth")


@pytest.fixture(scope="session")
def synthetic_video(synth_dir: Path) -> Path:
    """Vidéo 12 s 720×1280, sous-titres traditionnels en haut + thaï + filigrane, bips audio."""
    return make_video(synth_dir / "vidéo é test.mp4")


@pytest.fixture(scope="session")
def short_video(synth_dir: Path) -> Path:
    """Vidéo 4 s, petite résolution, un seul sous-titre en bas (rendu rapide)."""
    return make_video(synth_dir / "short.mp4", cues=[SubCue(1.0, 3.0, "謝謝你們的幫助")], duration=4.0,
                      size=(360, 640), sub_y=0.72, watermark="")


@pytest.fixture
def cfg(tmp_path: Path) -> AppConfig:
    c = AppConfig()
    c.cache_dir = str(tmp_path / "cache")
    c.render.preset = "ultrafast"
    return c


@pytest.fixture
def cues() -> list[SubCue]:
    return DEFAULT_CUES
