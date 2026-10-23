"""Traduction par un LLM en ligne gratuit piloté dans un vrai navigateur (Gemini, puis ChatGPT).

Principe (repris du projet auto-wordpress-translator) : Playwright ouvre Chrome avec un **profil
persistant** (connexion manuelle une seule fois, ``python -m video_ocr login``), colle un prompt dans
la zone de saisie du site, l'envoie, puis lit la réponse dans le dernier bloc de code de la page. La
réponse est considérée comme complète quand elle contient une ligne de fin (``END_MARKER``).

Une requête traduit toute une série de sous-titres numérotés : le modèle voit tout le contexte de la
vidéo, et 10 vidéos ne coûtent qu'une vingtaine de requêtes.

Limites : les sélecteurs CSS (``SITES``) dépendent de l'interface des sites et peuvent casser ; seul ce
dictionnaire est alors à adapter. Les conditions d'utilisation des services peuvent restreindre
l'automatisation : usage personnel, sur des textes non confidentiels, avec votre propre compte. Les
captchas et connexions ne sont jamais contournés : la fenêtre reste visible pour que vous les traitiez.
"""
from __future__ import annotations

import logging
import random
import re
import time
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol

from video_ocr.config import TranslationConfig
from video_ocr.ocr.text_utils import count_cjk

log = logging.getLogger(__name__)

END_MARKER = "###FIN###"

# Sélecteurs séparés par des virgules (le premier qui correspond est utilisé).
# ATTENTION : non vérifiés sur les sites en ligne tant que l'utilisateur ne s'est pas connecté ;
# à ajuster ici si l'interface change.
SITES: dict[str, dict[str, str]] = {
    "gemini": {
        "url": "https://gemini.google.com/app",
        "input": "div.ql-editor[contenteditable='true'], rich-textarea div[contenteditable='true']",
        "code": "code-block code, pre code",
        "reply": "message-content, .model-response-text",
    },
    "gpt": {
        "url": "https://chatgpt.com/",
        "input": "#prompt-textarea, textarea[data-testid='prompt-textarea']",
        "code": "pre code",
        "reply": "[data-message-author-role='assistant']",
    },
}

_REFUSE_RE = re.compile(r"tout refuser|reject all|refuser|rester déconnecté|stay logged out|non merci|no thanks", re.I)
_ERROR_RE = re.compile(
    r"something went wrong|une erreur est survenue|you've reached|vous avez atteint|try again later|réessayez plus tard|"
    r"too many requests|trop de requêtes|capacity|surcharg",
    re.I,
)
_LINE_RE = re.compile(r"^\s*[-*•]?\s*(\d+)\s*(?:\||:|\.|\)|-|–|—)\s*(.+?)\s*$")
_UNREADABLE_RE = re.compile(r"^\W*illisible\W*$", re.I)
_TRAILING_UNREADABLE_RE = re.compile(r"\s*[|/;,:–—-]*\s*\[?\s*illisibles?\s*\]?\W*$", re.I)


class TranslationUnavailable(Exception):
    """Le service ne peut pas être utilisé (déconnecté, captcha, quota, interface modifiée, navigateur)."""


class Session(Protocol):
    def ask(self, site: str, prompt: str, timeout_s: int) -> str: ...
    def close(self) -> None: ...


def default_profile_dir(cache_dir: str | Path, configured: str = "") -> Path:
    """Profil du navigateur : jamais dans le dépôt ni dans OneDrive (il contient des cookies de connexion)."""
    return Path(configured) if configured else Path(cache_dir) / "browser_profile"


