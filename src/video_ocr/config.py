"""Configuration centralisée de l'application.

Toutes les valeurs par défaut sont définies ici et peuvent être surchargées par
un fichier YAML (``config/default.yaml``) puis par l'interface ou la CLI.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_FILE = PROJECT_ROOT / "config" / "default.yaml"


def default_cache_dir() -> Path:
    """Répertoire des modèles et caches, hors OneDrive pour éviter la synchronisation de Go de modèles."""
    env = os.environ.get("VIDEO_OCR_CACHE")
    if env:
        return Path(env)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".cache")
    return Path(base) / "video_ocr"


@dataclass
class SamplingConfig:
    """Échantillonnage temporel des images."""

    ocr_interval_s: float = 0.5  # une image OCR toutes les N secondes
    dense_fps: float = 8.0  # images décodées par seconde (pour l'affinage des bornes)
    refine_boundaries: bool = True  # bissection entre deux échantillons dont le texte diffère
    skip_unchanged: bool = True  # réutilise l'OCR si la zone de texte n'a pas changé
    unchanged_threshold: float = 4.0  # écart moyen de niveaux de gris (0-255) en dessous duquel l'image est jugée identique
    max_ocr_width: int = 720  # redimensionnement avant OCR (0 = jamais)


@dataclass
class OcrConfig:
    """Paramètres du moteur OCR et du filtrage des lignes."""

    engine: str = "rapidocr"  # "rapidocr" (défaut) ou "paddleocr"
    rapid_ocr_version: str = "PP-OCRv6"
    rapid_model_type: str = "small"
    min_score: float = 0.5  # boîtes en dessous ignorées
    min_cjk_ratio: float = 0.5  # part minimale de caractères chinois pour qu'une ligne soit « chinoise »
    roi: list[float] | None = None  # [x0, y0, x1, y1] en fraction de l'image, None = image entière (ou zone auto)
    auto_roi: bool = True  # sans ROI manuelle : premier passage rapide puis OCR limité à la bande des sous-titres
    # Écart anticipé des vidéos sans sous-titres incrustés (vlogs : seules des enseignes passent à l'image),
    # décidé sur l'échantillon du premier passage, avant l'OCR complète (qui coûte des dizaines de minutes).
    # Seuil placé dans l'écart mesuré sur 33 vidéos d'un seul compte : vidéos écartées à juste titre 0-10 %,
    # vidéos à sous-titres 21-100 % (la plus basse : 21 %). Des vlogs à 15-24 % passent donc l'étape (voir TEST_REPORT §6.7).
    skip_when_no_subtitles: bool = True  # False : toujours traiter la vidéo entière
    no_subtitle_min_frames: int = 8  # échantillon minimal pour décider (sinon : traitement normal)
    no_subtitle_clear_ratio: float = 0.15  # moins d'images « type sous-titre » : aucun sous-titre
    remove_static_text: bool = True  # retire les textes présents pendant presque toute la vidéo (titres, filigranes)
    static_presence_ratio: float = 0.85
    uncertain_score: float = 0.80  # en dessous : segment signalé incertain
    zone_tolerance: float = 0.18  # écart vertical max (fraction de hauteur) par rapport à une zone de sous-titres
    secondary_zone_ratio: float = 0.15  # zone secondaire retenue si son poids >= ce ratio de la zone principale
    max_zones: int = 3  # nombre maximal de zones de sous-titres par vidéo
    center_tolerance: float = 0.15  # écart max du centre du bloc au centre de l'image (fraction de largeur) ; 0 = désactivé
    line_height_range: list[float] = field(default_factory=lambda: [0.6, 1.6])  # hauteur de ligne / hauteur typique des sous-titres
    block_score_drop: float = 0.3  # ligne d'un bloc écartée si son score < meilleur score du bloc - cette valeur


@dataclass
class SegmentConfig:
    """Regroupement temporel et déduplication."""

    similarity_threshold: float = 0.72  # similarité (0-1) pour considérer deux textes identiques
    max_gap_s: float = 0.75  # trou toléré (OCR manqué) à l'intérieur d'un même segment
    min_duration_s: float = 0.4  # durée minimale d'affichage d'un segment exporté
    merge_glitch_max_obs: int = 1  # segments d'une seule observation très proches d'un voisin -> fusion
    single_char_min_s: float = 0.2  # segment d'un seul caractère plus bref : artefact de transition, écarté
    recurring_single_char: int = 3  # même caractère au même endroit dans >= N segments : objet de la scène (0 = désactivé)
    # Vidéo « sans sous-titres probables » (vlog : seules des enseignes passent à l'image) : au moins
    # ``no_subtitle_min_segments`` segments, durée médiane < ``no_subtitle_median_s`` (texte de scène qui
    # défile) et part de segments signalés >= ``no_subtitle_flagged_ratio``.
    no_subtitle_min_segments: int = 5
    no_subtitle_median_s: float = 0.8
    no_subtitle_flagged_ratio: float = 0.6
    drop_when_no_subtitles: bool = True  # False : garder les segments et seulement avertir


@dataclass
class TranslationConfig:
    """Traduction : LLM en ligne gratuit via navigateur (défaut) ou moteurs locaux."""

    engine: str = "browser"  # "browser" (Gemini/ChatGPT dans Chrome), "llm" (Qwen3 local), "nllb", "argos", "none"
    browser_sites: list[str] = field(default_factory=lambda: ["gemini", "gpt"])  # ordre d'essai
    browser_profile: str = ""  # profil Chrome (cookies de connexion) ; "" = <cache_dir>/browser_profile, hors dépôt
    browser_channel: str = "chrome"  # "chrome", "msedge" ou "" (Chromium de Playwright, à installer)
    browser_headless: bool = False  # False : fenêtre visible (connexion, captcha) ; ne pas la fermer pendant le lot
    browser_chunk_size: int = 40  # sous-titres par requête
    browser_timeout_s: int = 300  # attente maximale d'une réponse
    browser_pause_s: float = 4.0  # pause entre deux requêtes
    browser_fallback: str = "llm"  # moteur local de secours si le navigateur échoue ("none" : aucun)
    nllb_model: str = "facebook/nllb-200-distilled-600M"
    beam_size: int = 4
    normalize_to: str = "simplified"  # texte envoyé au traducteur : "simplified" ou "raw"
    device_threads: int = 0  # 0 = automatique
    llm_repo: str = "Qwen/Qwen3-4B-GGUF"  # moteur « llm » (llama.cpp) : dépôt Hugging Face du modèle GGUF
    llm_file: str = "Qwen3-4B-Q4_K_M.gguf"
    glossary_path: str = "config/glossary.yaml"  # glossaire local prioritaire (relatif à la racine du projet), "" = aucun
    llm_context_segments: int = 2  # nombre de sous-titres voisins fournis comme contexte au LLM


@dataclass
class RenderConfig:
    """Incrustation du français dans la vidéo."""

    strategy: str = "inline"  # "inline" (stratégie A) ou "band" (stratégie B)
    font_path: str = "segoeuib.ttf"  # nom de fichier (cherché dans fonts/ du projet puis les polices du système) ou chemin
    font_size_ratio: float = 0.042  # taille de police relative à la largeur de la vidéo
    text_color: str = "#FFFFFF"
    outline_color: str = "#000000"
    outline_width_ratio: float = 0.08  # épaisseur du contour relative à la taille de police
    background_color: str = "#000000"
    background_opacity: float = 0.55  # 0 = pas de fond, 1 = opaque
    margin_ratio: float = 0.04  # marge latérale relative à la largeur
    gap_ratio: float = 0.012  # espace entre le bloc chinois et le français (relatif à la hauteur)
    line_spacing: float = 1.15
    max_lines: int = 3
    position: str = "below"  # "below" (sous le chinois), "above", "bottom" (bas de l'image)
    band_height_ratio: float = 0.16  # hauteur de la bande (stratégie B), relative à la hauteur
    crf: int = 20
    preset: str = "veryfast"


@dataclass
class AppConfig:
    """Configuration complète."""

    sampling: SamplingConfig = field(default_factory=SamplingConfig)
    ocr: OcrConfig = field(default_factory=OcrConfig)
    segments: SegmentConfig = field(default_factory=SegmentConfig)
    translation: TranslationConfig = field(default_factory=TranslationConfig)
    render: RenderConfig = field(default_factory=RenderConfig)
    cache_dir: str = field(default_factory=lambda: str(default_cache_dir()))
    ffmpeg_path: str = ""  # vide = détection automatique

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def processing_hash(self) -> str:
        """Empreinte des paramètres qui influencent le résultat (pour la reprise)."""
        data = self.to_dict()
        data.pop("cache_dir", None)
        data.pop("ffmpeg_path", None)
        raw = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _merge(obj: Any, values: dict[str, Any]) -> Any:
    """Applique récursivement un dict de valeurs sur une dataclass (clés inconnues refusées)."""
    known = {f.name: f for f in fields(obj)}
    for key, value in values.items():
        if key not in known:
            raise ValueError(f"Paramètre de configuration inconnu : {key}")
        current = getattr(obj, key)
        if is_dataclass(current) and isinstance(value, dict):
            _merge(current, value)
        else:
            setattr(obj, key, value)
    return obj


def load_config(path: str | Path | None = None, overrides: dict[str, Any] | None = None) -> AppConfig:
    """Charge la configuration : défauts, puis fichier YAML, puis surcharges."""
    cfg = AppConfig()
    cfg_path = Path(path) if path else DEFAULT_CONFIG_FILE
    if cfg_path.exists():
        with cfg_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        _merge(cfg, data)
    elif path:
        raise FileNotFoundError(f"Fichier de configuration introuvable : {cfg_path}")
    if overrides:
        _merge(cfg, overrides)
    from video_ocr.translation.engines import configure_model_env

    configure_model_env(cfg.cache_dir)  # caches de modèles explicites, avant tout import de huggingface_hub
    return cfg


def config_from_dict(data: dict[str, Any]) -> AppConfig:
    """Reconstruit une configuration depuis un dict (ex. state.json)."""
    return _merge(AppConfig(), data)
