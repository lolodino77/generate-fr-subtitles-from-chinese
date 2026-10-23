# Installation — reproduire à l'identique l'environnement de développement

Ce document décrit **exactement** ce qui a été installé sur le PC de développement, et comment obtenir le même environnement sur un autre PC Windows : même nom d'environnement Conda (`video_ocr`), mêmes versions de Python, de FFmpeg et de toutes les bibliothèques Python, mêmes modèles.

Version courte (Anaconda PowerShell Prompt, dans le dossier du projet) :

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install.ps1
```

Si une erreur `CERTIFICATE_VERIFY_FAILED` apparaît (antivirus ou proxy qui inspecte le HTTPS) :

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install.ps1 -UseWindowsCertStore
```

---

## 1. Ce qui est installé sur le PC de développement

| Élément | Valeur |
|---|---|
| Système | Windows 11 Pro, Intel i7-10510U (4 cœurs), 16 Go RAM, pas de GPU utilisé |
| Conda | Anaconda, conda 25.7.0 (`C:\Users\<vous>\anaconda3`) |
| Environnement | **`video_ocr`** (`…\anaconda3\envs\video_ocr`), créé pour ce projet ; aucun autre environnement modifié |
| Canal Conda | **conda-forge uniquement** (`--override-channels`) |
| Paquets Conda | 80, dont **Python 3.11.17**, **FFmpeg 9.0.2** (build GPL, avec libx264 ; sans libass), pip 26.2.2 |
| Bibliothèques Python (pip) | 137 : voir `requirements-lock.txt` |
| Projet | installé en mode éditable : `python -m pip install -e .` (paquet `video_ocr` 0.1.0) |
| Taille de l'environnement | ≈ 3,2 Go |
| Modèles | `%LOCALAPPDATA%\video_ocr\models` (hors OneDrive) : Qwen3-4B Q4_K_M 2,4 Go ; NLLB-600M 4,7 Go (téléchargement) + 0,6 Go (CTranslate2) ; Argos 0,25 Go ; Qwen3-1.7B 1,8 Go (benchmark seulement, inutile) |
| Cache de traduction | `%LOCALAPPDATA%\video_ocr\translation_cache.sqlite` |

Principales bibliothèques et leur rôle :

