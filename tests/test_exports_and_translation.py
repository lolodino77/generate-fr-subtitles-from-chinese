"""Tests unitaires : SRT, JSON/Markdown, traduction (moteur factice), cache, configuration, reprise."""
import json
from pathlib import Path

import pytest

from conftest import FakeTranslator
from video_ocr.config import AppConfig, load_config
from video_ocr.export.writers import write_bilingual_md, write_json, write_report_md
from video_ocr.ingestion.discover import discover_videos
from video_ocr.models import Segment
from video_ocr.pipeline.state import VideoState, step_hashes
from video_ocr.subtitles.srt import format_timestamp, parse_srt, segments_to_srt, validate_srt
from video_ocr.translation.cache import TranslationCache
from video_ocr.translation.translator import suspicious, translate_segments


def segs() -> list[Segment]:
    return [
        Segment(1, 0.4, 2.4, "這個問題\n很難解決", "這個問題很難解決", "这个问题很难解决", "C'est un problème très difficile à résoudre."),
        Segment(2, 2.4, 4.0, "謝謝", "謝謝", "谢谢", None, "failed", flags=["translation_failed"]),
    ]


def test_timestamp_format() -> None:
    assert format_timestamp(3725.0456) == "01:02:05,046"
    assert format_timestamp(-1) == "00:00:00,000"


def test_srt_roundtrip_utf8(tmp_path: Path) -> None:
    zh = segments_to_srt(segs(), "chinese")
    fr = segments_to_srt(segs(), "french")
    p = tmp_path / "x.fr.srt"
    p.write_text(fr, encoding="utf-8")
    parsed = parse_srt(p.read_text(encoding="utf-8"))
    assert parsed[0].text == "C'est un problème très difficile à résoudre."
    assert parsed[1].text == "[traduction indisponible]"  # jamais de chaîne vide silencieuse
    assert parse_srt(zh)[0].text == "這個問題\n很難解決"
    assert validate_srt(zh) == [] and validate_srt(fr) == []


def test_srt_validation_detects_overlap() -> None:
    bad = "1\n00:00:01,000 --> 00:00:03,000\na\n\n2\n00:00:02,000 --> 00:00:04,000\nb\n"
    assert any("Chevauchement" in p for p in validate_srt(bad))


def test_json_and_markdown(tmp_path: Path) -> None:
    data = {"segments": [s.to_dict() for s in segs()]}
    write_json(tmp_path / "s.json", data)
    loaded = json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))
    assert loaded["segments"][0]["text_raw"] == "這個問題\n很難解決"
    assert Segment.from_dict(loaded["segments"][0]).translation.startswith("C'est")
    md = write_bilingual_md(tmp_path / "b.md", "vidéo", segs()).read_text(encoding="utf-8")
    assert "這個問題<br>很難解決" in md and "[traduction indisponible]" in md
    rep = write_report_md(tmp_path / "r.md", "vidéo", {"Segments": 2}, segs(), ["attention"]).read_text(encoding="utf-8")
    assert "traduction manquante" in rep and "attention" in rep


def test_translation_dedup_cache_and_failure_isolation(tmp_path: Path) -> None:
    s = segs()
    s.append(Segment(3, 4.0, 5.0, "謝謝", "謝謝", "谢谢"))  # doublon
    s.append(Segment(4, 5.0, 6.0, "壞", "壞", "坏"))
    for x in s:
        x.translation, x.flags, x.translation_status = None, [], "pending"
    cache = TranslationCache(tmp_path / "c.sqlite")
    eng = FakeTranslator(fail_on="坏")
    stats = translate_segments(s, eng, AppConfig().translation, cache)
    assert stats.unique_texts == 3 and stats.failed == 1
    assert eng.calls.count("谢谢") <= 2  # traduit une fois (+ éventuel nouvel essai individuel)
    assert s[1].translation == s[2].translation and s[1].translation_status == "ok"
    assert s[3].translation is None and "translation_failed" in s[3].flags
    eng2 = FakeTranslator()
    stats2 = translate_segments(s[:3], eng2, AppConfig().translation, cache)
    assert stats2.cache_hits == 2 and eng2.calls == []
    cache.close()


def test_suspicious_translations() -> None:
    assert suspicious("谢谢", "") == "empty"
    assert suspicious("谢谢", "谢谢 merci") == "untranslated_chinese"
    assert suspicious("慢慢来", "Prenez votre temps. Prenez votre temps.") == "repetition"
    assert suspicious("谢谢你", "Merci à toi.") is None


def test_config_yaml_and_unknown_key(tmp_path: Path) -> None:
    p = tmp_path / "c.yaml"
    p.write_text("sampling:\n  ocr_interval_s: 1.0\nrender:\n  strategy: band\n", encoding="utf-8")
    cfg = load_config(p)
    assert cfg.sampling.ocr_interval_s == 1.0 and cfg.render.strategy == "band"
    p.write_text("sampling:\n  inconnu: 1\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(p)


def test_step_hashes_invalidate_only_downstream() -> None:
    a, b = AppConfig(), AppConfig()
    b.render.font_size_ratio = 0.05
    ha, hb = step_hashes(a), step_hashes(b)
    assert ha["ocr"] == hb["ocr"] and ha["translation"] == hb["translation"]
    assert ha["render"] != hb["render"]
    state = VideoState(source="x", steps=dict(ha))
    assert state.first_invalid_step(ha) is None
    assert state.first_invalid_step(hb) == "render"


def test_discover_videos(tmp_path: Path) -> None:
    (tmp_path / "a.mp4").write_bytes(b"x")
    (tmp_path / "b.MOV").write_bytes(b"x")
    (tmp_path / "a_bilingue.mp4").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("x")
    vids, problems = discover_videos([tmp_path, tmp_path / "a.mp4", tmp_path / "notes.txt", tmp_path / "absent.mkv"])
    assert [v.name for v in vids] == ["a.mp4", "b.MOV"]
    assert len(problems) == 2


def test_llm_output_cleaning_and_pinyin_detection() -> None:
    from video_ocr.translation.engines import clean_llm_output, looks_like_pinyin

    # Artefacts observés sur les vraies vidéos (consigne recopiée, alternatives)
    assert clean_llm_output("Court produit /no_response") == "Court produit"
    assert clean_llm_output("You / no thinking") == "You"
    assert clean_llm_output("Douce / hard") == "Douce"
    assert clean_llm_output("<think>\n</think>\n« Oui ! »") == "Oui !"
    assert looks_like_pinyin("Gao Ba Tu") and looks_like_pinyin("Fu")
    assert not looks_like_pinyin("Oui !") and not looks_like_pinyin("Épais") and not looks_like_pinyin("Lourd")


def test_portable_paths_and_font_lookup(tmp_path: Path) -> None:
    from video_ocr.fonts import find_font
    from video_ocr.pipeline.state import from_portable, to_portable

    out = tmp_path / "sorties" / "clip"
    video = tmp_path / "videos" / "clip é.mp4"
    rel = to_portable(video, out)
    assert not Path(rel).is_absolute() and "\\" not in rel  # relatif, séparateurs « / »
    assert from_portable(rel, out) == video.resolve()
    # Police désignée par son nom, sans chemin propre à la machine
    assert find_font("segoeuib.ttf") is not None and find_font("segoeuib.ttf").exists()
    assert find_font("police_inexistante.ttf") is None
