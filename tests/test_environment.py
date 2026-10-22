"""Tests de configuration de l'environnement Conda dédié."""
import sys
from pathlib import Path

from video_ocr.config import AppConfig
from video_ocr.envcheck import run_checks
from video_ocr.video.ffmpeg_tools import find_binary


def test_running_in_video_ocr_env() -> None:
    assert Path(sys.prefix).name == "video_ocr", f"Tests lancés hors de l'environnement video_ocr : {sys.prefix}"
    assert sys.version_info[:2] == (3, 11)


def test_ffmpeg_from_env() -> None:
    assert Path(find_binary("ffmpeg")).is_relative_to(Path(sys.prefix))
    assert Path(find_binary("ffprobe")).is_relative_to(Path(sys.prefix))


def test_env_checks_core_modules() -> None:
    results = {name: status for name, status, _ in run_checks(AppConfig())}
    for mod in ("numpy", "cv2", "rapidocr", "onnxruntime", "opencc", "streamlit"):
        assert results[f"Module {mod}"] == "OK"