| Bibliothèque | Version | Rôle |
|---|---|---|
| rapidocr + onnxruntime | 3.10.0 / 1.31.0 | OCR (modèles PP-OCRv6 inclus) |
| opencc-python-reimplemented | 0.1.7 | traditionnel ↔ simplifié |
| numpy, opencv-python-headless, pillow, PyYAML | 2.3.5 / 5.0.0.93 / 13.0.0 / 6.0.2 | image, configuration |
| llama-cpp-python (roue CPU précompilée) + huggingface_hub | 0.3.36 / 2.2.0 | traduction LLM Qwen3 (par défaut) |
| ctranslate2, transformers, sentencepiece, tokenizers | 4.8.3 / 5.20.2 / 0.2.2 / 0.23.3 | traduction NLLB (option) |
| torch (CPU) | 2.14.1+cpu | conversion NLLB, dépendance d'Argos/Stanza |
| argostranslate, minisbd | 1.11.0 / 0.9.5 | traduction Argos (option) |
| paddleocr, paddlepaddle, paddlex | 3.7.0 / 3.3.1 / 3.7.2 | OCR alternatif (option, non utilisé par défaut) |
| streamlit | 1.66.1 | interface |
| pytest, psutil | 9.1.1 / 7.2.2 | tests, mesures |
| yt-dlp | 2026.10.21 | téléchargement des vidéos de test (outil séparé de l'application) |

Remarque : PaddleOCR a installé `opencv-contrib-python` 4.10 en plus d'`opencv-python-headless` 5.0. Les deux coexistent ; c'est la version 4.10 qui est importée (`cv2`). L'application fonctionne avec l'une ou l'autre : c'est vérifié par les tests dans les deux environnements.

## 2. Fichiers d'installation

| Fichier | Contenu | Usage |
|---|---|---|
| `environment-lock.yml` | les 80 paquets Conda aux versions exactes, puis `-r requirements-lock.txt` et `-e .` | **copie exacte** (défaut) |
| `requirements-lock.txt` | les 137 bibliothèques pip aux versions exactes, avec les index PyTorch CPU et llama-cpp CPU | copie exacte |
| `conda-lock-win-64.txt` | liste Conda explicite (URL + MD5), Windows 64 bits | copie bit à bit de la partie Conda (voir §4) |
| `environment.yml` | Python 3.11 + FFmpeg 9.0.2 + `requirements.txt` + `requirements-optional.txt` | installation **minimale** propre |
| `requirements.txt` | dépendances directes indispensables (sans PyTorch) | minimal |
| `requirements-optional.txt` | moteurs NLLB et Argos (PyTorch CPU) | optionnel |
| `scripts/install.ps1` | installation automatique, non destructive | voir §3 |
| `scripts/download_models.py` | téléchargement des modèles | `--all` pour tous |
| `scripts/export_lock.py` | régénère les trois fichiers de verrouillage depuis l'environnement installé | après toute modification de l'environnement |

## 3. Installation automatique (recommandée)

Prérequis :
- Windows 10/11 ;
- Miniconda ou Anaconda (ouvrir **Anaconda PowerShell Prompt**) ;
- ≈ 15 Go libres (environnement 3,2 Go, modèles ≈ 8 Go en mode complet) ;
- Internet pendant l'installation seulement.

```powershell
cd <dossier du projet>
powershell -ExecutionPolicy Bypass -File scripts\install.ps1
```

Ce que fait le script :
1. Il vérifie Conda et affiche les environnements existants.
2. Si `video_ocr` **n'existe pas**, il le crée depuis `environment-lock.yml` (10 à 20 minutes). S'il **existe**, il l'inspecte sans le modifier ; ajoutez `-Update` pour l'aligner sur les fichiers de verrouillage (`conda env update` sans `--prune`, puis `pip install -r`). **Il ne supprime ni ne recrée jamais un environnement.**
3. Il vérifie que `python` et `pip` sont bien ceux de `video_ocr`, (ré)installe le projet (`-e .`) et lance `pip check`.
4. Il télécharge les modèles avec `download_models.py --all` : Qwen3-4B, NLLB converti en CTranslate2 int8, Argos et MiniSBD.
5. Il lance `python -m video_ocr check` : toutes les lignes doivent être « OK ».

Options :

| Option | Effet |
|---|---|
| `-UseWindowsCertStore` | crée `.certs\ca_bundle.pem` (certifi + certificats racines Windows) et l'utilise pour conda, pip et Hugging Face **pendant le script seulement**. Indispensable sur le PC de développement à cause d'Avast « Web Shield », qui intercepte le HTTPS. |
| `-Minimal` | environnement léger (`environment.yml`) et modèle Qwen3-4B seul |
| `-Update` | met à jour un `video_ocr` existant |
| `-SkipModels` | ne télécharge pas les modèles |

## 4. Installation manuelle, pas à pas (copie exacte)

```powershell
# 1. Vérifier Conda et inspecter les environnements existants
conda --version
conda env list

# 2. Créer video_ocr (seulement s'il n'existe pas)
conda env create -f environment-lock.yml
#    Variante bit à bit pour la partie Conda, puis les bibliothèques pip :
#    conda create -n video_ocr --file conda-lock-win-64.txt
#    conda activate video_ocr ; python -m pip install -r requirements-lock.txt ; python -m pip install -e .

# 3. Activer et vérifier l'interpréteur (doit afficher ...\envs\video_ocr\python.exe)
conda activate video_ocr
python -c "import sys; print(sys.executable)"
python -m pip --version
python -m pip check

# 4. Modèles (Internet requis une fois)
python scripts\download_models.py --all

# 5. Vérifications
python -m video_ocr check
python -m pytest
```

Si l'antivirus bloque le HTTPS en installation manuelle : créez le bundle avec `install.ps1 -UseWindowsCertStore -SkipModels`, ou à la main, puis définissez pour la session :

```powershell
$env:CONDA_SSL_VERIFY = "$PWD\.certs\ca_bundle.pem"
$env:PIP_CERT = $env:CONDA_SSL_VERIFY
$env:REQUESTS_CA_BUNDLE = $env:CONDA_SSL_VERIFY
$env:SSL_CERT_FILE = $env:CONDA_SSL_VERIFY
```

**yt-dlp** derrière Avast : il utilise ses propres certificats (certifi). Sur le PC de développement, il a fallu ajouter `--compat-options no-certifi`, qui lui fait utiliser le magasin de certificats Windows (avec l'accord de l'utilisateur). Exemple :

```powershell
python -m yt_dlp --compat-options no-certifi --ffmpeg-location "$env:CONDA_PREFIX\Library\bin" -f "bv*+ba/b" --merge-output-format mp4 -o "data/instagram/%(id)s.%(ext)s" <URL>
```

## 4 bis. Traduction en ligne (moteur par défaut) : connexion unique

Le moteur de traduction par défaut pilote **Chrome** (ou Edge) avec Playwright, installé par `requirements-lock.txt` : aucun navigateur supplémentaire à télécharger, et **aucun modèle de traduction local obligatoire** (économie d'environ 8 Go ; le modèle Qwen3-4B n'est qu'un secours facultatif).

```powershell
conda activate video_ocr
python -m video_ocr login        # une seule fois : ouvre Gemini et ChatGPT ; connectez-vous vous-même dans Chrome
python -m video_ocr check        # « Profil du navigateur » doit être OK
```

- Le profil de connexion est créé dans `%LOCALAPPDATA%\video_ocr\browser_profile` (hors dépôt, hors OneDrive, jamais versionné : il contient des cookies). Il faut donc refaire `login` sur chaque PC.
- **Gemini fonctionne sans compte** (mode invité) ; ChatGPT exige un compte. Un seul des deux suffit.
- Si Chrome n'est pas installé : Edge est essayé, puis le Chromium de Playwright (`python -m playwright install chromium`, ≈ 150 Mo).
- Pour ne **pas** utiliser le réseau : `translation.engine: llm` dans `config/default.yaml`, après `python scripts\download_models.py`.

## 5. Vérifier que l'installation est identique

```powershell
conda activate video_ocr
python --version                      # Python 3.11.17
ffmpeg -version                       # ffmpeg version 9.0.2
python -m pip freeze --all > $env:TEMP\freeze.txt
python -m video_ocr check             # toutes les lignes OK
python -m pytest                      # 41 tests réussis attendus (voir TEST_REPORT.md)
```

Pour comparer finement, régénérez les verrous sur le nouveau PC (`python scripts\export_lock.py`) et comparez les fichiers avec ceux du dépôt. Aucune différence attendue, hormis les chemins.

## 6. Points d'attention connus

- **Chemins longs** : n'installez pas l'environnement dans un dossier au chemin très long (> 260 caractères). Sinon, `rapidocr` échoue (`DLL load failed … Nom de fichier ou extension trop long`). L'emplacement par défaut `…\anaconda3\envs\video_ocr` convient.
- **Modèles hors OneDrive** : ils ne suivent pas le dossier du projet ; il faut les retélécharger sur chaque PC (`download_models.py`). Pour un autre emplacement : variable `VIDEO_OCR_CACHE`.
- **PaddlePaddle 3.3.1** plante sous Windows si oneDNN est actif. L'application le désactive pour le moteur `paddleocr` ; le moteur par défaut est `rapidocr`.
- Le script ne modifie aucune configuration globale : ni `.condarc`, ni `pip.conf`, ni variables d'environnement permanentes.

## 7. Mettre à jour les verrous après un changement

Après avoir installé ou retiré un paquet dans `video_ocr` :

```powershell
conda activate video_ocr
python scripts\export_lock.py
```

Puis ajoutez les paquets directement nécessaires dans `requirements.txt` ou `requirements-optional.txt` pour garder l'installation minimale cohérente.
