# Rapport de tests — video_ocr

Date : 2026-10-22. Machine : Windows 11 Pro, Intel i7-10510U (4 cœurs / 8 threads, 1,8 GHz), 16 Go RAM, sans GPU utilisé.
Environnement : Conda `video_ocr` (Python 3.11.17, FFmpeg 9.0.2 conda-forge), créé pendant cette session ; aucun autre environnement n'a été modifié.

Légende : ✅ exécuté et réussi · ❌ exécuté et échoué · ⏸️ **non exécuté**.

---

## 0. Synthèse

| Élément | Statut |
|---|---|
| Suite automatisée (41 tests sur le 1ᵉʳ PC, hors ligne `HF_HUB_OFFLINE=1`) | ✅ 41/41 |
| Suite automatisée sur le 2ᵉ PC, environnement recréé par `install.ps1` | ✅ 48/48 après les derniers changements (45 + 3 tests « sans sous-titres », §6), 4 min 41 s |
| Recréation de l'environnement depuis `environment.yml` + tests | ✅ 40/41 (1 échec attendu, voir §2) |
| Chaîne complète sur vidéos synthétiques (chinois traditionnel incrusté) | ✅ texte OCR exact 5/5, erreur temporelle max 0,067 s |
| Inspection visuelle des vidéos **exportées** (images extraites des MP4) | ✅ (2 défauts trouvés puis corrigés, §4) |
| Interface Streamlit (aperçu OCR, lancement, annulation, reprise, résultats) | ✅ testée dans le navigateur |
| **Test sur 10 vidéos du compte Instagram jinnyteochew_th** | ✅ exécuté, `verify` 10/10 OK ; défauts d'OCR et de traduction consignés, non corrigés (§6) |

---

## 1. Suite de tests automatisés

Commande : `python -m pytest -rA -v` dans `video_ocr`, avec `HF_HUB_OFFLINE=1` (preuve du fonctionnement hors ligne). Journal : `data/logs/pytest_full.txt`.

Résultat final : **41 passed in 327.68s**.

| Fichier | Couvre | Résultat |
|---|---|---|
| `test_text_and_lines.py` (6) | caractères traditionnels ≠ simplifiés (這/这, 們/们, 錢/钱…), conservation du texte brut, similarité, lignes multi-boîtes, blocs, extension aux lignes thaïes, rejet d'un objet lu « O » | ✅ |
| `test_segments.py` (7) | filigrane fixe écarté, zone dominante, bornes et ordre, fusion des lectures partielles et trous OCR, segment court conservé et signalé, confiance faible, texte jusqu'à la fin | ✅ |
| `test_exports_and_translation.py` (10) | SRT UTF-8 aller-retour, validation (chevauchements), JSON/Markdown/rapport, traduction : déduplication, cache, isolation d'une panne, détection des traductions douteuses, YAML, empreintes de reprise, découverte des fichiers / fichiers invalides | ✅ |
| `test_video_render.py` (6) | ffprobe, extraction d'images aux horodatages source réels, fichier corrompu/absent, glyphes accentués de la police, retour à la ligne, placements A/B, **rendu bilingue A et B** : source intacte (SHA-256), durée/fps/résolution, **flux audio identique au MD5 près** (synchro A/V), français visible pendant le segment et absent hors segment, bloc chinois non modifié | ✅ |
| `test_pipeline.py` (7) | OCR réel du traditionnel sur image ; **pipeline complet** (texte exact des 5 sous-titres, bornes ±0,15 s, ligne thaïe jamais recouverte — vérité terrain), reprise (ignore une vidéo inchangée, ne refait que le rendu si seul le style change), **annulation puis reprise**, **lot avec fichier corrompu qui continue**, panne de traduction non bloquante (`[traduction indisponible]`), ROI | ✅ |
| `test_translation_models.py` (3) | vrais moteurs **LLM Qwen3-4B, NLLB, Argos** hors ligne | ✅ |
| `test_environment.py` (3) | exécution dans `video_ocr`, Python 3.11, FFmpeg de l'environnement, modules | ✅ |

Les tests distinguent : réussite technique OCR (texte exact), synchronisation (bornes), validité des fichiers (SRT, MP4, audio), placement (vérité terrain), et réussite technique de traduction. **La qualité linguistique n'est pas testée automatiquement** : elle est évaluée à la main au §3.