class BrowserSession:
    """Chrome piloté par Playwright, profil persistant, fenêtre visible (connexion et captcha manuels)."""

    def __init__(self, profile_dir: str | Path, channel: str = "chrome", headless: bool = False) -> None:
        self.profile_dir = Path(profile_dir)
        self.channel = channel
        self.headless = headless
        self._pw: Any = None
        self._ctx: Any = None

    def open(self) -> None:
        if self._ctx is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise TranslationUnavailable(
                "Playwright n'est pas installé (python -m pip install playwright)"
            ) from exc
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        last: Exception | None = None
        for channel in dict.fromkeys([self.channel, "msedge", ""]):  # Chrome, puis Edge, puis Chromium de Playwright
            try:
                kwargs: dict[str, Any] = {"headless": self.headless, "viewport": {"width": 1280, "height": 900}}
                if channel:
                    kwargs["channel"] = channel
                self._ctx = self._pw.chromium.launch_persistent_context(str(self.profile_dir), **kwargs)
                log.info("Navigateur ouvert (%s), profil %s", channel or "chromium", self.profile_dir)
                return
            except Exception as exc:  # noqa: BLE001 - essai du navigateur suivant
                last = exc
        self.close()
        raise TranslationUnavailable(f"Aucun navigateur utilisable : {last}")

    def close(self) -> None:
        for obj, method in ((self._ctx, "close"), (self._pw, "stop")):
            try:
                if obj is not None:
                    getattr(obj, method)()
            except Exception:  # noqa: BLE001
                pass
        self._ctx = self._pw = None

    def login(self, sites: Sequence[str]) -> None:
        """Ouvre chaque site dans un onglet ; l'utilisateur se connecte à la main puis valide dans la console."""
        self.open()
        for site in sites:
            page = self._ctx.new_page()
            page.goto(SITES[site]["url"], wait_until="domcontentloaded")
        input("Connectez-vous à vos comptes dans les onglets ouverts (jamais ici), puis appuyez sur Entrée… ")

    def _dismiss_banners(self, page: Any) -> None:
        """Refuse bannières et cookies ; n'accepte jamais rien."""
        try:
            page.get_by_role("button", name=_REFUSE_RE).first.click(timeout=3000)
            page.wait_for_timeout(800)
        except Exception:  # noqa: BLE001 - pas de bannière
            pass

    @staticmethod
    def _last_text(page: Any, selector: str) -> str:
        try:
            loc = page.locator(selector)
            n = loc.count()
            return loc.nth(n - 1).inner_text() if n else ""
        except Exception:  # noqa: BLE001
            return ""

    def ask(self, site: str, prompt: str, timeout_s: int = 300) -> str:
        """Envoie ``prompt`` au site et renvoie le texte brut de la réponse complète."""
        if site not in SITES:
            raise TranslationUnavailable(f"Site inconnu : {site}")
        cfg = SITES[site]
        self.open()
        page = self._ctx.new_page()
        try:
            page.goto(cfg["url"], wait_until="domcontentloaded")
            try:
                page.wait_for_selector(cfg["input"], timeout=60000)
            except Exception as exc:  # noqa: BLE001
                raise TranslationUnavailable(
                    f"{site} : zone de saisie introuvable (déconnecté ? captcha ? interface modifiée ? "
                    "lancez « python -m video_ocr login »)"
                ) from exc
            self._dismiss_banners(page)
            for attempt in (1, 2):
                try:
                    page.locator(cfg["input"]).first.click()
                    page.keyboard.insert_text(prompt)  # d'un bloc (pas de frappe caractère par caractère)
                    page.wait_for_timeout(1500)
                    page.keyboard.press("Enter")
                    break
                except Exception as exc:  # noqa: BLE001
                    if attempt == 2:
                        raise TranslationUnavailable(f"{site} : envoi impossible ({exc})") from exc
                    page.wait_for_timeout(3000)
            return self._wait_answer(page, site, cfg, timeout_s)
        finally:
            try:
                page.close()
            except Exception:  # noqa: BLE001
                pass

    def _wait_answer(self, page: Any, site: str, cfg: dict[str, str], timeout_s: int) -> str:
        start = time.monotonic()
        while time.monotonic() - start < timeout_s:
            for key in ("code", "reply"):
                text = self._last_text(page, cfg[key])
                if END_MARKER in text and parse_numbered(text):
                    return text
            if time.monotonic() - start > 45 and not self._last_text(page, cfg["reply"]):
                try:
                    body = page.inner_text("body")
                except Exception:  # noqa: BLE001
                    body = ""
                if _ERROR_RE.search(body):
                    raise TranslationUnavailable(f"{site} : message d'erreur ou de limite affiché")
            page.wait_for_timeout(3000)
        seen = (self._last_text(page, cfg["reply"]) or self._last_text(page, cfg["code"]))[-300:].replace("\n", " ⏎ ")
        raise TranslationUnavailable(
            f"{site} : pas de réponse complète en {timeout_s} s (dernier texte vu : « {seen or 'aucun'} »)"
        )


