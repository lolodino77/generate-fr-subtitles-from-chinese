"""Tests unitaires : analyse de zone, regroupement temporel, déduplication et horodatages."""
from video_ocr.config import AppConfig, OcrConfig
from video_ocr.models import FrameObservation, Segment, TextLine
from video_ocr.ocr.analysis import analyse_observations
from video_ocr.segments.grouping import build_segments, looks_without_subtitles

H = 1280
SUB_BOX = (100, 180, 620, 240)
WM_BOX = (20, 1170, 200, 1200)


def obs(t: float, text: str | None, score: float = 0.95, watermark: bool = True, box=SUB_BOX) -> FrameObservation:
    lines = []
    if text:
        lines.append(TextLine(text, score, box, True))
    if watermark:
        lines.append(TextLine("@測試頻道", 0.99, WM_BOX, True))
    return FrameObservation(t=t, lines=lines)


def timeline(spec: list[tuple[float, float, str]], duration: float, step: float = 0.125, **kw) -> list[FrameObservation]:
    out = []
    n = int(duration / step)
    for i in range(n):
        t = round(i * step, 3)
        text = next((s for a, b, s in spec if a <= t < b), None)
        out.append(obs(t, text, **kw))
    return out


def analysed(observations: list[FrameObservation]) -> list[FrameObservation]:
    analyse_observations(observations, H, OcrConfig())
    return observations


def test_static_watermark_removed_and_zone_found() -> None:
    o = timeline([(1, 3, "這個問題很難解決"), (4, 6, "我們應該怎麼辦")], 8)
    result = analyse_observations(o, H, OcrConfig())
    assert result.static_texts == ["@測試頻道"]
    assert abs(result.zone_center - 210 / H) < 0.02
    assert all("測試" not in x.subtitle_text for x in o)


def test_single_subtitle_whole_video_is_not_static() -> None:
    o = timeline([(0, 10, "整段影片只有一句")], 10, watermark=False)
    analyse_observations(o, H, OcrConfig())
    assert all(x.subtitle_text == "整段影片只有一句" for x in o)


def test_grouping_bounds_and_order() -> None:
    spec = [(0.5, 2.5, "這個問題很難解決"), (2.5, 4.2, "我們應該怎麼辦？"), (4.8, 5.4, "對！")]
    segs = build_segments(analysed(timeline(spec, 7)), 7.0, AppConfig())
    assert [s.text_raw for s in segs] == [s for _, _, s in spec]
    for seg, (a, b, _) in zip(segs, spec):
        assert abs(seg.start - a) <= 0.0626 and abs(seg.end - b) <= 0.0626
        assert seg.timing_uncertainty_s <= 0.0626
    assert all(segs[i].end <= segs[i + 1].start for i in range(len(segs) - 1))


def test_ocr_glitch_and_gap_are_merged() -> None:
    o = timeline([(1, 4, "錢不是萬能的")], 5)
    o[12] = obs(o[12].t, "錢不是萬能")  # lecture partielle
    o[16] = obs(o[16].t, None)  # OCR manqué
    segs = build_segments(analysed(o), 5.0, AppConfig())
    assert len(segs) == 1
    assert segs[0].text_raw == "錢不是萬能的"
    assert "錢不是萬能" in segs[0].variants
    assert "ocr_variants" in segs[0].flags


def test_short_segment_kept_and_flagged() -> None:
    o = analysed(timeline([(1, 1.25, "對")], 3))
    segs = build_segments(o, 3.0, AppConfig())
    assert len(segs) == 1
    assert segs[0].duration >= AppConfig().segments.min_duration_s - 1e-6
    assert "short" in segs[0].flags


def test_low_confidence_flag_and_trad_simplified_versions() -> None:
    o = analysed(timeline([(0, 2, "謝謝你們的幫助")], 3, score=0.6))
    seg = build_segments(o, 3.0, AppConfig())[0]
    assert "low_confidence" in seg.flags
    assert seg.text_raw == "謝謝你們的幫助" and seg.text_simplified == "谢谢你们的帮助"


def test_text_until_end_of_video() -> None:
    segs = build_segments(analysed(timeline([(2, 99, "最後一句")], 4)), 4.0, AppConfig())
    assert segs[-1].end == 4.0


def test_scene_text_rejected_by_centering_and_height() -> None:
    # Cas des vlogs réels : enseignes/menus chinois filmés, décentrés ou plus petits que les sous-titres
    o = timeline([(0, 6, "要做工")], 6, watermark=False)
    for x in o:
        x.lines.append(TextLine("特色小吃", 0.99, (560, 190, 700, 230), True))  # enseigne décentrée, même hauteur de zone
        x.lines.append(TextLine("炒米粉", 0.99, (330, 250, 390, 262), True))  # menu centré mais trop petit
    analyse_observations(o, H, OcrConfig(), width=720)
    assert all(x.subtitle_text == "要做工" for x in o)


def _seg(i: int, start: float, dur: float, flags: list[str]) -> Segment:
    return Segment(index=i, start=start, end=start + dur, text_raw="大勝餅", flags=flags)


def test_scene_text_video_is_detected_as_without_subtitles() -> None:
    # enseignes qui défilent : segments au minimum de durée, presque tous signalés
    segs = [_seg(i, i * 3.0, 0.4, ["short", "single_observation"]) for i in range(8)]
    assert looks_without_subtitles(segs, AppConfig())


def test_real_subtitles_are_not_flagged_as_without_subtitles() -> None:
    segs = [_seg(i, i * 3.0, 2.5, ["ocr_variants"] if i == 0 else []) for i in range(8)]
    assert not looks_without_subtitles(segs, AppConfig())
    # vidéo de vocabulaire aux mots brefs mais stables : durée médiane 1,4 s, moitié seulement signalée
    vocab = [_seg(i, i * 3.0, 1.4, ["low_confidence"] if i % 2 else []) for i in range(10)]
    assert not looks_without_subtitles(vocab, AppConfig())


def test_too_few_segments_are_never_judged() -> None:
    assert not looks_without_subtitles([_seg(0, 0.0, 0.4, ["short"]), _seg(1, 5.0, 0.4, ["short"])], AppConfig())


def test_subtitles_at_two_heights_are_both_kept() -> None:
    # Cas réel (DermDTjgqrz) : certaines phrases en bas de l'image, d'autres en haut
    bottom = (260, 940, 460, 1000)
    o = timeline([(0, 3, "烫到")], 3, watermark=False, box=bottom)
    o += [obs(round(3 + x.t, 3), x.lines[0].text if x.lines else None, watermark=False)
          for x in timeline([(0, 9, "鱼胶")], 9, watermark=False)]
    analyse_observations(o, H, OcrConfig(), width=720)
    segs = build_segments(o, 12.0, AppConfig())
    assert [s.text_raw for s in segs] == ["烫到", "鱼胶"]


def test_single_char_scene_object_and_transition_dropped() -> None:
    # Cas réel (DeyYW7qDQiZ) : un boîtier carré lu « 口 » entre chaque sous-titre, toujours au même endroit
    spec = [(0, 2, "没钱没关系"), (2, 2.25, "口"), (2.25, 4, "没本事没关系"), (4, 4.25, "口"),
            (4.25, 6, "没钱可以再找"), (6, 6.25, "口"), (6.25, 8, "没本事可以再学"), (8, 8.1, "丑")]
    o = analysed(timeline(spec, 9, watermark=False))
    texts = [s.text_raw for s in build_segments(o, 9.0, AppConfig())]
    assert "口" not in texts and "丑" not in texts
    assert texts == ["没钱没关系", "没本事没关系", "没钱可以再找", "没本事可以再学"]