## 2. Reproductibilité de l'installation

- `conda env create -f environment.yml -p <dossier temporaire>` : ✅ en 11 min 35 s (avec certificat Avast, voir README §10), puis `pip install -r requirements.txt` (ajout de psutil après coup) et `pip check` : « No broken requirements found ».
- Suite de tests dans cet environnement neuf : **40 passed, 1 failed**. L'échec, `test_running_in_video_ocr_env`, est **attendu** : l'environnement temporaire ne s'appelle pas `video_ocr`.
- Problème trouvé : dans un dossier au chemin très long, `rapidocr` → `DLL load failed … Nom de fichier ou extension trop long` (limite Windows de 260 caractères). Ce n'est pas un défaut des fichiers d'installation : le test passe via un chemin court. Ajouté au README (§10).
- `scripts/install.ps1` : ✅ exécuté de bout en bout sur le 2ᵉ PC (`-UseWindowsCertStore`, voir §6). Deux réserves : le script affiche « Installation terminée » même quand le téléchargement des modèles a échoué (`CERTIFICATE_VERIFY_FAILED` côté Hugging Face : le bundle de certificats n'a pas atteint ce téléchargement), qu'il a fallu relancer à part avec les mêmes variables ; et `export_lock.py` ne trouve pas `conda` hors du shell Conda.
- L'environnement temporaire (≈3 Go) reste dans le dossier scratchpad de la session ; il peut être supprimé.

## 3. Choix et qualité de la traduction (évaluation humaine)

10 phrases courtes types (simplifié et traditionnel), mêmes entrées pour chaque moteur :

| Phrase | Qwen3-4B (retenu) | NLLB-600M | Argos |
|---|---|---|---|
| 钱不是万能的，但没有钱是万万不能的 | ✅ L'argent n'est pas tout, mais sans argent, rien n'est possible. | ❌ La richesse n'est pas omnipotente, mais la richesse n'est pas omnipotente. | ≈ … mais c'est impossible sans. |
| 慢慢来，不要着急 | ✅ Viens doucement, ne sois pas pressé | ❌ Allez vite et ne vous précipitez pas. | ≈ Prenez votre temps. Prenez votre temps. |
| 对！ (dans la vidéo) | ✅ Oui ! | ❌ Je vous en prie. | — |
| 阿嬤最喜歡說潮汕話 | ❌ « cantonais » au lieu de teochew | ❌ « parler de l'orage » | ❌ « parler fluffy » |
| 没本事没关系 | ≈ Pas de problème (sens partiel) | ≈ Ce n'est pas grave | ✅ Peu importe si tu ne peux pas. |

Également testés et écartés : Qwen3-1.7B (« Le money n'est pas magique… ») et M2M100-418M (inférieur à NLLB). Conclusion : Qwen3-4B est nettement le plus fidèle, mais il reste imparfait sur les termes dialectaux.

## 4. Chaîne complète et inspection visuelle (vidéos synthétiques)

Faute de vidéos Instagram, deux vidéos de 12 s (720×1280, 30 i/s, AAC) reproduisent la mise en page observée sur les Reels du compte : chinois **traditionnel** vert à contour noir, ligne thaïe dessous, filigrane chinois fixe, fond animé, sous-titres en haut (`synthetic_trad`) ou en bas (`synthetic_bottom`), une phrase de 0,6 s, une phrase sur 2 lignes.

Mesures (configuration par défaut) :

- Sous-titres détectés : **5/5** ; texte OCR **exact 5/5** (lignes multiples comprises) ; filigrane écarté.
- Erreur temporelle : **max 0,067 s, moyenne 0,037 s** (10 bornes), dans l'incertitude annoncée.
- Traductions : 5/5, 0 manquante, 0 douteuse.
- `python -m video_ocr verify` sur les MP4 exportés : statut complet, source inchangée (SHA-256), H.264/AAC, durée 12,000 s = source, 30 i/s = source, 720×1280 = source (stratégie B : 720×1484), **audio identique au MD5 près**, SRT valides. ✅
- Images extraites des MP4 exportés (`verification_frames.png`) : chinois toujours visible, français affiché en même temps, sous le bon segment, accents corrects, lisible. ✅

Défauts trouvés **par l'inspection des fichiers exportés**, puis corrigés et revérifiés :

1. Le français était placé loin du chinois : un disque de la scène lu « O » agrandissait le bloc. → filtrage par hauteur de ligne.
2. Le français recouvrait la ligne thaïe courte « ขอบคุณ » : RapidOCR jetait les boîtes de score < 0,5. → seuil interne désactivé.

Autres défauts trouvés en test et corrigés : fin du dernier sous-titre à 12,0 s au lieu de 11,6 s ; phrase courte non affinée à cause du filigrane ; biais d'environ 0,06 s du filtre `fps` (→ sélection d'images réelles avec horodatage exact) ; Argos qui interrogeait Internet (Stanza → MiniSBD) ; tokenizer NLLB introuvable hors ligne selon l'ordre d'import ; bouton « Lancer / reprendre » qui restait grisé après une annulation dans l'interface.

## 5. Performances mesurées (`scripts/measure_run.py`, vidéo de 12 s)

| Configuration | Total | OCR | Traduction | Rendu | RAM max |
|---|---|---|---|---|---|
| Défaut (LLM, cache de traduction vide) | 177 s | 74 s | 84,5 s (dont chargement ≈25-33 s) | 12 s | 4,3 Go |
| Défaut (traductions en cache) | 66 s | 46 s | 4 s | 12 s | 4,5 Go |
| Stratégie B (bande) | 63 s | 44 s | 5 s (cache) | 10,5 s | 4,5 Go |
| NLLB | 70 s | 42 s | 15,5 s | 9,5 s | 1,8 Go |
| Intervalle 1 s | 105 s | 43 s | 49 s | 10 s | 5,2 Go |

Observations :

- Le temps d'OCR varie de 42 à 74 s d'une exécution à l'autre pour la même vidéo (portable à processeur basse consommation) : ≈1-1,7 s par image analysée en 720 px.
- Avec 5 changements de texte, 24 images échantillonnées et 19 affinages.
- L'intervalle 1 s n'accélère pas l'OCR (13 échantillons mais 26 affinages).
- Traduction LLM ≈5-10 s par sous-titre après chargement.
- Export ≈1× la durée de la vidéo.
- Ramené à la minute de vidéo, ces chiffres extrapolés d'un clip de 12 s (plus de 10 min par minute à froid) sont **non garantis** : la fréquence des changements de texte domine.
- Disque : Qwen3-4B 2,4 Go ; NLLB 4,7 Go (téléchargement Transformers) + 0,6 Go (CT2) ; Argos 0,25 Go ; environnement 3,2 Go.

## 6. Test sur 10 vidéos Instagram — ✅ exécuté (2026-10-22, 2ᵉ PC)

**Origine des fichiers** : les 10 MP4 (237 Mo, `data/instagram/`) avaient été téléchargés sur le premier PC avec yt-dlp, sans connexion ni cookie, et avec `--compat-options no-certifi` (magasin de certificats Windows, à cause d'Avast), **avec l'accord explicite de l'utilisateur** (d'après `HANDOFF.md`). Ils ont été recopiés sur le 2ᵉ PC ; leur durée totale (893 s) correspond. Cette section remplace l'ancienne mention « non exécuté » : ce test a bien été exécuté, avec le code et les modèles décrits ci-dessous.

**Machine** : 2ᵉ PC, environnement `video_ocr` recréé à l'identique par `install.ps1 -UseWindowsCertStore` (Python 3.11.17, FFmpeg 9.0.2, 137 bibliothèques pip identiques au verrou), **45 tests réussis sur 45** (4 min 10 s).

**Commandes** :

```powershell
python scripts\measure_run.py data\instagram -o data\output_instagram --force     # lot complet : 6 304 s (1 h 45)
python -m video_ocr process data\instagram -o data\output_instagram               # reprise du rendu d'une vidéo (voir §6.3)
python -m video_ocr process data\instagram -o data\output_instagram --redo-from segments   # après ajout du critère « sans sous-titres »
python -m video_ocr verify data\output_instagram                                  # 10/10 OK
```

### 6.1 Résultats par vidéo

Temps mesurés lors du lot complet (OCR + traduction + rendu, en secondes) ; le lot a tourné seul sur la machine.

| Vidéo | Durée | Contenu | Segments | Signalés | OCR | Traduction | Rendu | Verdict |
|---|---|---|---|---|---|---|---|---|
| DeqaVjljIVb | 86 s | vocabulaire, mots isolés stylisés | 32 | 15 | 261 | 41 | 14 | ✅ chinois + français visibles ; erreurs d'OCR et de sens (§6.4) |
| DerIojFALtk | 37 s | sous-titres en bas | 12 | 1 | 97 | 26 | 9 | ✅ |
| DermDTjgqrz | 35 s | sous-titres clairsemés, fréquence d'images variable | 2 | 0 | 58 | 3 | 10 | ⚠️ au moins 1 sous-titre manqué (§6.4) |
| Des3v1LDJIa | 59 s | vocabulaire | 8 | 1 | 198 | 13 | 11 | ✅ |
| Detr9vXCpnB | 99 s | vocabulaire | 38 | 13 | 245 | 46 | 16 | ✅ |
| DewaCrmHFcM | 131 s | vocabulaire (famille) | 27 | 2 | 243 | 38 | 20 | ✅ erreurs de sens sur les termes de parenté |
| DeyYW7qDQiZ | 53 s | phrases | 10 | 3 | 101 | 25 | 9 | ✅ 1 fragment parasite (§6.4) |
| Deql7rCjNsx | 110 s | **vlog, aucun sous-titre** | 0 | — | 1 620 | — | 11 | ✅ « aucun sous-titre probable » signalé |
| DetCsEFCqkB | 109 s | **vlog, aucun sous-titre** | 0 | — | 886 | — | 10 | ✅ idem (49 faux segments avant le correctif) |
| Devm500DwjZ | 174 s | **vlog, aucun sous-titre** | 0 | — | 1 728 | — | 33 | ✅ idem (10 faux segments avant le correctif) |

Vérifications automatiques (`verify`) : **10/10 OK** — durée, fréquence d'images et résolution identiques à la source, source inchangée (SHA-256), SRT valides, audio copié sans réencodage.

**Performance** : lot de 893 s de vidéo traité en 6 304 s, soit **423 s par minute de vidéo** ; pic de mémoire 5,9 Go. L'OCR représente 5 437 s sur 6 304 s (86 %). Les trois vlogs coûtent à eux seuls 4 234 s d'OCR (78 % du temps d'OCR) : du texte de scène partout et aucune bande de sous-titres à exploiter.

### 6.2 Vidéos sans sous-titres chinois

Trois vlogs sur dix n'ont **aucun sous-titre chinois incrusté** (enseignes, menus, banderole ; titre thaï seulement). Avant correctif, le lot en tirait 49, 10 et 7 « sous-titres » (`DetCsEFCqkB`, `Devm500DwjZ`, `Deql7rCjNsx`) qui étaient des enseignes (大勝餅, 壹品大…), traduits et incrustés dans la vidéo — constaté sur la planche de `DetCsEFCqkB`.

- **Critère retenu** (`looks_without_subtitles`, `segments.no_subtitle_*`) : au moins 5 segments, **durée médiane < 0,8 s** et **≥ 60 % de segments signalés**. Un texte de scène défile en une fraction de seconde ; un sous-titre reste lisible plusieurs secondes.
- **Choix du critère** : une première idée, la part d'images avec du chinois centré sur 20 images, séparait mal (vlogs 15-30 %, mais `DermDTjgqrz` qui a de vrais sous-titres clairsemés : 33 %). Les statistiques complètes séparent nettement : durée médiane des segments **0,4 s** pour les 3 vlogs contre **≥ 1,4 s** pour les 7 autres ; part de segments signalés **94-100 %** contre **0-47 %**.
- **Comportement** : avertissement dans le rapport, aucun segment traduit ni incrusté (`segments.drop_when_no_subtitles: false` pour les garder et seulement avertir), statut `partial`, accepté par `verify` quand l'avertissement est présent. La vidéo de sortie reste identique à la source.
- **Réserve** : seuils calibrés sur **10 vidéos d'un seul compte**, vérifiés par un seul passage. Ils séparent bien ces données mais ne sont pas démontrés ailleurs. Le coût d'OCR de ces vidéos (§6.1) n'est pas réduit : la détection se fait après l'OCR.
- Test automatique : 3 tests (`test_segments.py`).

### 6.3 Incidents pendant l'exécution

- **`Deql7rCjNsx` a échoué au rendu** (`Permission denied` sur `Deql7rCjNsx_bilingue.partial.mp4`). Ce fichier datait de 17 h 38, d'une exécution interrompue sur le premier PC (état `running`, voir `HANDOFF.md`). Ses droits étaient normaux et il s'ouvrait en écriture quand je l'ai vérifié : le verrou était temporaire, **cause exacte non établie** (scan antivirus probable, non prouvé). Une reprise sans `--force` n'a refait que le rendu, avec succès.
- **`verify` : faux échecs d'audio sur 3 vidéos** (`Deql7rCjNsx`, `DermDTjgqrz`, `Detr9vXCpnB`), message « audio réencodé en AAC ». Le mode enregistré est bien `copy`, le codec reste HE-AAC 44,1 kHz ; l'audio source dépasse la vidéo de 30 à 80 ms et la copie est coupée à la fin de la vidéo, donc le MD5 complet diffère. Correction de `verify` : il compare désormais aussi le début de flux (2 380, 763 et 2 133 paquets identiques). Le message ne parle plus de réencodage quand il n'y en a pas.

### 6.4 Défauts constatés (non corrigés)

- **`DermDTjgqrz` : sous-titre manqué** — 烫到 (≈ 4 s) n'est pas détecté : il est à ≈ 75 % de la hauteur alors que la zone dominante est à 14 % ; `auto_roi` limite l'OCR à cette bande. Limite connue de l'ROI automatique quand la position des sous-titres change dans une même vidéo (déjà observé à la lecture des Reels, voir ci-dessus). Contournement : `--roi 0 0 1 1` ou `ocr.auto_roi: false`, plus lent.
- **`DeyYW7qDQiZ` : fragment parasite** — « 口 » (0,27 s, entre deux sous-titres) est traduit « bouche » et incrusté ; il est correctement signalé `short`.
- **Mode dictionnaire (mots courts, via l'anglais)** : fuites de mots anglais, ex. 鱼胶 → « gelatin. » (au lieu de « gélatine » / « colle de poisson »), 排骨 → « os » (au lieu de « côtes »).
- **Termes de parenté** (`DewaCrmHFcM`) : 儿媳妇 → « fille de loi » (belle-fille), 大姑 → « mère de la sœur cadette » (OCR « 大姑 的m »), 阿嫂 → « sœur ».
- **OCR de polices stylisées** (`DeqaVjljIVb`) : 穷 lu « 品 » (« goût »), 富高 → « très réussie » ; l'instabilité du 4B sur certains mots reste présente (薄 → « fin » ou « pauvre » selon l'exécution).
- **Qualité linguistique** : évaluée sur les planches de `verification_frames.png` (6 images par vidéo, soit 42 segments (6 images × 7 vidéos) sur 129), **pas** segment par segment ni par un locuteur du chinois. Aucune mesure chiffrée de qualité de traduction.
- **Non inspecté** : la lecture des vidéos exportées en continu (synchronisation fine, lisibilité en mouvement) — seules des images fixes et les contrôles automatiques ont été examinées.

## 7. Définition du « terminé » (spec §12)

| Critère | État |
|---|---|
| S'exécute dans `video_ocr` | ✅ |
| Environnement recréable depuis les fichiers | ✅ (§2) |
| Vidéo locale à sous-titres traditionnels traitée de bout en bout | ✅ synthétique et 10 vidéos réelles |
| Chinois extrait avec horodatages | ✅ |
| Traduction sans API payante | ✅ (Qwen3-4B, NLLB, Argos, hors ligne) |
| Vidéo exportée avec chinois et français simultanés | ✅ (inspecté) |
| Français synchronisé et lisible | ✅ synthétique ; réel : images fixes inspectées, lecture continue non vérifiée |
| Source inchangée | ✅ |
| Lot de plusieurs vidéos, une erreur ne bloque pas le lot | ✅ |
| SRT, JSON, rapports valides | ✅ |
| Tests exécutés et documentés | ✅ |
| Instructions d'installation et de lancement vérifiées | ✅ partiellement (étapes exécutées une à une ; `install.ps1` non lancé d'un bloc) |
| **Validation sur vidéos Instagram réelles** | ✅ exécutée (§6) ; qualité linguistique non mesurée, défauts consignés |
