"""Outils texte : détection du chinois, normalisation et similarité."""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from functools import lru_cache

_CJK_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿\U00020000-\U0002ebef]")
_PUNCT_SPACE_RE = re.compile(r"[\s\W_]+", re.UNICODE)


def count_cjk(text: str) -> int:
    """Nombre d'idéogrammes CJK."""
    return len(_CJK_RE.findall(text))


def cjk_ratio(text: str) -> float:
    """Part d'idéogrammes parmi les caractères non blancs et non ponctuation."""
    core = [c for c in text if not c.isspace() and not unicodedata.category(c).startswith("P")]
    if not core:
        return 0.0
    return count_cjk(text) / len(core)


@lru_cache(maxsize=4)
def _opencc(config: str):  # type: ignore[no-untyped-def]
    from opencc import OpenCC

    return OpenCC(config)


def to_simplified(text: str) -> str:
    """Conversion traditionnel -> simplifié (OpenCC t2s)."""
    return _opencc("t2s").convert(text)


def to_traditional(text: str) -> str:
    """Conversion simplifié -> traditionnel (OpenCC s2t)."""
    return _opencc("s2t").convert(text)


def normalize_text(text: str) -> str:
    """Normalisation douce conservant le sens : NFKC (ponctuation pleine chasse unifiée), espaces réduits."""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def comparison_key(text: str) -> str:
    """Clé de comparaison : sans ponctuation ni espace, en simplifié (confusions trad./simp. de l'OCR neutralisées)."""
    return to_simplified(_PUNCT_SPACE_RE.sub("", normalize_text(text)))


def similarity(a: str, b: str) -> float:
    """Similarité 0-1 entre deux textes sur leur clé de comparaison."""
    ka, kb = comparison_key(a), comparison_key(b)
    if not ka and not kb:
        return 1.0
    if not ka or not kb:
        return 0.0
    if ka == kb:
        return 1.0
    return SequenceMatcher(None, ka, kb, autojunk=False).ratio()


def detect_script(text: str) -> str:
    """Retourne « traditional », « simplified », « ambiguous » ou « none » selon les caractères présents."""
    if count_cjk(text) == 0:
        return "none"
    simp = to_simplified(text)
    trad = to_traditional(text)
    if simp != text and trad == text:
        return "traditional"
    if trad != text and simp == text:
        return "simplified"
    return "ambiguous"
