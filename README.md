# video_ocr — sous-titres chinois → français, 100 % local

Application Windows locale qui :

1. lit des vidéos (MP4, MOV, MKV…) dont les sous-titres chinois (traditionnels **ou** simplifiés) sont incrustés dans l'image ;
2. extrait ces sous-titres par OCR, avec leurs horodatages ;
3. les traduit en français avec un modèle exécuté **sur votre PC** (aucune API, aucun compte, aucun coût) ;
4. produit une **nouvelle vidéo** où le chinois d'origine reste visible et où le français s'affiche simultanément juste en dessous ;
5. exporte aussi les SRT chinois et français, un JSON détaillé, un tableau bilingue et un rapport.

Le fichier source n'est jamais modifié (vérifié par empreinte SHA-256 avant/après).

> Résultats de test mesurés : voir [TEST_REPORT.md](TEST_REPORT.md).

---

## Sommaire

1. [Choix techniques](#1-choix-techniques)
2. [Licences](#2-licences)
3. [Installation (PowerShell)](#3-installation-powershell)
4. [Utilisation](#4-utilisation)
5. [Fichiers produits](#5-fichiers-produits)
6. [Configuration](#6-configuration)
7. [Fonctionnement hors ligne](#7-fonctionnement-hors-ligne)
8. [Performances](#8-performances)
9. [Limites connues](#9-limites-connues)
10. [Erreurs fréquentes](#10-erreurs-fréquentes)
11. [Architecture du code](#11-architecture-du-code)
12. [Vidéos Instagram](#12-vidéos-instagram)

---

## 1. Choix techniques

Les composants ont été comparés sur ce PC (Intel i7-10510U, 4 cœurs, 16 Go, sans GPU).

### OCR

| Option | Chinois trad. | Temps / image (720×1280, CPU) | Remarques |
|---|---|---|---|
| **RapidOCR + PP-OCRv6 small** (retenu) | oui (simplifié + traditionnel) | ≈ 0,3-1,2 s | modèles inclus dans le paquet pip, ONNX Runtime, aucun téléchargement |
| PaddleOCR 3.7 + PP-OCRv5 mobile (option `paddleocr`) | oui | ≈ 2,6 s | PaddlePaddle 3.3.1 plante sous Windows avec oneDNN (`ConvertPirAttribute2RuntimeAttribute`) : contourné par `enable_mkldnn=False`, d'où la lenteur ; ≈ 1,5 Go de dépendances |
| PP-OCR *server* / *medium* | oui | 17-26 s | trop lent sur CPU |

RapidOCR exécute les mêmes modèles PP-OCR (famille PaddleOCR) via ONNX Runtime : c'est un « équivalent PaddleOCR » plus léger et plus rapide sous Windows. OpenCC sert à produire une version simplifiée **distincte** du texte (comparaison et traduction) ; le texte OCR brut est toujours conservé.

### Traduction (testée sur 10 phrases courtes types, simplifiées et traditionnelles)

| Option | Paire | Qualité observée | Vitesse CPU | Licence des poids |
|---|---|---|---|---|
| **Qwen3-4B Q4_K_M via llama.cpp** (défaut, `llm`) | zh → fr direct, avec contexte des sous-titres précédents | la meilleure : phrases idiomatiques correctes (« 钱不是万能的，但没有钱是万万不能的 » → « L'argent n'est pas tout, mais sans argent, rien n'est possible. ») | ≈ 5-13 s / phrase | Apache-2.0 |
| NLLB-200 distillé 600M via CTranslate2 int8 (`nllb`) | zh → fr direct | correcte sur les phrases simples, contresens fréquents sur les tournures (« 慢慢来 » → « Allez vite ») | ≈ 0,6 s / phrase | **CC-BY-NC 4.0 (non commercial)** |
| Argos Translate (`argos`) | zh → en → fr (pivot) | moyenne, répétitions, mots inventés | ≈ 1 s / phrase | MIT + modèles OPUS CC-BY 4.0 |
| M2M100 418M | zh → fr | inférieure à NLLB | ≈ 4 s / phrase | MIT — non retenu |

Le LLM est plus lent mais nettement plus fidèle ; NLLB reste disponible comme option rapide. Aucun de ces moteurs n'est parfait : les traductions douteuses sont signalées dans le rapport.

### Vidéo

- **FFmpeg 9** (conda-forge, installé *dans* l'environnement) : décodage, sélection d'images, encodage final.
- Le français est dessiné avec **Pillow** (police Windows Segoe UI, accents garantis, retour à la ligne mesuré au pixel) dans des PNG transparents, assemblés en une séquence `ffconcat` puis superposés par le filtre `overlay`. Ce choix évite libass (absent du build conda-forge) et les problèmes d'échappement de `drawtext` sous Windows.
- **Un seul réencodage vidéo** (H.264 `libx264`, CRF 20, `yuv420p`, `+faststart`, lisible PC/smartphone) ; **l'audio est copié sans réencodage** (synchronisation audio-vidéo et qualité audio inchangées).

### Interface

**Streamlit** (page web locale sur `127.0.0.1`) : aucune installation supplémentaire, fonctionne dans le navigateur, traitement en tâche de fond.

---

## 2. Licences

| Composant | Licence | Gratuit | Open source | Usage commercial | Internet |
|---|---|---|---|---|---|
| Python, NumPy, Pillow, PyYAML | PSF / BSD / HPND / MIT | oui | oui | oui | installation |
| FFmpeg (build conda-forge **GPL**, avec x264) | GPL-2.0+ | oui | oui | oui (obligations GPL si vous redistribuez) | installation |
| OpenCV (headless) | Apache-2.0 | oui | oui | oui | installation |
| RapidOCR | Apache-2.0 | oui | oui | oui | installation |
| Modèles PP-OCRv6 (PaddleOCR) | Apache-2.0 | oui | oui | oui | non (inclus) |
| ONNX Runtime | MIT | oui | oui | oui | installation |
| OpenCC (python-reimplemented) | Apache-2.0 | oui | oui | oui | installation |
| llama.cpp / llama-cpp-python | MIT | oui | oui | oui | installation |
| **Qwen3-4B** (modèle par défaut) | Apache-2.0 | oui | poids ouverts | oui | téléchargement unique (≈2,5 Go) |
| CTranslate2, Transformers, sentencepiece | MIT / Apache-2.0 | oui | oui | oui | installation (optionnel) |
| PyTorch (CPU, optionnel : conversion NLLB) | BSD-3 | oui | oui | oui | installation (optionnel) |
| **NLLB-200 600M** (optionnel) | **CC-BY-NC 4.0** | oui | poids ouverts | **non** | téléchargement unique (≈2,5 Go) |
| Argos Translate (optionnel) | MIT ; modèles OPUS CC-BY 4.0 | oui | oui | oui (attribution) | téléchargement unique |
| MiniSBD (dépendance d'Argos) | **AGPL-3.0** | oui | oui | oui (obligations AGPL si service réseau) | téléchargement unique |
| PaddleOCR / PaddlePaddle (optionnel) | Apache-2.0 | oui | oui | oui | installation + modèles |
| Streamlit | Apache-2.0 | oui | oui | oui | installation |
| Polices Segoe UI / Microsoft JhengHei | licence Windows | incluses dans Windows | non | utilisées localement pour le rendu | non |

Aucun composant ne requiert de clé API, de compte ni d'abonnement. Seuls l'installation et le premier téléchargement des modèles nécessitent Internet.

---

## 3. Installation (PowerShell)

Prérequis : Windows 10/11, [Miniconda ou Anaconda](https://docs.conda.io/), ≈ 8 Go d'espace disque (environnement ≈ 3 Go avec les moteurs optionnels + modèle LLM 2,5 Go), 8 Go de RAM minimum (16 Go conseillés pour le LLM).

### Installation automatique

Ouvrir **Anaconda PowerShell Prompt** dans le dossier du projet :

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install.ps1
```

Le script : vérifie Conda, liste les environnements, crée `video_ocr` **seulement s'il n'existe pas** (sinon l'inspecte sans le modifier ; `-Update` pour le mettre à jour sans rien supprimer), vérifie l'interpréteur, installe les dépendances avec `python -m pip`, télécharge le modèle de traduction puis lance `python -m video_ocr check`.

Par défaut, le script reproduit **à l'identique** l'environnement de développement (`environment-lock.yml` + `requirements-lock.txt`, tous les modèles). Options : `-UseWindowsCertStore` (antivirus ou proxy qui inspecte le HTTPS, voir §10), `-Minimal` (installation légère depuis `environment.yml`), `-Update`, `-SkipModels`.

> Détail complet de l'installation réalisée, des fichiers de verrouillage et de la procédure manuelle : **[INSTALL.md](INSTALL.md)**.

### Procédure manuelle (pas à pas)

```powershell
# 1. Vérifier Conda
conda --version
# 2. Inspecter les environnements existants (aucun ne sera modifié)
conda env list
# 3. Créer video_ocr s'il n'existe pas (Python 3.11 + FFmpeg dans l'environnement)
conda env create -f environment.yml
#    S'il existe déjà : l'inspecter, puis mise à jour NON destructive si besoin
conda list -n video_ocr
conda env update -n video_ocr -f environment.yml
# 4. Activer
conda activate video_ocr
# 5. Vérifier l'interpréteur et pip (doivent pointer vers ...\envs\video_ocr\)
python -c "import sys; print(sys.executable)"
python -m pip --version
# 6. (Ré)installer les dépendances si nécessaire
python -m pip install -r requirements.txt -r requirements-optional.txt
python -m pip install -e . --no-deps
python -m pip check
# 7. Télécharger les modèles (une seule fois ; --all pour NLLB + Argos)
python scripts\download_models.py
# 8. Vérifier imports, versions, FFmpeg, modèles, police
python -m video_ocr check
# 9. Lancer les tests
python -m pytest
# 10. Lancer l'application
powershell -ExecutionPolicy Bypass -File scripts\launch.ps1
```

Version **minimale** (sans PyTorch, ≈ 1 Go de moins) : n'installez que `requirements.txt` ; seuls les moteurs `llm` et `none` seront disponibles.

Les modèles sont stockés dans `%LOCALAPPDATA%\video_ocr\models` (hors OneDrive, pour éviter la synchronisation de plusieurs Go). Pour changer ce dossier : variable d'environnement `VIDEO_OCR_CACHE`.

---

## 4. Utilisation

### Interface graphique

```powershell
powershell -ExecutionPolicy Bypass -File scripts\launch.ps1
```

Le navigateur s'ouvre sur `http://localhost:8501` (accessible uniquement depuis ce PC).

1. **Vidéos** : « Choisir des vidéos… », « Choisir un dossier… », coller un chemin, ou glisser-déposer des fichiers. Choisir le dossier de sortie.
2. **Aperçu OCR** : vérifier sur quelques instants que les lignes chinoises sont détectées (cadres verts). Ajuster si besoin la zone d'analyse (ROI) dans la barre latérale.
3. **Traitement** : « Lancer / reprendre », « Annuler ». Barres de progression du lot et de la vidéo en cours, tableau des statuts, erreurs et avertissements. Une vidéo en échec n'arrête pas le lot.
4. **Résultats** : tableau chinois/français avec les signalements, lecture de la vidéo bilingue, aperçu d'un segment (rendu calculé **et** image extraite du fichier exporté), bouton « Ouvrir le dossier des résultats ».

La barre latérale règle : intervalle d'échantillonnage, affinage des bornes, ROI, textes fixes, moteur de traduction, stratégie A/B, position, taille, police, couleurs du texte, du contour et du fond, épaisseur du contour, opacité, interligne, marges, nombre de lignes, hauteur de bande.

### Ligne de commande

```powershell
conda activate video_ocr
python -m video_ocr process data\instagram -o data\sorties   # un dossier entier (chemins relatifs à la racine du projet)
python -m video_ocr process a.mp4 b.mov --strategy band       # stratégie B
python -m video_ocr process a.mp4 --engine nllb --interval 0.25
python -m video_ocr process a.mp4 --roi 0 0 1 0.5             # OCR limité à la moitié haute
python -m video_ocr preview a.mp4 --times 1 3 5                # aperçu des détections OCR (PNG annotés)
python -m video_ocr check                                     # vérification de l'environnement
```

Relancer la même commande **reprend** un lot interrompu : les étapes terminées (OCR, segments, traduction, rendu) sont réutilisées si la vidéo et les paramètres concernés n'ont pas changé. `--force` recalcule tout.

---

## 5. Fichiers produits

Pour `ma_video.mp4`, dans `<sortie>\ma_video\` :

| Fichier | Contenu |
|---|---|
| `ma_video_bilingue.mp4` | vidéo finale : chinois d'origine + français simultané |
| `ma_video.zh.srt` | sous-titres chinois (texte OCR brut, UTF-8) |
| `ma_video.fr.srt` | sous-titres français (`[traduction indisponible]` si échec, jamais vide en silence) |
| `ma_video.segments.json` | segments : texte brut, normalisé, simplifié, traduction, début/fin, incertitude temporelle, scores OCR, lectures alternatives, positions, placement du français, paramètres utilisés |
| `ma_video.bilingue.md` | tableau chinois / français côte à côte |
| `ma_video.rapport.md` | rapport : erreurs OCR, traductions manquantes ou douteuses, incertitudes de synchronisation, textes fixes écartés |
| `observations.json` | toutes les détections OCR horodatées (diagnostic, reprise) |
| `state.json` | état de reprise (étapes, empreintes) |

À la racine de la sortie : `batch_report.md`, `batch_summary.json` (récapitulatif du lot), `video_ocr.log`.

---

## 6. Configuration

Tous les paramètres sont centralisés dans [`config/default.yaml`](config/default.yaml) (valeurs par défaut documentées dans `src/video_ocr/config.py`). Principaux réglages :

- `sampling.ocr_interval_s` (0,5 s) : une image analysée par OCR toutes les N secondes.
- `sampling.dense_fps` (8) et `refine_boundaries` : quand le texte change entre deux images analysées, les images intermédiaires sont analysées par **bissection** → bornes précises à ≈ 1/(2×8) s, sans analyser toutes les images. Les phrases plus courtes que l'intervalle sont ainsi rattrapées.
- `sampling.skip_unchanged` : réutilise l'OCR précédent quand la zone de texte n'a pas changé.
- `ocr.roi` : zone d'analyse `[x0, y0, x1, y1]` en fractions de l'image (`null` = image entière, zone des sous-titres détectée automatiquement).
- `ocr.remove_static_text` : écarte les textes chinois présents pendant presque toute la vidéo (titre, filigrane).
- `segments.similarity_threshold`, `max_gap_s`, `min_duration_s` : regroupement et déduplication.
- `translation.engine` : `llm` | `nllb` | `argos` | `none`.
- `render.*` : stratégie (`inline` = A, `band` = B), position, police, couleurs, contour, fond, marges, interligne, hauteur de bande, qualité (CRF, preset).

### Stratégies de placement

- **A — `inline`** (défaut) : le français est placé **juste sous le bloc de sous-titres** (le chinois et les lignes voisines non chinoises, p. ex. la transcription thaïe des Reels testés, ne sont jamais recouverts). S'il n'y a pas la place, il passe au-dessus, sinon en bas de l'image ; le cas est signalé. Résolution et cadrage conservés.
- **B — `band`** : une bande noire est ajoutée sous l'image (16 % de la hauteur par défaut) ; l'image d'origine est intacte et son ratio conservé. Pour un Reel 720×1280, la sortie fait 720×1484.

---

## 7. Fonctionnement hors ligne

Après l'installation et `scripts\download_models.py` :

- OCR : hors ligne (modèles inclus dans le paquet `rapidocr`).
- Traduction LLM / NLLB : hors ligne (`HF_HUB_OFFLINE=1` est défini par `launch.ps1`).
- Argos : hors ligne une fois MiniSBD téléchargé (le script le fait). L'application force MiniSBD au lieu de Stanza, qui interroge Internet à chaque chargement.
- Rendu FFmpeg, interface Streamlit (sur `127.0.0.1`), exports : hors ligne, sans compte.

Testé : tests unitaires et pipeline complet exécutés avec `HF_HUB_OFFLINE=1` (voir TEST_REPORT.md).

---

## 8. Performances

Mesures détaillées dans [TEST_REPORT.md](TEST_REPORT.md). Ordres de grandeur sur i7-10510U (4 cœurs, sans GPU) :

- OCR : dépend de l'intervalle d'échantillonnage et du nombre de changements de texte (≈ 0,5-1,2 s par image analysée en 720 px de large).
- Traduction LLM : ≈ 5-13 s par sous-titre ; NLLB ≈ 0,6 s.
- Export vidéo : ≈ 1× la durée de la vidéo (preset `medium`) pour un Reel 720p.
- RAM : ≈ 1 Go (OCR) + ≈ 3,5 Go (Qwen3-4B) ; NLLB ≈ 1,5 Go.
- Disque : modèle Qwen3-4B 2,5 Go ; NLLB (Transformers + CT2) ≈ 3,3 Go ; Argos ≈ 0,4 Go.

Mesure sur 10 Reels réels (893 s au total, 720p/1080p, preset `veryfast`, `auto_roi`) : **≈ 423 s de calcul par minute de vidéo**, dont 86 % d'OCR ; pic de RAM 5,9 Go. Les vlogs sans sous-titres sont les plus coûteux (jusqu'à 1 728 s d'OCR pour 174 s de vidéo) car le texte de scène est lu en entier : la détection « sans sous-titres » intervient après l'OCR et ne réduit pas ce coût. Détail dans [TEST_REPORT.md](TEST_REPORT.md) §6.

Effets des réglages : diviser l'intervalle par deux double à peu près le temps d'OCR ; les vidéos 1080p sont réduites à 720 px de large pour l'OCR (`max_ocr_width`), ce qui limite l'effet de la résolution sur l'OCR ; l'export dépend directement de la résolution et du preset x264 (`veryfast` ≈ 2-3× plus rapide, fichiers plus gros).

---

## 9. Limites connues

- **Horodatages** : estimés au milieu de l'intervalle entre la dernière image sans le texte et la première avec (incertitude enregistrée par segment, ≈ ±0,07 s avec les réglages par défaut). Pas d'exactitude à l'image près garantie.
- **OCR** : polices très stylisées, texte en mouvement, flou, très petit texte ou contraste faible dégradent la lecture ; les confusions sont signalées (`low_confidence`, `ocr_variants`). Les écritures non chinoises (ex. thaï) ne sont pas reconnues : elles sont seulement évitées lors du placement.
- **Distinction sous-titres / autres textes** : heuristique (zone verticale dominante, textes fixes écartés). Un panneau chinois visible dans la scène, dans la zone des sous-titres, peut être pris pour un sous-titre.
- **Vidéos sans sous-titres** : une vidéo dont les « segments » sont très brefs et instables (durée médiane < 0,8 s, ≥ 60 % de segments signalés, au moins 5 segments) est déclarée « aucun sous-titre probable » : avertissement dans le rapport, rien n'est traduit ni incrusté (`segments.drop_when_no_subtitles: false` pour garder les segments). Seuils calibrés sur 10 vidéos d'un seul compte : à revérifier sur d'autres sources.
- **Position des sous-titres qui change dans une même vidéo** : avec `ocr.auto_roi`, l'OCR est limité à la bande dominante ; un sous-titre à une autre hauteur peut être manqué (constaté sur `DermDTjgqrz`). Utiliser `--roi 0 0 1 1` ou `ocr.auto_roi: false` (plus lent).
- **Mots courts** : le mode dictionnaire passe par l'anglais et peut laisser un mot anglais (« gelatin. ») ; les termes de parenté et les polices très stylisées sont mal lus ou mal traduits (voir [TEST_REPORT.md](TEST_REPORT.md) §6.4).
- **Traduction** : les modèles locaux se trompent encore sur les expressions dialectales ou culturelles (p. ex. 潮汕话 « teochew » traduit « cantonais »). Les sous-titres très courts manquent de contexte ; le LLM utilise les sous-titres précédents pour limiter ce problème.
- **Reprise** : granularité par étape ; une OCR interrompue reprend au début de la vidéo concernée.
- Le français peut recouvrir une partie de l'image (stratégie A) : utilisez la stratégie B si c'est gênant.
- Les tests ne garantissent pas la qualité sur toutes les vidéos Instagram.

---

## 10. Erreurs fréquentes

| Symptôme | Cause / solution |
|---|---|
| `CERTIFICATE_VERIFY_FAILED` (conda, pip, Hugging Face) | Un antivirus (ex. **Avast « Web Shield »**) ou un proxy inspecte le HTTPS. Relancer `scripts\install.ps1 -UseWindowsCertStore` : un bundle PEM (certifi + racines Windows) est créé dans `.certs\` et utilisé uniquement pour cette installation. Ou désactiver temporairement l'analyse HTTPS de l'antivirus. |
| `DLL load failed … Nom de fichier ou extension trop long` | Environnement Conda créé dans un dossier au chemin très long (limite Windows de 260 caractères). Utiliser l'emplacement par défaut (`…\anaconda3\envs\video_ocr`) ou activer les chemins longs de Windows. |
| `ffmpeg introuvable` | Lancer depuis l'environnement : `conda activate video_ocr` (FFmpeg est dans `envs\video_ocr\Library\bin`). |
| `NotImplementedError: ConvertPirAttribute2RuntimeAttribute` | Bug de PaddlePaddle 3.3 sous Windows ; l'option `paddleocr` désactive déjà oneDNN. Préférer `rapidocr` (défaut). |
| `Modèle LLM … absent` | `python scripts\download_models.py` (Internet requis une fois). |
| Accents remplacés par des carrés | Choisir une police TrueType complète par son **nom** (`segoeuib.ttf`, `arial.ttf`) : elle est cherchée dans `fonts/` du projet puis dans les polices du système. Pour une police non installée, la déposer dans `fonts/`. |
| Aucun sous-titre détecté | Vérifier avec « Aperçu OCR » ; restreindre la ROI ; désactiver « Ignorer les textes fixes » si la vidéo ne contient qu'une phrase. |
| Traitement très lent | Augmenter l'intervalle (1 s), utiliser `nllb` au lieu de `llm`, fermer les autres applications lourdes. |
| Fichiers de sortie dans OneDrive | Possible, mais choisissez de préférence un dossier hors OneDrive pour de gros lots. |

---

## 11. Architecture du code

```
src/video_ocr/
  config.py            configuration centralisée (dataclasses + YAML, empreintes pour la reprise)
  models.py            structures : TextBox, TextLine, FrameObservation, Segment, VideoInfo
  ingestion/           sélection des vidéos locales
  video/               FFmpeg/FFprobe, sélection d'images aux horodatages exacts
  ocr/                 moteurs OCR, lignes/blocs, analyse de zone, OCR vidéo avec bissection
  segments/            regroupement temporel, déduplication, incertitudes
  translation/         moteurs (LLM, NLLB, Argos), cache SQLite, détection des traductions douteuses
  subtitles/           SRT (écriture, lecture, validation)
  rendering/           placement A/B, dessin Pillow, rendu FFmpeg (un seul encodage)
  export/              JSON, Markdown bilingue, rapports
  pipeline/            traitement d'une vidéo (étapes + reprise), lot, rapport de lot
  ui/                  interface Streamlit, tâches de fond, aperçus
  synthetic.py         générateur de vidéos de test (sous-titres à instants connus)
  envcheck.py, cli.py
tests/                 tests unitaires et d'intégration (pytest)
config/default.yaml    paramètres
scripts/               install.ps1, launch.ps1, run_tests.ps1, download_models.py
```

Tests : `python -m pytest` (tout), `-m "not slow"` (rapide, sans pipeline complet). Aucun test ne nécessite Internet ; seuls les tests marqués `models` utilisent un modèle de traduction téléchargé.

---

## 12. Vidéos Instagram

L'application travaille **uniquement sur des fichiers locaux**. Elle n'intègre pas de téléchargement depuis Instagram : les conditions d'utilisation d'Instagram interdisent la collecte automatisée de contenus, et le site web ne propose pas de téléchargement des Reels d'autres comptes. Méthodes légitimes pour obtenir les fichiers :

- le bouton **Télécharger** de l'application mobile Instagram, quand le créateur l'autorise pour ses Reels publics ;
- demander les fichiers au créateur ;
- pour vos propres publications : *Paramètres → Votre activité → Télécharger vos informations*.

Déposez ensuite les fichiers dans un dossier et traitez-le comme n'importe quel lot.

Pour les tests du projet, 10 Reels du compte `jinnyteochew_th` ont été téléchargés une fois avec **yt-dlp**, un outil séparé qui n'est pas dans les dépendances de l'application, sans connexion ni cookie, avec l'accord explicite de l'utilisateur du projet. Derrière un antivirus qui inspecte le HTTPS (Avast), il a fallu `--compat-options no-certifi`. Les résultats sont dans [TEST_REPORT.md](TEST_REPORT.md) §6. Ces fichiers ne sont pas versionnés (`data/` est ignoré par Git).
