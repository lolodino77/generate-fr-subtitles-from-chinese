# HANDOFF — état du projet pour reprise sur un autre ordinateur

Rédigé le 2026-10-22 vers 18 h, au moment d'une pause demandée par l'utilisateur.
Ce document se suffit à lui-même : il ne suppose aucun accès à la conversation d'origine.

**Mis à jour le 2026-10-22 (soir) sur le 2ᵉ PC** : installation refaite à l'identique, lot des 10 vidéos exécuté et vérifié, critère « sans sous-titres » ajouté. **Lire d'abord le §0 ci-dessous.**

---

## 0. À lire en premier (état réel à la fin de la session du 2ᵉ PC)

1. **`data/` n'est pas dans Git** (`.gitignore`). Les 10 vidéos (`data/instagram/`, 237 Mo) et les résultats (`data/output_instagram/`, dont les 10 `*_bilingue.mp4`) ne passent que par OneDrive ou par copie manuelle. Sans eux, l'autre PC ne peut pas reproduire le lot.
2. **Les modèles ne passent pas par Git non plus** : `%LOCALAPPDATA%\video_ocr\models` (≈ 8 Go). À retélécharger (`download_models.py --all`) ou à copier.
3. **Environnement** : `video_ocr` existe sur ce PC (créé par `install.ps1 -UseWindowsCertStore`). Versions vérifiées : Python 3.11.17, FFmpeg 9.0.2, `pip check` propre, `video_ocr check` tout OK, **48 tests réussis sur 48** (4 min 41 s).
4. **Piège rencontré à l'installation** (antivirus qui inspecte le HTTPS) : `install.ps1 -UseWindowsCertStore` crée l'environnement, mais le bundle de certificats **n'atteint pas** le téléchargement des modèles Hugging Face, qui échoue en `CERTIFICATE_VERIFY_FAILED` alors que le script affiche « Installation terminée ». Contournement qui a fonctionné, pour la session seulement : définir `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE` et `PIP_CERT` vers `.certs\ca_bundle.pem`, puis lancer `python scripts\download_models.py --all` directement. Lancer ensuite `python -m video_ocr check` : il doit être entièrement vert.
5. `python scripts\export_lock.py` échoue hors du shell Conda (il ne trouve pas `conda`). Les verrous du dépôt n'ont pas été régénérés ; `pip freeze` a été comparé à la main au verrou pip (identique).
6. **Variable utile** : `HF_HUB_OFFLINE=1` évite des attentes réseau quand les modèles sont déjà en cache.
7. **NOUVEAU (2026-10-23, 3ᵉ session) — traduction en ligne par navigateur, moteur par défaut** (`translation.engine: browser`). Demande de l'utilisateur : les petits modèles locaux traduisent mal, le disque manque, les textes ne sont pas confidentiels, et les API gratuites (clé Gemini) sont trop saturées. Implémentation inspirée de son projet `auto-wordpress-translator` (`llm_browser.py`) : Playwright + profil Chrome persistant, prompt collé, réponse lue dans le dernier bloc de code jusqu'à `###FIN###`.
   - Code : `translation/browser_llm.py` (`BrowserSession`, `BrowserTranslator`, `SITES`, `build_prompt`, `parse_numbered`), voie `_translate_chunks` dans `translation/translator.py`, `Engines.close()`, commande `python -m video_ocr login`.
   - **Validé en réel** sur Gemini en mode invité (sans compte) : 8 sous-titres en 18,7 s, puis **les 7 vidéos à sous-titres du lot traduites par Gemini seul** (0 repli local, glossaire utilisé 27 fois), traductions nettement meilleures que Qwen3-4B local. **Non testé en réel** : ChatGPT (exige un compte), captchas et limites du service. Tests hors ligne avec faux navigateur : `tests/test_browser_translation.py`. Détails et défauts : `TEST_REPORT.md` §6.5 B.
   - Le profil du navigateur (`%LOCALAPPDATA%\video_ocr\browser_profile`) n'est ni dans le dépôt ni dans OneDrive : sur un autre PC, refaire `python -m video_ocr login` (ou utiliser Gemini en invité).
   - Les sélecteurs CSS des sites (`SITES`) peuvent changer : c'est le premier endroit à regarder si la traduction échoue (« zone de saisie introuvable », « pas de réponse complète »).
   - **Reste à faire** : proposer à l'utilisateur de supprimer les modèles locaux devenus inutiles (NLLB ≈ 5,3 Go, Argos ≈ 0,25 Go ; Qwen3-4B ≈ 2,4 Go est le secours facultatif) : **rien n'a été supprimé** ; regarder les 5 planches `verification_frames.png` non inspectées (`data/output_instagram_v2/*/`) ; tester ChatGPT en secours (`python -m video_ocr login`).
