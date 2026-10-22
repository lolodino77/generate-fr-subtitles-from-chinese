"""Moteurs de traduction locaux chinois -> français.

- ``nllb`` : NLLB-200 distillé 600M (Meta), traduction directe zho_Hans -> fra_Latn.
  Exécuté avec CTranslate2 (int8, rapide sur CPU) si le modèle converti est présent,
  sinon avec Transformers/PyTorch. Licence des poids : CC-BY-NC 4.0 (usage non commercial).
- ``argos`` : Argos Translate (MIT), pivot zh -> en -> fr ; plus léger, qualité inférieure.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Protocol

from video_ocr.config import TranslationConfig
from video_ocr.ocr.text_utils import count_cjk

log = logging.getLogger(__name__)


class TranslationEngine(Protocol):
    name: str  # identifiant stable utilisé comme clé de cache

    def translate_batch(self, texts: list[str]) -> list[str]: ...


def models_dir(cache_dir: str | Path) -> Path:
    return Path(cache_dir) / "models"


def hf_cache(cache_dir: str | Path) -> str:
    """Cache Hugging Face explicite (indépendant de l'ordre d'import de huggingface_hub)."""
    return str(models_dir(cache_dir) / "hf" / "hub")


def ct2_model_path(cache_dir: str | Path, model_name: str) -> Path:
    return models_dir(cache_dir) / "ct2" / (model_name.replace("/", "--") + "-int8")


def configure_model_env(cache_dir: str | Path) -> None:
    """Fixe les caches de modèles dans le répertoire du projet (pas de cache global implicite)."""
    md = models_dir(cache_dir)
    os.environ.setdefault("HF_HOME", str(md / "hf"))
    os.environ.setdefault("ARGOS_PACKAGES_DIR", str(md / "argos"))
    os.environ.setdefault("ARGOS_DEVICE_TYPE", "cpu")
    # MiniSBD (découpage en phrases ONNX, mis en cache) plutôt que Stanza, qui interroge Internet à chaque chargement.
    os.environ.setdefault("ARGOS_CHUNK_TYPE", "MINISBD")
    try:
        import minisbd.models

        minisbd.models.cache_dir = str(md / "minisbd")
    except ImportError:
        pass


class NllbEngine:
    """NLLB-200 via CTranslate2 (préféré) ou Transformers."""

    SRC, TGT = "zho_Hans", "fra_Latn"

    def __init__(self, cfg: TranslationConfig, cache_dir: str | Path, offline: bool = False) -> None:
        configure_model_env(cache_dir)
        if offline:
            os.environ["HF_HUB_OFFLINE"] = "1"
        from transformers import AutoTokenizer

        self.cfg = cfg
        ct2_path = ct2_model_path(cache_dir, cfg.nllb_model)
        self.backend = "ct2" if (ct2_path / "model.bin").exists() else "transformers"
        self.name = f"nllb:{cfg.nllb_model}:b{cfg.beam_size}"
        self.tokenizer = AutoTokenizer.from_pretrained(cfg.nllb_model, src_lang=self.SRC, cache_dir=hf_cache(cache_dir))
        if self.backend == "ct2":
            import ctranslate2

            self.model = ctranslate2.Translator(
                str(ct2_path), device="cpu", compute_type="int8", intra_threads=cfg.device_threads or 0
            )
        else:
            from transformers import AutoModelForSeq2SeqLM

            log.warning("Modèle CTranslate2 absent (%s) : utilisation de Transformers (plus lent)", ct2_path)
            self.model = AutoModelForSeq2SeqLM.from_pretrained(cfg.nllb_model, cache_dir=hf_cache(cache_dir))
        log.info("Traduction NLLB chargée (backend %s)", self.backend)

    def translate_batch(self, texts: list[str]) -> list[str]:
        if not texts:
            return []
        if self.backend == "ct2":
            tokens = [self.tokenizer.convert_ids_to_tokens(self.tokenizer.encode(t)) for t in texts]
            results = self.model.translate_batch(
                tokens, target_prefix=[[self.TGT]] * len(texts), beam_size=self.cfg.beam_size,
                max_decoding_length=256, no_repeat_ngram_size=3, repetition_penalty=1.1,
            )
            outs = []
            for r in results:
                hyp = r.hypotheses[0][1:] if r.hypotheses[0][:1] == [self.TGT] else r.hypotheses[0]
                outs.append(self.tokenizer.decode(self.tokenizer.convert_tokens_to_ids(hyp), skip_special_tokens=True))
            return outs
        import torch

        enc = self.tokenizer(texts, return_tensors="pt", padding=True)
        with torch.inference_mode():
            out = self.model.generate(
                **enc, forced_bos_token_id=self.tokenizer.convert_tokens_to_ids(self.TGT),
                num_beams=self.cfg.beam_size, max_new_tokens=256, no_repeat_ngram_size=3, repetition_penalty=1.1,
            )
        return self.tokenizer.batch_decode(out, skip_special_tokens=True)


class ArgosEngine:
    """Argos Translate, pivot automatique zh -> en -> fr."""

    def __init__(self, cfg: TranslationConfig, cache_dir: str | Path, offline: bool = False) -> None:
        configure_model_env(cache_dir)
        import argostranslate.translate as T

        langs = {lang.code: lang for lang in T.get_installed_languages()}
        if "zh" not in langs or "fr" not in langs:
            raise RuntimeError("Paquets Argos zh->en et en->fr absents : lancez scripts/download_models.py")
        self._translation = langs["zh"].get_translation(langs["fr"])
        if self._translation is None:
            raise RuntimeError("Aucun chemin de traduction Argos zh -> fr")
        self.name = "argos:zh-en-fr"

    def translate_batch(self, texts: list[str]) -> list[str]:
        return [self._translation.translate(t) for t in texts]


LLM_SYSTEM = (
    "/no_think\n"
    "Tu es un traducteur professionnel chinois-français spécialisé dans les sous-titres de vidéos courtes. "
    "Traduis uniquement la ligne demandée en français naturel, fidèle et concis, adapté à un sous-titre. "
    "Traduis toujours le sens : ne donne jamais de transcription phonétique (pinyin). "
    "Pour un mot isolé, réponds par le mot ou la courte expression française équivalente. "
    "Les sous-titres voisins ne servent qu'à comprendre le contexte : ne les traduis pas. "
    "Réponds uniquement par la traduction, sur une seule ligne, sans guillemets, sans note ni explication."
)
LLM_DICTIONARY = (
    "/no_think\n"
    "You are a Chinese dictionary. For the Chinese word or short phrase, answer on one line in the format: "
    "english meaning => sens en français. French must be the most common dictionary translation, lowercase, no article."
)
SHORT_TEXT_CJK = 3  # au plus 3 idéogrammes : traité comme un mot de vocabulaire (mode dictionnaire)
_ARTIFACT_RE = re.compile(r"\s*/?\s*\bno[_\s-]?(?:think|thinking|response)\b.*$", re.IGNORECASE)
_PINYIN_SYLLABLE = re.compile(
    r"^(?:[bpmfdtnlgkhjqxrzcsyw]|zh|ch|sh)?(?:i|u|ü|v)?(?:a|o|e|ai|ei|ao|ou|an|en|ang|eng|ong|er|i|u|ü|in|ing|un|un|ia|ie|iu|ua|uo|ui)(?:n|ng)?$"
)
_FRENCH_SHORT = {"oui", "non", "eau", "au", "ou", "un", "une", "le", "la", "les", "en", "an", "ni", "si", "il", "ai", "on"}


def clean_llm_output(text: str) -> str:
    """Nettoie une réponse du LLM : balises de réflexion, consignes recopiées, alternatives « a / b »."""
    text = text.split("</think>")[-1].replace("<think>", "").strip()
    line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    line = _ARTIFACT_RE.sub("", line).strip()
    if " / " in line:  # « Douce / hard » : on garde la première proposition
        line = line.split(" / ")[0].strip()
    return line.rstrip(" /").strip("\"'«» “”")


def looks_like_pinyin(text: str) -> bool:
    """Vrai si la sortie ressemble à une translittération (« Gao Ba Tu », « Fu ») plutôt qu'à du français."""
    words = re.findall(r"[A-Za-zÀ-ÿü]+", text)
    if not words or any(re.search(r"[À-ÿ]", w) for w in words):
        return False
    return all(_PINYIN_SYLLABLE.match(w.lower()) and w.lower() not in _FRENCH_SHORT for w in words)