def build_prompt(items: Sequence[tuple[int, str]], context: Sequence[tuple[str, str]] = ()) -> str:
    """Prompt de traduction d'une série de sous-titres numérotés (le numéro d'origine est conservé)."""
    lines = [
        "Tu es traducteur professionnel chinois-français pour le sous-titrage de vidéos.",
        "Voici des sous-titres d'une même vidéo, dans l'ordre. Ils viennent d'une reconnaissance de texte (OCR) "
        "et peuvent contenir des caractères erronés : traduis le sens le plus probable ; "
        "si un sous-titre est illisible, écris [illisible].",
        "Consignes : traduction française naturelle, fidèle et concise, adaptée à un sous-titre ; "
        "pour un mot isolé, donne le mot français courant (vocabulaire de cours, termes de parenté précis : "
        "oncle, tante, beau-frère…) ; jamais de transcription phonétique (pinyin) ; garde les noms propres.",
        "Format de réponse STRICT : un seul bloc de code, une ligne par sous-titre au format « numéro | traduction », "
        f"avec le même numéro que ci-dessous, sans commentaire, puis une dernière ligne contenant exactement {END_MARKER}",
    ]
    if context:
        lines.append("Contexte (sous-titres précédents déjà traduits, à ne pas retraduire) :")
        lines += [f"{zh} => {fr}" for zh, fr in context]
    lines.append("Sous-titres à traduire :")
    lines += [f"{n} | {text}" for n, text in items]
    return "\n".join(lines)


def parse_numbered(raw: str) -> dict[int, str]:
    """Extrait ``{numéro: traduction}`` d'une réponse « numéro | traduction » (première occurrence retenue)."""
    text = raw.split(END_MARKER)[0].replace("```", "")
    out: dict[int, str] = {}
    for line in text.splitlines():
        m = _LINE_RE.match(line)
        if m:
            out.setdefault(int(m.group(1)), m.group(2).strip().strip('"«»“” ').strip())
    return out


class BrowserTranslator:
    """Moteur « browser » : traduit une série de sous-titres via un LLM en ligne, avec repli."""

    supports_chunks = True
    name = "browser:v1"

    def __init__(
        self,
        cfg: TranslationConfig,
        cache_dir: str | Path,
        session: Session | None = None,
        fallback_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.cfg = cfg
        self._session = session or BrowserSession(
            default_profile_dir(cache_dir, cfg.browser_profile), cfg.browser_channel, cfg.browser_headless
        )
        self._fallback_factory = fallback_factory
        self._fallback: Any = None
        self._fallback_tried = False
        self.sources: Counter[str] = Counter()  # site ayant fourni chaque traduction (« local » = repli)
        self.errors: list[str] = []

    def close(self) -> None:
        self._session.close()

    def _local_fallback(self) -> Any:
        if not self._fallback_tried:
            self._fallback_tried = True
            try:
                self._fallback = self._fallback_factory() if self._fallback_factory else None
            except Exception as exc:  # noqa: BLE001 - modèle local absent : pas de repli
                self.errors.append(f"repli local indisponible : {exc}")
        return self._fallback

    def translate_chunk(self, texts: Sequence[str], context: Sequence[tuple[str, str]] = ()) -> list[str | None]:
        """Traduit ``texts`` ; une entrée vaut None si aucune traduction exploitable n'a pu être obtenue."""
        n = len(texts)
        result: list[str | None] = [None] * n
        unreadable: set[int] = set()

        def missing() -> list[int]:
            return [i for i in range(n) if result[i] is None and i not in unreadable]

        for site in self.cfg.browser_sites:
            if not missing():
                break
            for attempt in (1, 2):
                todo = missing()
                if not todo:
                    break
                prompt = build_prompt([(i + 1, texts[i]) for i in todo], context)
                try:
                    raw = self._session.ask(site, prompt, self.cfg.browser_timeout_s)
                except TranslationUnavailable as exc:
                    self.errors.append(str(exc))
                    log.warning("Traduction en ligne : %s", exc)
                    break  # site suivant
                for k, text in parse_numbered(raw).items():
                    i = k - 1
                    if not (0 <= i < n) or result[i] is not None or i in unreadable or i not in todo:
                        continue
                    # « grand-tante | [illisible] » : la partie illisible (ligne parasite de l'OCR) ne s'affiche pas
                    text = _TRAILING_UNREADABLE_RE.sub("", text).strip()
                    if not text or _UNREADABLE_RE.match(text):
                        unreadable.add(i)
                    elif not count_cjk(text):
                        result[i] = text
                        self.sources[site] += 1
                time.sleep(self.cfg.browser_pause_s * (0.75 + 0.5 * random.random()))
        todo = missing()
        if todo:
            fallback = self._local_fallback()
            if fallback is not None:
                for i in todo:
                    try:
                        text = fallback.translate_with_context(texts[i], [t for t in texts[max(0, i - 2):i]], [])
                    except Exception as exc:  # noqa: BLE001
                        self.errors.append(f"repli local : {exc}")
                        break
                    if text:
                        result[i] = text
                        self.sources["local"] += 1
        return result
