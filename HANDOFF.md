# HANDOFF — état du projet pour reprise sur un autre ordinateur

Rédigé le 2026-10-22 vers 18 h, au moment d'une pause demandée par l'utilisateur.
Ce document se suffit à lui-même : il ne suppose aucun accès à la conversation d'origine.

---

## 1. Objectif (rappel)

La spécification complète est dans `Spec Projet - application locale d'OCR vidéo, … bilingues.md`, à la racine.

En résumé : une application Python locale et gratuite (Windows, CPU, environnement Conda `video_ocr`) qui :
- fait l'OCR des sous-titres chinois incrustés dans des vidéos ;
- les regroupe dans le temps ;
- les traduit en français avec des modèles locaux ;
- produit une **vidéo où le chinois d'origine et le français sont visibles en même temps**, ainsi que des SRT, un JSON et des rapports.

Consigne de l'utilisateur : tester sur **10 vidéos du compte Instagram `jinnyteochew_th`**, corriger, consigner dans `TEST_REPORT.md`, et ne **jamais** prétendre qu'un test a été exécuté s'il ne l'a pas été.

Contrainte Conda : ne supprimer ni recréer aucun environnement existant sans autorisation.

## 2. Où en est-on (résumé)

| Élément | État |
|---|---|
| Application complète (pipeline, CLI, interface Streamlit, scripts, README) | ✅ faite |
| Tests automatisés (synthétiques) | ✅ 41/41 au dernier passage complet. ⚠️ Le code a changé depuis (§6) : relancer `pytest`. |
| Reproductibilité de l'environnement (`environment.yml`) | ✅ vérifiée (40/41, l'échec restant est attendu) |
| Téléchargement des 10 Reels | ✅ dans `data/instagram/` (237 Mo, yt-dlp, autorisé par l'utilisateur) |
| Traitement des 10 vraies vidéos | ⏳ **EN COURS DE MISE AU POINT** : 1 vidéo terminée (avec l'avant-dernière version du code), lot arrêté volontairement (§5) |
| `TEST_REPORT.md` | ⚠️ **à mettre à jour** : sa section 6 indique encore « Instagram non exécuté » et ne contient pas les résultats réels |

Aucun processus ne tourne : le lot a été arrêté proprement.

## 3. Mise en place sur un nouvel ordinateur

> **Procédure complète et détaillée : [INSTALL.md](INSTALL.md).** En une commande (copie exacte de l'environnement de développement : `environment-lock.yml` + `requirements-lock.txt` + tous les modèles) :
> `powershell -ExecutionPolicy Bypass -File scripts\install.ps1 -UseWindowsCertStore`

1. Récupérer le projet. Le dossier s'appelle désormais `Documents/perso/projets/generate-fr-subtitles-from-chinese` (dans OneDrive ; anciennement `projet_sous_titres_ch_khmer_fr`). C'est un dépôt Git relié à `git@github.com:lolodino77/generate-fr-subtitles-from-chinese.git`.
   - **Le code passe par Git** (si commité et poussé) ou par OneDrive.
   - **Les données ne passent PAS par Git** (`data/` est dans le `.gitignore`) : les vidéos `data/instagram/` et les résultats arrivent uniquement par OneDrive, ou par copie manuelle, ou en les retéléchargeant (§3.5).
   - Après un déplacement du dossier, réinstaller le projet dans l'environnement : `python -m pip install -e . --no-deps`. Sinon, `import video_ocr` pointe vers l'ancien emplacement et échoue.
2. Créer l'environnement : `conda env create -f environment-lock.yml` (copie exacte ; `environment.yml` = version minimale), puis `conda activate video_ocr`. Vérifier avant que `video_ocr` n'existe pas déjà (`conda env list`) ; s'il existe, l'inspecter sans le supprimer.
   - Si `CERTIFICATE_VERIFY_FAILED` (antivirus qui inspecte le HTTPS, ex. **Avast**, rencontré sur le premier PC) : `powershell -ExecutionPolicy Bypass -File scripts\install.ps1 -UseWindowsCertStore`. Le script construit `.certs\ca_bundle.pem` (certifi + racines Windows) et le passe par variables d'environnement pour cette session seulement.
   - Ne pas créer l'environnement dans un dossier au chemin très long (> 260 caractères) : `rapidocr`/`shapely` échoue alors avec « Nom de fichier ou extension trop long ».
3. Modèles, une seule fois : `python scripts\download_models.py` télécharge le modèle par défaut **Qwen3-4B Q4_K_M** (environ 2,4 Go). `--all` ajoute NLLB et Argos.
   - Ils sont stockés dans `%LOCALAPPDATA%\video_ocr\models` (ou dans `VIDEO_OCR_CACHE`), **hors OneDrive**, donc **pas** présents sur le nouvel ordinateur.
   - Les modèles OCR (PP-OCRv6) sont inclus dans le paquet `rapidocr`.
4. Vérifier : `python -m video_ocr check` (tout doit être OK), puis `python -m pytest`.
5. yt-dlp n'est **pas** dans les requirements (outil de test ponctuel) : `python -m pip install yt-dlp` si besoin. Les vidéos sont déjà dans `data/instagram/` si OneDrive a synchronisé le dossier `data/`.
   - Sur le premier PC, yt-dlp exigeait `--compat-options no-certifi` (magasin de certificats Windows, à cause d'Avast). **L'utilisateur l'a explicitement autorisé.** Aucune connexion Instagram ni cookie n'a été utilisé.

### Liste de contrôle avant de changer de PC

- [ ] **Code commité et poussé** sur GitHub, si l'autre PC part d'un `git clone`.
- [ ] **OneDrive entièrement synchronisé** sur le PC d'origine avant d'ouvrir le projet ailleurs. Ne pas travailler sur les deux PC en même temps : risque de fichiers en conflit.
- [ ] Sur l'autre PC : clic droit sur le dossier → **« Toujours conserver sur cet appareil »**. Avec « Fichiers à la demande », les vidéos de `data/instagram/` peuvent n'être que des liens vers le cloud.
- [ ] **Modèles** (hors OneDrive) : les retélécharger (`install.ps1`, environ 8 Go) ou copier `%LOCALAPPDATA%\video_ocr\models` au même emplacement, ce qui est plus rapide. Copier aussi `%LOCALAPPDATA%\video_ocr\translation_cache.sqlite` pour éviter de retraduire.
- [ ] **Anaconda ou Miniconda** installé sur l'autre PC.
- [x] **Aucun chemin propre à une machine** dans le projet : polices désignées par leur nom (`video_ocr.fonts`), `.claude/launch.json` passe par `scripts/launch.ps1` (environnement retrouvé via Conda), et les résultats (`state.json`, `segments.json`, `batch_summary.json`) sont enregistrés en chemins relatifs au dossier de sortie.
- [ ] **Autorisations Claude Code** : propres à chaque machine. `yt-dlp --compat-options no-certifi` avait été refusé par le mode automatique jusqu'à l'accord explicite de l'utilisateur ; le redonner seulement s'il faut retélécharger les vidéos.
- [ ] **Antivirus avec inspection HTTPS** sur l'autre PC : utiliser `install.ps1 -UseWindowsCertStore`.

## 4. Choix techniques retenus (et pourquoi)

- **OCR** : RapidOCR 3.10 + PP-OCRv6 *small* (ONNX Runtime). PaddleOCR 3.3 plante sous Windows (bogue oneDNN) et n'est utilisable qu'avec `enable_mkldnn=False` (lent) : il reste en option `paddleocr`. Les modèles *server* sont trop lents (≈17 s par image).
- **Traduction** : par défaut **Qwen3-4B (llama.cpp, Apache-2.0)**, qui donne la meilleure qualité sur les benchmarks.
  - Options : NLLB-600M (CTranslate2, rapide, licence **non commerciale**) et Argos (pivot par l'anglais).
  - Qwen3-1.7B et M2M100 ont été testés puis écartés.
  - Mots isolés (≤ 3 idéogrammes) : **mode dictionnaire** passant par l'anglais (`english => français`), bien plus fiable avec ce modèle.
- **Rendu** : le français est dessiné avec Pillow dans des PNG transparents, assemblés en séquence `ffconcat` et superposés par le filtre FFmpeg `overlay`. Le build conda-forge de FFmpeg n'a pas libass. Un seul encodage x264 ; **audio copié sans réencodage**, donc synchronisation conservée.
  - Stratégie A `inline` : sous le bloc chinois, sans recouvrir les lignes thaïes voisines.
  - Stratégie B `band` : bande ajoutée sous l'image.
- **Horodatages** : sélection d'images source réelles (`select` + `showinfo`, horodatages exacts), échantillon OCR toutes les 0,5 s, **bissection** sur les images intermédiaires quand le texte change. Erreur mesurée ≤ 0,067 s sur vidéo synthétique.
- Les étapes (`ocr`, `segments`, `translation`, `render`, `export`) ont une empreinte de configuration ; la **reprise** saute les étapes à jour. L'option `--redo-from segments` réutilise l'OCR déjà faite.

## 5. Ce que les vraies vidéos ont révélé (et ce qui a été corrigé)

Les 10 Reels font 893 s au total, en VP9 + AAC, en 1080×1920 ou 720×1280 ; l'un est à fréquence d'images variable (~49 i/s). Sur ce compte, le chinois est **simplifié** (pas traditionnel), avec en général **2 lignes thaïes** dessous ; la langue parlée est le teochew/thaï.

Problèmes trouvés en inspectant les images exportées, **tous corrigés dans le code** :
1. Les lignes chinoise et thaïe empilées étaient fusionnées en une seule, à cause des diacritiques thaïs qui font chevaucher les boîtes. → `lines._same_row` : centres proches **et** boîtes côte à côte. Test ajouté.
2. Une vidéo de vocabulaire (`DeqaVjljIVb`) contient un caractère isolé empilé au-dessus de mots thaïs, lu comme une colonne verticale (`短的品`). → `RapidOcrEngine._split_stacked` : seconde détection sur la zone découpée quand la boîte est haute (h ≥ 1,2 × l).
3. Le thaï est parfois lu comme du chinois avec un score faible. → `ocr.block_score_drop` (0,3) écarte du bloc les lignes nettement moins sûres que la meilleure.
4. Le texte de scène (enseignes, menus) était pris pour des sous-titres. → Filtres par ligne avant le regroupement : centrage horizontal (`center_tolerance` 0,15) et hauteur cohérente (`line_height_range` [0,6 ; 1,6] × hauteur typique, médiane pondérée par le nombre de caractères). Test ajouté.
5. Le français recouvrait la 3ᵉ ligne thaïe, détectée sur une partie des images seulement. → Cadre de bloc par percentiles (`lines.envelope_bbox`), plus une **extension typique apprise par vidéo** (`analysis._apply_typical_extension`).
6. Traduction LLM : artefacts « /no_response », « Douce / hard », pinyin (« Fu », « Gao Ba Tu »). → `/no_think` placé dans la consigne système, `clean_llm_output`, `looks_like_pinyin` avec une relance, et mode dictionnaire pour les mots courts. Tests ajoutés. Clé de cache `llm:…:v3`.
7. Lenteur : vlog de 110 s → 2008 s d'OCR (texte de scène, 364 affinages) et rendu lent. → `ocr.auto_roi` (premier passage sur 20 images, puis OCR limité à la bande des sous-titres) et preset x264 `veryfast` par défaut.

Résultat partiel validé sur `DeqaVjljIVb` (avant les correctifs 5 et 7) : 25 segments, 25 traduits ; `verify` tout vert (durée, fps, résolution, audio identique au MD5, source inchangée, SRT valides) ; traductions correctes (厚 → épaisseur, 硬 → dur, 开 → ouvrir…). Défauts visibles alors : français sur la dernière ligne thaïe (corrigé par le point 5, **non encore revérifié en vidéo**) ; 穷 lu « 究 » et 美 manqué (limites de l'OCR sur une police stylisée).

## 6. Blocages et points ouverts — À FAIRE ENSUITE

1. **Découverte importante, pas encore traitée** : d'après les bandes d'images, **3 vidéos sur 10 n'ont PAS de sous-titres chinois incrustés**. Ce sont des vlogs avec seulement des enseignes et menus chinois filmés, plus un titre thaï : `Deql7rCjNsx`, `Devm500DwjZ`, `DetCsEFCqkB`.
   - Le comportement correct est « aucun sous-titre détecté », avec l'avertissement dans le rapport. Or `detect_subtitle_band` renvoie l'image entière pour 2 d'entre elles, et des enseignes risquent encore d'être retenues.
   - Piste : dans `detect_subtitle_band`/`analysis`, exiger qu'un « sous-titre » change de texte au fil du temps tout en restant à une position stable et centrée. Ou signaler la vidéo « sans sous-titres probables » si la zone dominante est peu peuplée (part d'images avec du chinois centré inférieure à un seuil, par exemple 30 %).
   - À **documenter dans TEST_REPORT** comme vidéos sans sous-titres, et à dire à l'utilisateur.
2. ✅ **Suite de tests relancée** le 2026-10-22 vers 18 h 25, après tous les correctifs et le passage aux chemins portables : **44 réussis sur 45** (journal : `data/logs/pytest_full.txt`, non versionné). Le seul échec venait d'une assertion devenue obsolète avec `auto_roi` : le filigrane du bas n'est plus lu du tout. Le test a été corrigé et repasse seul. Sur le nouveau PC, relancer `python -m pytest` une fois l'installation faite (45 tests attendus).
3. **Relancer le lot complet** sur les 10 vidéos. `auto_roi` et le preset changent l'empreinte OCR, donc tout est recalculé :
   ```
   python scripts\measure_run.py data\instagram -o data\output_instagram --force
   python -m video_ocr verify data\output_instagram
   ```
   - Durée estimée avant optimisation : environ 1 h par vlog. À remesurer.
   - **Ne pas lancer d'autres calculs lourds en même temps** : sur le premier PC, cela a faussé les temps (rendu de 644 s au lieu de 156 s).
4. **Inspecter visuellement** chaque `data\output_instagram\<id>\verification_frames.png` et quelques vidéos : chinois visible, français simultané, pas de recouvrement du thaï, bonne correspondance des segments. Corriger, puis relancer avec `--redo-from segments` si seule l'analyse ou la traduction change.
5. **Mettre à jour `TEST_REPORT.md`** : remplacer la section 6 (« NON EXÉCUTÉ ») par les résultats réels pour chacune des 10 vidéos (segments, traduits, signalés, temps, vérifications, défauts visuels). Ajouter les vidéos sans sous-titres, les limites (OCR des polices stylisées, instabilité du 4B sur certains mots : 薄 → « fin » ou « pauvre » selon l'exécution), les performances réelles, et mentionner yt-dlp avec `no-certifi` autorisé par l'utilisateur. Mettre aussi à jour le README (§8 Performances, §9 Limites, §12 Instagram).
6. Petits points :
   - `data/output_instagram/Deql7rCjNsx/state.json` est resté à `running` (arrêt forcé) ; sans conséquence avec `--force`.
   - Un environnement de test de reproductibilité (≈3 Go) existe dans le dossier temporaire de la session d'origine (`…\AppData\Local\Temp\claude\…\scratchpad\repro_env`) sur le **premier PC** ; il peut être supprimé.
   - Les modèles NLLB et Argos (≈5,5 Go) sont dans `%LOCALAPPDATA%\video_ocr\models` sur le premier PC.

## 7. Carte du code

| Fichier | Rôle |
|---|---|
| `src/video_ocr/config.py` | toute la configuration (dataclasses), chargée depuis `config/default.yaml` |
| `video/ffmpeg_tools.py`, `video/sampler.py` | ffprobe, sélection d'images aux horodatages exacts, `grab_frame` |
| `ocr/engines.py` | RapidOCR (+ `_split_stacked`), PaddleOCR optionnel |
| `ocr/lines.py` | boîtes → lignes → blocs, `expand_with_neighbours`, `envelope_bbox` |
| `ocr/video_ocr.py` | `detect_subtitle_band` (auto-ROI), échantillonnage, saut des images inchangées, bissection |
| `ocr/analysis.py` | textes fixes, zone dominante, filtres centrage/hauteur, choix du bloc, extension typique |
| `segments/grouping.py` | segments, bornes, incertitude, fusion, signalements |
| `translation/engines.py` | LLM (consignes, nettoyage, pinyin, mode dictionnaire), NLLB, Argos |
| `translation/translator.py` | déduplication, cache SQLite, contexte, traductions douteuses |
| `rendering/layout.py`, `overlay.py`, `video_render.py` | placement A/B, dessin, rendu FFmpeg |
| `pipeline/processor.py` | une vidéo, étapes et reprise (`redo_from`) |
| `pipeline/batch.py`, `state.py` | lot et état |
| `export/writers.py`, `export/verify.py` | SRT/JSON/MD/rapport ; `verify` (contrôles et planche d'images) |
| `ui/app.py`, `ui/jobs.py`, `ui/preview.py` | interface Streamlit (`scripts\launch.ps1`) |
| `synthetic.py` | vidéos de test à sous-titres connus |
| `cli.py` | `process` (`--force`, `--redo-from`, `--engine`, `--strategy`, `--interval`, `--roi`), `preview`, `verify`, `check` |
| `scripts/` | `install.ps1`, `launch.ps1`, `run_tests.ps1`, `download_models.py`, `measure_run.py` |

Commandes utiles :
- `python -m video_ocr preview data\instagram\<id>.mp4 --times 3 10 20 -o data\preview\<id>` : aperçu OCR annoté.
- `python -m video_ocr process … --redo-from segments` : réanalyse sans refaire l'OCR.

## 8. Les 10 vidéos

`DeyYW7qDQiZ` (53 s), `DewaCrmHFcM` (131 s), `Devm500DwjZ` (174 s, vlog, **sans sous-titres ?**), `Detr9vXCpnB` (99 s), `DetCsEFCqkB` (109 s, vlog, **sans sous-titres ?**), `Des3v1LDJIa` (59 s), `DermDTjgqrz` (35 s, fréquence d'images variable), `DerIojFALtk` (37 s, sous-titres en bas), `Deql7rCjNsx` (110 s, vlog, **sans sous-titres ?**), `DeqaVjljIVb` (86 s, vocabulaire, caractères isolés stylisés).

URL : `https://www.instagram.com/jinnyteochew_th/reel/<id>/`
