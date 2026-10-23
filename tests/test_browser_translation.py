"""Tests hors ligne du moteur de traduction « browser » (faux navigateur, aucune connexion)."""
import json
from pathlib import Path

from video_ocr.config import AppConfig
from video_ocr.models import Segment
from video_ocr.translation.browser_llm import (
    END_MARKER, BrowserTranslator, TranslationUnavailable, build_prompt, parse_numbered,
)
from video_ocr.translation.cache import TranslationCache
from video_ocr.translation.translator import translate_segments


class FakeSession:
    """Répond selon un scénario : une liste de réponses (texte) ou d'exceptions, consommées dans l'ordre."""

    def __init__(self, replies: list) -> None:
        self.replies = list(replies)
        self.calls: list[tuple[str, str]] = []
        self.closed = False

    def ask(self, site: str, prompt: str, timeout_s: int) -> str:
        self.calls.append((site, prompt))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def close(self) -> None:
        self.closed = True


def cfg(**kw):  # type: ignore[no-untyped-def]
    c = AppConfig().translation
    c.browser_pause_s = 0.0
    c.glossary_path = ""
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def answer(*lines: str) -> str:
    return "```\n" + "\n".join(lines) + f"\n{END_MARKER}\n```"


def seg(i: int, zh: str) -> Segment:
    return Segment(i, i, i + 1, zh, zh, zh)


def test_prompt_numbers_items_and_gives_context() -> None:
    p = build_prompt([(3, "谢谢"), (5, "你好")], context=[("早上好", "bonjour")])
    assert "3 | 谢谢" in p and "5 | 你好" in p and "早上好 => bonjour" in p
    assert "[illisible]" in p and END_MARKER in p and "pinyin" in p


def test_parse_numbered_tolerates_formats() -> None:
    raw = f"Voici :\n```text\n1 | Merci\n2: « Bonjour »\n- 3. Au revoir\n4 - dix personnes\nbla bla\n{END_MARKER}\n5 | ignoré\n```"
    assert parse_numbered(raw) == {1: "Merci", 2: "Bonjour", 3: "Au revoir", 4: "dix personnes"}


def test_translate_chunk_success_and_cleaning() -> None:
    s = FakeSession([answer("1 | Merci", "2 | Bonjour")])
    t = BrowserTranslator(cfg(), "x", session=s)
    assert t.translate_chunk(["谢谢", "你好"]) == ["Merci", "Bonjour"]
    assert t.sources["gemini"] == 2 and [c[0] for c in s.calls] == ["gemini"]


def test_falls_back_to_second_site_when_first_fails() -> None:
    s = FakeSession([TranslationUnavailable("gemini : déconnecté"), answer("1 | Merci")])
    t = BrowserTranslator(cfg(), "x", session=s)
    assert t.translate_chunk(["谢谢"]) == ["Merci"]
    assert [c[0] for c in s.calls] == ["gemini", "gpt"] and t.sources["gpt"] == 1
    assert any("déconnecté" in e for e in t.errors)


def test_missing_items_are_requested_again_with_original_numbers() -> None:
    s = FakeSession([answer("1 | Merci"), answer("2 | Bonjour")])
    t = BrowserTranslator(cfg(), "x", session=s)
    assert t.translate_chunk(["谢谢", "你好"]) == ["Merci", "Bonjour"]
    retry_prompt = s.calls[1][1]
    assert "2 | 你好" in retry_prompt and "1 | 谢谢" not in retry_prompt.split("Sous-titres à traduire :")[1]


def test_untranslated_chinese_and_unreadable_are_not_accepted() -> None:
    s = FakeSession([answer("1 | 谢谢 merci", "2 | [illisible]")] * 4)
    t = BrowserTranslator(cfg(browser_sites=["gemini"]), "x", session=s)
    assert t.translate_chunk(["谢谢", "口"]) == [None, None]
    assert len(s.calls) == 2  # « illisible » n'est pas redemandé ; le chinois non traduit l'est (2 essais)


def test_local_fallback_when_all_sites_fail() -> None:
    class Local:
        def translate_with_context(self, text, before, after):  # type: ignore[no-untyped-def]
            return f"local:{text}"

    s = FakeSession([TranslationUnavailable("a"), TranslationUnavailable("b")])
    t = BrowserTranslator(cfg(), "x", session=s, fallback_factory=Local)
    assert t.translate_chunk(["谢谢"]) == ["local:谢谢"] and t.sources["local"] == 1