8. **NOUVEAU (2026-10-23) — écart anticipé des vidéos sans sous-titres** (demande de l'utilisateur : ignorer ces vidéos). Une **sonde de ~20 images** (`ocr/video_ocr.py: probe_subtitles`, indicateurs et règle dans `ocr/analysis.py: sample_indicators, likely_no_subtitles`) décide avant l'OCR complète : la vidéo est écartée (statut `partial`, `state.no_subtitles`, rapport, **aucune vidéo produite**, `verify` OK) si moins de 15 % d'images « type sous-titre » (**seul critère** depuis la décision A du 2026-10-23 : le critère « lignes longues » a été retiré, voir point 13 et `TEST_REPORT.md` §6.7). Réglage : `ocr.skip_when_no_subtitles` et `ocr.no_subtitle_*`.
   - Vérifié en réel : les 3 vlogs écartés (sonde de 60 à 122 s, **lot des trois en 291 s** au lieu de ≈ 1 h), les 7 autres vidéos non écartées. `python scripts\probe_samples.py <vidéos>` refait la mesure.
   - **Réserve** : seuil validé sur 33 vidéos d'un seul compte (écartées à juste titre : 0-10 % ; à sous-titres : 21-100 %). Trois vlogs (15-24 %) ne sont plus écartés par la sonde mais seulement après l'OCR. Désactiver la règle si besoin.
9. **Autres changements de cette session** (voir `TEST_REPORT.md` §6.5 A) : sous-titres à plusieurs hauteurs (`ocr.secondary_zone_ratio`, `max_zones`), caractères isolés parasites écartés (`segments.single_char_min_s`, `recurring_single_char`), glossaire local `config/glossary.yaml` (termes de parenté), polices par nom et chemins relatifs. **Suite de tests : 85/85** (6 min 9 s, hors ligne, après la décision A).
10. **Git** : le commit de cette session est sur la branche `video-ocr-app` (voir le message de commit ; il part après `4fdc42d`). Dernier commit poussé avant : `4fdc42d`. Pousser en HTTPS avec `git -c http.sslBackend=schannel push …` si un antivirus intercepte le HTTPS.
11. **Lot des 30 autres vidéos — TERMINÉ le 2026-10-23** (résultats dans `data/output_instagram_v2`, bilan détaillé dans `TEST_REPORT.md` §6.6) : 23 traitées, 7 écartées par la sonde (toutes vérifiées à l'œil), 204 segments dont 202 traduits (Gemini seul, 0 repli local), 95 min de calcul. **Le lot s'est d'abord arrêté à 1 vidéo** (fins de ligne `\r` collées aux chemins de la liste) : si vous régénérez une liste de vidéos, retirez les `\r`. Pour reprendre un lot interrompu : relancer la même commande, les vidéos terminées sont sautées.
12. **Défaut connu NON corrigé (décision de l'utilisateur) : lignes mixtes chinois + thaï** (`TEST_REPORT.md` §6.6). Un sous-titre chinois lu d'un seul bloc avec le thaï voisin (« 着火ladi ») est classé « non chinois » par `ocr.min_cjk_ratio` (0,5) et perdu. Confirmé sur `DeAzmhqAThH` (« 着火 » vers 8 s) ; 3 autres vidéos ont des lignes semblables mais ce sont des bannières ou du texte de scène (une, `DdybOa6Dggk`, non vérifiée à l'œil). Correction possible mais **refusée pour l'instant** : garder la suite de caractères chinois d'une ligne mixte (≥ 2 caractères, bon score) puis refaire l'OCR des vidéos concernées (les observations ne gardent pas les blocs d'origine) ; risque d'accepter du thaï mal lu comme du chinois.
13. **Règle d'écartement révisée (décision A de l'utilisateur, 2026-10-23)** : sur les 9 écartements du lot de 30, 2 étaient faux (`Del8z_ziYQH` par la sonde, `DeS37izE5lk` par le critère après OCR). Le critère « lignes longues » a été **retiré** de la sonde (champs `no_subtitle_sample_ratio` et `no_subtitle_long_line_cjk` supprimés) ; il ne reste que le seuil de 15 %. Revalidé hors ligne sur 33 vidéos : 0 vidéo à sous-titres écartée, les 7 bons écartements conservés, 3 vlogs (`DeYtWIolGAa`, `Devm500DwjZ`, `DetCsEFCqkB`) passent désormais la sonde. **Conséquence évitée** : supprimer ces champs changeait l'empreinte OCR et aurait fait recalculer toutes les vidéos. Les réglages de la sonde sont maintenant exclus de l'empreinte (`HASH_EXCLUDED` dans `pipeline/state.py`), `8` et `8.0` donnent la même empreinte, et `python scripts/migrate_hashes.py data/output_instagram_v2` a réécrit les empreintes des résultats existants (seules 3 vidéos ont une étape à recalculer, légitimement : `DeS37izE5lk` segments, `DetCsEFCqkB` et `Devm500DwjZ` traduction). Pour re-sonder une vidéo écartée après avoir changé le seuil : `--force`, ou `ocr.skip_when_no_subtitles: false` (reprise automatique). **Non résolu, distinct** : `DeS37izE5lk` reste non fiable (étiquette fixe non filtrée, point 14) ; le critère après OCR `looks_without_subtitles` l'a écartée à tort (`segments.drop_when_no_subtitles`).
14. **`DeS37izE5lk` : sortie NON fiable, à ne pas livrer** (`TEST_REPORT.md` §6.6) : l'étiquette fixe « 中文 潮州话 泰语 » est traduite « Chinois, teochew, thaï » pendant presque toute la vidéo, les vraies phrases ne sont lues que par fragments, et l'encadré français recouvre en partie le chinois sur une image. Cause probable : le filtre « texte fixe » compare des textes exacts et échoue quand l'OCR lit l'étiquette de plusieurs façons (piste : comparer avec `similarity`). Non corrigé.
15. **Bug corrigé (2026-10-23)** : l'empreinte de reprise dépendait du type des nombres (`8` dans `config/default.yaml`, `8.0` dans le code), ce qui refaisait toute l'OCR (constaté : 1 170 s). Les nombres entiers sont maintenant normalisés (`_canonical` dans `pipeline/state.py`) ; test dans `tests/test_pipeline.py`.
16. **Bug corrigé** : `state.no_subtitles` restait à vrai après un retraitement et faisait échouer `verify` (test `test_skipped_then_processed_leaves_a_consistent_state`).
17. **NOUVEAU (2026-10-23) — empreintes de reprise et sonde** : les réglages de la sonde (`ocr.skip_when_no_subtitles`, `ocr.no_subtitle_min_frames`, `ocr.no_subtitle_clear_ratio`) sont exclus de l'empreinte OCR (`HASH_EXCLUDED`, `pipeline/state.py`) : les modifier ne recalcule rien. Désactiver `skip_when_no_subtitles` retraite une vidéo précédemment écartée (`processor.py`). `scripts/migrate_hashes.py <dossier>` (`--dry-run` d'abord) met à jour les empreintes des résultats existants sans rien recalculer ; il ne touche qu'une étape dont la configuration enregistrée donne la même empreinte après suppression des champs retirés. Résultat sur `data/output_instagram_v2` : 37 vidéos à jour, 3 étapes à recalculer (`DeS37izE5lk` segments ; `DetCsEFCqkB` et `Devm500DwjZ` traduction). **Limite** : l'empreinte reste sensible à la structure de la configuration ; une liste blanche des réglages par étape (non faite) supprimerait cette fragilité.

---

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
| Tests automatisés | ✅ **48/48** sur le 2ᵉ PC, code final (45 + 3 tests « sans sous-titres ») |
| Reproductibilité de l'environnement (`environment.yml`) | ✅ vérifiée (40/41, l'échec restant est attendu) |
| Téléchargement des 10 Reels | ✅ dans `data/instagram/` (237 Mo, yt-dlp, autorisé par l'utilisateur) |
| Traitement des 10 vraies vidéos | ✅ **fait** (lot de 6 304 s) ; `verify` 10/10 OK ; 7 vidéos bilingues + 3 vlogs sans sous-titres (§6) |
| `TEST_REPORT.md` | ✅ section 6 réécrite avec les résultats réels |

Aucun processus ne tourne.

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

**État des points ci-dessous (2026-10-22, soir) :**

| # | Point | État |
|---|---|---|
| 1 | Vidéos sans sous-titres | ✅ traité : `looks_without_subtitles` (`segments/grouping.py`, seuils `segments.no_subtitle_*`, interrupteur `drop_when_no_subtitles`). Seuils calibrés sur ces 10 vidéos seulement. |
| 2 | Tests | ✅ 48/48 |
| 3 | Lot complet | ✅ fait, 423 s de calcul par minute de vidéo, pic 5,9 Go |
| 4 | Inspection visuelle | ✅ planches `verification_frames.png` regardées pour les 10 vidéos ; **lecture continue des MP4 non faite** |
| 5 | `TEST_REPORT.md` / README | ✅ mis à jour |
| 6 | Petits points | 🔸 voir ci-dessous |

**Reste à faire (défauts consignés dans `TEST_REPORT.md` §6.4, non corrigés) :**

- `DermDTjgqrz` : sous-titre 烫到 (≈ 4 s) manqué. Il est à ≈ 75 % de la hauteur, la zone dominante à 14 % ; `auto_roi` limite l'OCR à cette bande. Piste : élargir ou fusionner plusieurs bandes dans `detect_subtitle_band`, ou tester `--roi 0 0 1 1` pour mesurer le coût.
- `DeyYW7qDQiZ` : segment « 口 » (0,27 s) traduit « bouche » alors qu'aucun chinois n'est visible ; signalé `short`. Piste : écarter les segments d'un seul caractère très brefs entre deux sous-titres.
- Traduction : mots anglais dans le mode dictionnaire (鱼胶 → « gelatin. », 排骨 → « os »), termes de parenté (儿媳妇 → « fille de loi »).
- Le coût d'OCR des vlogs (≈ 78 % du temps d'OCR du lot) n'est pas réduit : la détection « sans sous-titres » se fait après l'OCR.
- Non vérifié : l'interface Streamlit n'a pas été relancée sur ce PC (`scripts\launch.ps1`).
- À décider avec l'utilisateur : le cahier des charges parle de chinois **traditionnel**, les vidéos réelles du compte sont en chinois **simplifié**.

**Incident à connaître** : `Deql7rCjNsx` avait échoué au rendu (`Permission denied` sur un `.partial.mp4` datant de l'ancien PC). Cause exacte non établie ; une reprise sans `--force` a suffi. `data/output_instagram/batch_summary_run1.json` et `batch_report_run1.md` conservent le résumé du lot d'origine (le résumé courant a été écrasé par la reprise).

**Ancien texte du §6, conservé pour mémoire (points 1 à 6 d'origine) :**

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