class LlmEngine:
    """Petit LLM local (Qwen3, licence Apache-2.0) exécuté par llama.cpp ; exploite le contexte des segments voisins."""

    supports_context = True

    def __init__(self, cfg: TranslationConfig, cache_dir: str | Path, offline: bool = False) -> None:
        configure_model_env(cache_dir)
        if offline:
            os.environ["HF_HUB_OFFLINE"] = "1"
        from huggingface_hub import hf_hub_download
        from llama_cpp import Llama

        path = hf_hub_download(cfg.llm_repo, cfg.llm_file, cache_dir=hf_cache(cache_dir))
        threads = cfg.device_threads or max(1, (os.cpu_count() or 4) // 2)
        self._llm = Llama(model_path=path, n_ctx=2048, n_threads=threads, verbose=False, seed=0)
        self.name = f"llm:{cfg.llm_file}:v3"

    def _complete(self, user: str) -> str:
        out = self._llm.create_chat_completion(
            messages=[{"role": "system", "content": LLM_SYSTEM}, {"role": "user", "content": user}],
            temperature=0.0, max_tokens=160,
        )
        return clean_llm_output(str(out["choices"][0]["message"]["content"]))

    def _dictionary(self, text: str) -> str:
        """Mot isolé : passage par l'anglais (bien plus fiable sur ce modèle), format « english => français »."""
        out = self._llm.create_chat_completion(
            messages=[{"role": "system", "content": LLM_DICTIONARY}, {"role": "user", "content": text}],
            temperature=0.0, max_tokens=60,
        )
        raw = str(out["choices"][0]["message"]["content"]).split("</think>")[-1].strip()
        line = next((ln for ln in raw.splitlines() if "=>" in ln), "")
        return clean_llm_output(line.split("=>", 1)[1]) if line else ""

    def translate_with_context(self, text: str, before: list[str], after: list[str]) -> str:
        if count_cjk(text) <= SHORT_TEXT_CJK and len(text) <= SHORT_TEXT_CJK + 1:
            word = self._dictionary(text)
            if word and not looks_like_pinyin(word):
                return word
        parts = []
        if before:
            parts.append("Sous-titres précédents (contexte) :\n" + "\n".join(before))
        if after:
            parts.append("Sous-titre suivant (contexte) :\n" + "\n".join(after))
        parts.append(f"Ligne à traduire :\n{text}")
        prompt = "\n\n".join(parts)
        result = self._complete(prompt)
        if looks_like_pinyin(result):  # une seule relance avec une consigne explicite
            result = self._complete(
                prompt + f"\n\nAttention : « {result} » est une transcription phonétique, pas une traduction. "
                "Donne le sens en français."
            )
        return result

    def translate_batch(self, texts: list[str]) -> list[str]:
        return [self.translate_with_context(t, [], []) for t in texts]


def create_engine(cfg: TranslationConfig, cache_dir: str | Path, offline: bool = False) -> TranslationEngine | None:
    """Instancie le moteur ; ``None`` pour « none » (pas de traduction)."""
    if cfg.engine == "none":
        return None
    if cfg.engine == "llm":
        return LlmEngine(cfg, cache_dir, offline)
    if cfg.engine == "nllb":
        return NllbEngine(cfg, cache_dir, offline)
    if cfg.engine == "argos":
        return ArgosEngine(cfg, cache_dir, offline)
    raise ValueError(f"Moteur de traduction inconnu : {cfg.engine}")