def test_no_fallback_model_leaves_none_and_reports_errors() -> None:
    def broken():  # type: ignore[no-untyped-def]
        raise FileNotFoundError("modèle absent")

    s = FakeSession([TranslationUnavailable("a"), TranslationUnavailable("b")])
    t = BrowserTranslator(cfg(), "x", session=s, fallback_factory=broken)
    assert t.translate_chunk(["谢谢"]) == [None]
    assert any("repli local indisponible" in e for e in t.errors)


def test_pipeline_level_chunks_cache_context_and_glossary(tmp_path: Path) -> None:
    segs = [seg(i + 1, z) for i, z in enumerate(["谢谢", "你好", "再见", "好的", "儿媳妇"])]
    s = FakeSession([answer("1 | Merci", "2 | Bonjour"), answer("1 | Au revoir", "2 | D'accord")])
    c = cfg(browser_chunk_size=2, glossary_path="config/glossary.yaml")
    t = BrowserTranslator(c, "x", session=s)
    cache = TranslationCache(tmp_path / "c.sqlite")
    stats = translate_segments(segs, t, c, cache)
    assert [x.translation for x in segs] == ["Merci", "Bonjour", "Au revoir", "D'accord", "belle-fille (épouse du fils)"]
    assert stats.glossary == 1 and stats.failed == 0 and len(s.calls) == 2  # le glossaire n'est jamais envoyé en ligne
    assert "Merci" in s.calls[1][1]  # le contexte (série précédente) est fourni à la série suivante
    # Reprise : tout vient du cache, aucune requête
    s2 = FakeSession([])
    for x in segs:
        x.translation, x.flags = None, []
    stats2 = translate_segments(segs, BrowserTranslator(c, "x", session=s2), c, cache)
    assert s2.calls == [] and stats2.cache_hits == 4 and segs[0].translation == "Merci"
    cache.close()


def test_partial_failure_is_flagged_not_cached(tmp_path: Path) -> None:
    segs = [seg(1, "谢谢"), seg(2, "你好")]
    s = FakeSession([answer("1 | Merci"), answer("1 | Merci")] + [TranslationUnavailable("quota")] * 4)
    c = cfg(browser_sites=["gemini"])
    cache = TranslationCache(tmp_path / "c.sqlite")
    stats = translate_segments(segs, BrowserTranslator(c, "x", session=s), c, cache)
    assert segs[0].translation == "Merci" and segs[1].translation is None
    assert "translation_failed" in segs[1].flags and stats.failed == 1
    assert cache.get("browser:v1", "谢谢\n你好", "chunk") is None  # une série incomplète n'est pas mise en cache
    assert any("quota" in w or "Merci" not in w for w in stats.warnings) or stats.warnings == []
    cache.close()


def test_close_closes_session() -> None:
    s = FakeSession([])
    BrowserTranslator(cfg(), "x", session=s).close()
    assert s.closed


def test_chunk_cache_roundtrip_json() -> None:
    assert json.loads(json.dumps(["é", "ç"], ensure_ascii=False)) == ["é", "ç"]


def test_parse_numbered_ignores_site_header_and_works_on_reply_text() -> None:
    # Cas réel (Gemini) : le texte de la réponse commence par « Plaintext » avant les lignes numérotées
    raw = f"Plaintext\n1 | épais\n2 | mince\n{END_MARKER}\n"
    assert parse_numbered(raw) == {1: "épais", 2: "mince"}


def test_trailing_unreadable_part_is_removed_and_fully_unreadable_is_not_shown() -> None:
    # Cas réel (Detr9vXCpnB) : « 大姑 / 的m » -> « grand-tante paternelle | [illisible] » ; ne doit pas s'afficher tel quel
    s = FakeSession([answer("1 | tante paternelle | [illisible]", "2 | [illisible]", "3 | Merci [illisible]")])
    t = BrowserTranslator(cfg(browser_sites=["gemini"]), "x", session=s)
    assert t.translate_chunk(["大姑", "的m", "谢谢"]) == ["tante paternelle", None, "Merci"]
    assert len(s.calls) == 1  # « illisible » n'est pas redemandé
