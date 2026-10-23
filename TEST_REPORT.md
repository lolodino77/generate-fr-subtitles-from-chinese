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
- **Réserve** : seuils calibrés sur **10 vidéos d'un seul compte**, vérifiés par un seul passage. Ils séparent bien ces données mais ne sont pas démontrés ailleurs. Le coût d'OCR de ces vidéos (§6.1) n'était pas réduit à ce stade : la détection se faisait après l'OCR (réduit depuis par la sonde, §6.5 C).
- Test automatique : 3 tests (`test_segments.py`).

### 6.3 Incidents pendant l'exécution

- **`Deql7rCjNsx` a échoué au rendu** (`Permission denied` sur `Deql7rCjNsx_bilingue.partial.mp4`). Ce fichier datait de 17 h 38, d'une exécution interrompue sur le premier PC (état `running`, voir `HANDOFF.md`). Ses droits étaient normaux et il s'ouvrait en écriture quand je l'ai vérifié : le verrou était temporaire, **cause exacte non établie** (scan antivirus probable, non prouvé). Une reprise sans `--force` n'a refait que le rendu, avec succès.
- **`verify` : faux échecs d'audio sur 3 vidéos** (`Deql7rCjNsx`, `DermDTjgqrz`, `Detr9vXCpnB`), message « audio réencodé en AAC ». Le mode enregistré est bien `copy`, le codec reste HE-AAC 44,1 kHz ; l'audio source dépasse la vidéo de 30 à 80 ms et la copie est coupée à la fin de la vidéo, donc le MD5 complet diffère. Correction de `verify` : il compare désormais aussi le début de flux (2 380, 763 et 2 133 paquets identiques). Le message ne parle plus de réencodage quand il n'y en a pas.

### 6.4 Défauts constatés lors du lot du 2026-10-22

**Mise à jour du 2026-10-23 : les trois premiers défauts ci-dessous ont été corrigés ou remplacés, voir §6.5.** Le texte d'origine est conservé.

- **`DermDTjgqrz` : sous-titre manqué** (✅ corrigé, §6.5) — 烫到 (≈ 4 s) n'est pas détecté : il est à ≈ 75 % de la hauteur alors que la zone dominante est à 14 % ; `auto_roi` limite l'OCR à cette bande. Limite connue de l'ROI automatique quand la position des sous-titres change dans une même vidéo (déjà observé à la lecture des Reels, voir ci-dessus). Contournement : `--roi 0 0 1 1` ou `ocr.auto_roi: false`, plus lent.
- **`DeyYW7qDQiZ` : fragment parasite** (✅ corrigé, §6.5) — « 口 » (0,27 s, entre deux sous-titres) est traduit « bouche » et incrusté ; il est correctement signalé `short`.
- **Mode dictionnaire (mots courts, via l'anglais)** (✅ remplacé par la traduction en ligne, §6.5) : fuites de mots anglais, ex. 鱼胶 → « gelatin. » (au lieu de « gélatine » / « colle de poisson »), 排骨 → « os » (au lieu de « côtes »).
- **Termes de parenté** (✅ glossaire local + traduction en ligne, §6.5) : 儿媳妇 → « fille de loi » (belle-fille), 大姑 → « mère de la sœur cadette » (OCR « 大姑 的m »), 阿嫂 → « sœur ».
- **OCR de polices stylisées** (`DeqaVjljIVb`) : 穷 lu « 品 » (« goût »), 富高 → « très réussie » ; l'instabilité du 4B sur certains mots reste présente (薄 → « fin » ou « pauvre » selon l'exécution).
- **Qualité linguistique** : évaluée sur les planches de `verification_frames.png` (6 images par vidéo, soit 42 segments (6 images × 7 vidéos) sur 129), **pas** segment par segment ni par un locuteur du chinois. Aucune mesure chiffrée de qualité de traduction.
- **Non inspecté** : la lecture des vidéos exportées en continu (synchronisation fine, lisibilité en mouvement) — seules des images fixes et les contrôles automatiques ont été examinées.

### 6.5 Session du 2026-10-23 : corrections, traduction en ligne, écart anticipé

**A. Corrections d'OCR et de segmentation (vérifiées sur les sorties réelles).**

- **Sous-titres à plusieurs hauteurs** : `DermDTjgqrz` passe de 2 à **4 segments** (烫到, 人参汤, 鱼胶, 排骨) ; trois zones détectées (14 %, 70 %, 81 % de la hauteur).
- **Caractères isolés parasites** : `DeyYW7qDQiZ` passe de 10 à **6 segments** ; les quatre fragments « 口 » (un boîtier lu comme un caractère) ont disparu.
- **Non mesuré** : le gain de temps de l'affinage limité aux lignes centrées (seul le taux de changement de texte a été calculé, pas le temps gagné).

**B. Traduction en ligne par navigateur (moteur par défaut).** Chrome piloté par Playwright, profil dédié, **Gemini en mode invité (aucun compte)**, à la demande de l'utilisateur (modèles locaux de qualité insuffisante, disque limité, textes non confidentiels).

- Essai réel isolé : 8 sous-titres en 18,7 s. Dans le pipeline, les 7 vidéos à sous-titres ont toutes été traduites par Gemini (96 sous-titres envoyés), **0 repli sur le modèle local**, glossaire utilisé 27 fois (`Detr9vXCpnB`).
- Durées par vidéo : traduction **12,9 à 28,6 s**, rendu **36 à 93 s**. Contrôles `verify` : **9/9 OK** dans `data/output_instagram_v2` (7 vidéos + 2 vlogs classés sans sous-titres).
- **Qualité** : nettement meilleure que Qwen3-4B local sur les exemples relus (« 排骨 » → « côtes de porc », « 儿媳妇 » → « belle-fille », « 口渴 » → « J'ai soif », « 没本事可以再学 » → « Le talent s'apprend » au lieu d'un contresens). **Mesure chiffrée : aucune** ; relecture de quelques exemples seulement, pas par un locuteur du chinois.
- **Rendu** : planches d'images extraites des MP4 regardées pour **2 vidéos sur 7** (`DewaCrmHFcM`, `DermDTjgqrz`) : chinois visible, français en même temps sous le bloc chinois et thaï, sans recouvrement. Les 5 autres planches n'ont pas été regardées.
- **Défauts constatés** :
  - 4 segments de `DeqaVjljIVb` (高丽, 高富/前9, 富高, 育富) sans traduction : l'OCR de ces polices stylisées est illisible, le modèle répond « [illisible] ». Rien n'est incrusté ; le SRT français porte « [traduction indisponible] ».
  - Les erreurs d'OCR sont **devinées** au lieu d'être signalées : 太具 → « arrière-grand-père », 大具 → « grand-père paternel », 品 → « Article » (non signalé).
  - Deux traductions très concises (« L'argent se retrouve » pour 没钱可以再找).
  - `大姑 / 的m` (ligne thaïe mal lue) : le modèle a répondu « grand-tante paternelle | [illisible] », fausse et affichée telle quelle. **Corrigé ensuite** (partie « illisible » retirée, glossaire essayé sur la 1ʳᵉ ligne), **testé par tests unitaires, pas revérifié sur la vidéo**.
- **Non testé en réel** : ChatGPT (exige un compte), le moteur sur d'autres comptes ou d'autres jours, et le comportement en cas de captcha ou de limite de service.
- **Limites** : dépend de l'interface web de Gemini (sélecteurs CSS susceptibles de changer, fenêtre Chrome visible pendant la traduction) ; les textes quittent le PC ; les conditions d'utilisation du service peuvent restreindre l'automatisation.

**C. Écart anticipé des vidéos sans sous-titres (sonde de 20 images).** Les vlogs coûtaient 78 % du temps d'OCR du lot précédent (1 699 s, 907 s, plus 540 s d'un traitement interrompu). Indicateurs mesurés sur les 10 vidéos (sonde réelle, image entière) :

| Vidéo | Images « type sous-titre » | Caractères par ligne | Décision |
|---|---|---|---|
| DeyYW7qDQiZ | 71 % | 4,9 | traitée |
| DewaCrmHFcM | 80 % | 2,6 | traitée |
| Detr9vXCpnB | 71 % | 1,9 | traitée |
| Des3v1LDJIa | 52 % | 3,5 | traitée |
| DermDTjgqrz | **44 %** | 2,1 | traitée (la plus proche de la frontière) |
| DerIojFALtk | 84 % | 4,7 | traitée |
| DeqaVjljIVb | 52 % | 1,1 | traitée |
| Devm500DwjZ | 20 % | 7,6 | **écartée** |
| DetCsEFCqkB | 24 % | 7,0 | **écartée** |
| Deql7rCjNsx | 5 % | 21,9 | **écartée** |

- **Règle (version initiale, remplacée au §6.7)** : écartée si moins de 15 % d'images « type sous-titre », ou moins de 33 % **et** lignes de plus de 5,5 caractères. Échantillon de moins de 8 images : jamais d'écart. Désactivable : `ocr.skip_when_no_subtitles: false`.
- **Vérification réelle avec le code final** : les 3 vlogs sont écartés (sonde de 107 s, 60 s et 122 s, **lot des trois en 290,9 s**), sans OCR complète, traduction ni rendu ; `verify` OK (aucune vidéo produite, source inchangée, rapport présent). La sonde, relancée sur les 7 autres vidéos, **n'en écarte aucune**.
- **Réserve importante** : seuils calibrés **et** vérifiés sur les **mêmes 10 vidéos d'un seul compte** ; ce n'est pas une validation indépendante. Marge côté sous-titres : 11 points (44 % contre 33 %) pour `DermDTjgqrz`. Une vidéo avec peu de sous-titres et des lignes longues risque d'être écartée à tort.

**D. Tests** : suite complète, hors ligne (`HF_HUB_OFFLINE=1`), avec le code final : **81 réussis sur 81** en 8 min 5 s (journal `data/logs/pytest_full.txt`, non versionné). Elle couvre notamment le moteur en ligne avec un **faux navigateur** (succès, panne d'un site, réponse incomplète, secours local, cache, glossaire), l'écart anticipé (les 10 profils réellement mesurés, y compris la frontière, plus le pipeline complet sur une vidéo sans texte), les corrections d'OCR et de segmentation, et les deux dernières corrections de traduction. **Non couvert par les tests automatiques** : le vrai site de Gemini, vérifié seulement à la main (§6.5 B). Deux bugs ont été trouvés par ces tests pendant la session : un plantage sur une vidéo sans aucun texte chinois et un défaut d'espaces autour des guillemets français dans l'analyse des réponses.

### 6.6 Lot des 30 autres vidéos (2026-10-23) — terminé

Les 30 vidéos de `data/instagram/` non encore traitées (33,3 min de vidéo au total), avec la pipeline finale (sonde, traduction en ligne par Gemini en mode invité). Résultats dans `data/output_instagram_v2`.

**Déroulement**

- **Incident de lancement (mon erreur)** : le premier lancement n'a traité qu'**1 vidéo sur 30** (`DezEI4fjLD_`) : la liste avait été écrite avec des fins de ligne Windows (`\r`) restées collées à 29 chemins, jugés invalides. Corrigé et relancé ; la vidéo déjà faite a été sautée.
- **Durée** : lot de 30 vidéos en **5 697 s (95 min)**, soit 171 s de calcul par minute de vidéo, pic de mémoire 1,6 Go. Chiffre à prendre comme un ordre de grandeur : une exécution sur un PC, sans autre charge importante.
- **Statuts finaux (après le retraitement de 2 vidéos, voir plus bas)** : **23 traitées, 7 écartées par la sonde**, 0 échec. **204 segments, dont 202 traduits** ; 69 segments signalés (confiance faible, segment très court, lectures divergentes…).
- **Traduction** : toutes les traductions viennent de Gemini, **0 repli sur le modèle local**. 2 segments sans traduction (1 dans `Delch9ODhwe`, 1 dans `DeS37izE5lk`).
- **Contrôles `verify`** : OK sur les 39 dossiers de `output_instagram_v2` avant le retraitement ; les 2 vidéos retraitées ont été vérifiées individuellement ensuite (OK).

**Contrôle visuel des écartements : 2 sur 9 étaient faux.** J'ai regardé des images de chacune des 9 vidéos écartées au premier passage (sonde ou critère après OCR) :

| Vidéo | Ce que montrent les images | Verdict |
|---|---|---|
| `Dd0Wy1kgahR`, `DegxcfClRwU`, `DeoUfUNgWJV` | vlogs ; le texte chinois jaune vu brièvement est le sous-titre d'un **film projeté** filmé par la caméra (même séquence dans les trois) | juste |
| `Dd3UkvwCsYL` | sous-titres verts **en thaï uniquement** | juste |
| `De0pkdiGNao`, `DeYtWIolGAa`, `DeitFdGkrYJ` | vlogs, titres thaïs, enseignes ou bannières filmées | juste |
| `Del8z_ziYQH` | **sous-titres chinois en phrases** (« 去外省工作 », « 那个女孩子出门了 ») avec thaï dessous | **faux** (sonde : 29 % d'images « type sous-titre », 6,1 caractères par ligne, donc « lignes longues ») |
| `DeS37izE5lk` | **sous-titres chinois en phrases longues** sur presque toute la vidéo | **faux** (critère après OCR : « 39 textes très brefs et instables ») |

- **Cause** : les seuils de la sonde ont été calibrés sur des sous-titres **courts** (mots de vocabulaire). Le critère « lignes longues = enseignes » ne vaut pas pour des sous-titres en phrases. **La règle d'écartement n'est donc pas fiable sur ce type de vidéo** ; les 7 écartements restants (tous vérifiés justes) ne prouvent pas le contraire, l'échantillon est petit. Le seuil de 15 % de la règle « claire » a aussi été frôlé par `DeYtWIolGAa` (affiché 15 %).
- **Retraitement des 2 vidéos écartées à tort** (écartement désactivé par un fichier de configuration temporaire, sans toucher aux réglages par défaut) :
  - `Del8z_ziYQH` : **correct**, 2 segments traduits, français sous le bloc chinois et thaï (planche regardée). **Il manque** le titre vert « 出门 ??? » du début de la vidéo (style et position différents).
  - `DeS37izE5lk` : **mauvais résultat** (planche regardée). L'étiquette fixe en bas à gauche « 中文 潮州话 泰语 », lue de façons variables, n'est pas reconnue comme texte fixe et est traitée comme un sous-titre : sa traduction « Chinois, teochew, thaï » s'affiche pendant l'essentiel de la vidéo, alors que les vraies phrases ne sont lues que par fragments de 0,1 à 0,5 s. Sur une image, l'encadré français **recouvre en partie le sous-titre chinois**. **Cette vidéo exportée n'est pas fiable** ; elle aurait été moins trompeuse non traitée.
- **Défauts de la pipeline mis en évidence** : (a) le filtre « texte fixe » compare des textes exacts et échoue quand l'OCR lit l'étiquette de plusieurs façons ; (b) les longues phrases multi-lignes sur fond mouvant sont lues de façon instable.

**Défaut constaté, NON corrigé (décision de l'utilisateur : le consigner seulement) — lignes mixtes chinois + thaï.**

- **Symptôme** : dans `DeAzmhqAThH`, le sous-titre « 着火 » est visible vers 8 s (images à 5 s : absent, 8 s : présent, 11 s : absent) mais ne figure dans **aucun segment**. Les trois autres sous-titres de la vidéo sont captés, avec les bonnes bornes.
- **Cause établie dans les observations OCR** : « 着火 » et le thaï voisin sont lus **d'un seul bloc**, le thaï mal lu en lettres latines (« 着火ladi », « 着火lanedi »), score 0,64 à 0,72. Les caractères chinois ne font que 2 sur 7 à 9 caractères : la ligne est classée « non chinoise » par `ocr.min_cjk_ratio` (0,5).
- **Ampleur mesurée** : sur 19 vidéos qui avaient des observations ce jour-là, 4 contiennent des lignes « non chinoises » avec au moins 2 caractères chinois et un score ≥ 0,6 : deux vlogs écartés (bannière « 双语游学 »), `DdybOa6Dggk` (probablement du texte de scène, **non vérifié à l'œil**) et `DeAzmhqAThH` (seul cas confirmé). **Taux sur l'ensemble des 30 vidéos non mesuré.**
- **Correction envisagée, non appliquée** : garder la suite de caractères chinois d'une ligne mixte (≥ 2 caractères, bon score) ; risque d'accepter du thaï mal lu comme du chinois ; il faudrait refaire l'OCR des vidéos concernées (les observations ne gardent pas les blocs d'origine). Abaisser `ocr.min_cjk_ratio` : piste non testée.

**Contrôle des vidéos à peu de segments** (3 regardées) : `De0izbCD9oy` n'a bien qu'un long sous-titre (0 → 37 s) ; `Dd-mj6Jj48R` est exacte (bornes 13,53 s et 13,93 s confirmées sur des images à 9, 10… 17 s) ; `DeAzmhqAThH` a perdu « 着火 » (ci-dessus).

**Bugs de la pipeline trouvés pendant ce lot**

- **Corrigé, testé** : après un écartement puis un retraitement, l'indicateur « sans sous-titres » restait à vrai dans l'état, donc `verify` échouait (« vidéo non produite ») alors que la vidéo existait. Corrigé (remise à zéro au retraitement, test de non-régression) ; l'état de `Del8z_ziYQH` a été réparé par une reprise de 2,6 s.
- **NON corrigé** : l'empreinte de reprise dépend du **type numérique** des réglages : `dense_fps` vaut `8` (entier) dans `config/default.yaml` mais `8.0` (décimal) par défaut dans le code, donc une configuration chargée depuis un autre fichier donne une empreinte d'OCR différente. Conséquence constatée : le retraitement de `DeS37izE5lk` a **refait toute l'OCR (1 170 s)** au lieu de la réutiliser, contrairement à ce que j'avais annoncé. Normaliser les nombres dans l'empreinte changerait **toutes** les empreintes et forcerait le recalcul de tous les résultats existants : non fait.

**Limites de ce contrôle** : planches d'images regardées pour les 9 écartements initiaux, 3 vidéos à peu de segments, les 2 vidéos retraitées et, plus tôt, 2 vidéos de la première série. **Les planches des autres vidéos traitées de ce lot n'ont pas été regardées**, et la qualité linguistique n'a pas été mesurée (aucun locuteur du chinois).

**D. Tests** : suite complète, hors ligne (`HF_HUB_OFFLINE=1`), avec le code final : **82 réussis sur 82** en 4 min 43 s (journal `data/logs/pytest_full.txt`, non versionné). Elle couvre notamment un test de non-régression du bug d'état décrit ci-dessus. **Non couvert par les tests automatiques** : le vrai site de Gemini et la qualité des traductions, vérifiés seulement à la main.

## 7. Définition du « terminé » (spec §12)

| Critère | État |
|---|---|
| S'exécute dans `video_ocr` | ✅ |
| Environnement recréable depuis les fichiers | ✅ (§2) |
| Vidéo locale à sous-titres traditionnels traitée de bout en bout | ✅ synthétique et 10 vidéos réelles |
| Chinois extrait avec horodatages | ✅ |
| Traduction sans API payante | ✅ Gemini en mode invité via navigateur (en ligne, gratuit, sans clé) ; moteurs locaux Qwen3-4B, NLLB, Argos hors ligne en option. La spec d'origine demandait un traitement 100 % local : écart décidé par l'utilisateur le 2026-10-23 |
| Vidéo exportée avec chinois et français simultanés | ✅ (inspecté) |
| Français synchronisé et lisible | ✅ synthétique ; réel : images fixes inspectées, lecture continue non vérifiée |
| Source inchangée | ✅ |
| Lot de plusieurs vidéos, une erreur ne bloque pas le lot | ✅ |
| SRT, JSON, rapports valides | ✅ |
| Tests exécutés et documentés | ✅ |
| Instructions d'installation et de lancement vérifiées | ✅ partiellement (étapes exécutées une à une ; `install.ps1` non lancé d'un bloc) |
| **Validation sur vidéos Instagram réelles** | ✅ exécutée (§6) ; qualité linguistique non mesurée, défauts consignés |

### 6.7 Révision de la règle de la sonde après le lot de 30 (2026-10-23)

Décision de l'utilisateur (option A) : **retirer le critère « lignes longues »**, ne garder que le seuil clair de 15 % d'images « type sous-titre ». Les champs `ocr.no_subtitle_sample_ratio` et `ocr.no_subtitle_long_line_cjk` sont supprimés.

- **Revalidation hors ligne** (sonde réelle sur 33 vidéos, indicateurs dans `data/logs/probe_all.json`, non versionné) : 
  - **0 vidéo à sous-titres écartée** (minimum observé 21 %, `Dea_JItj1r9`) ; `Del8z_ziYQH` (29 %) n'est plus écartée.
  - Les **7 écartements justes sont conservés** (0 à 10 %).
  - **3 vlogs passent désormais la sonde** : `DeYtWIolGAa` (15 %, pile sur le seuil), `Devm500DwjZ` (20 %), `DetCsEFCqkB` (24 %). Ils ne sont plus écartés qu'après l'OCR complète, bien plus coûteuse : c'est le prix assumé de la décision. `DetCsEFCqkB` (24 %) est au même niveau que `DeAzmhqAThH` (24 %, à sous-titres) : aucun seuil ne les sépare.
- **Non traité ici** : `DeS37izE5lk` (écartée à tort par le critère *après* OCR) reste un problème distinct et non corrigé (§6.6). Pour ne rien recalculer : les réglages de la sonde sont exclus de l'empreinte de configuration, l'écart `8` / `8.0` est neutralisé, et `scripts/migrate_hashes.py` a réécrit les empreintes des résultats existants (vérifié : seules `DeS37izE5lk`, `DetCsEFCqkB` et `Devm500DwjZ` ont une étape à refaire, pour une vraie différence de configuration). Test ajouté dans `tests/test_pipeline.py`.
- **Réserve** : un seul compte Instagram, seuil choisi dans l'écart observé, pas de validation indépendante.
- **Tests** : `tests/test_no_subtitles.py` réécrit avec les valeurs réellement mesurées (19 tests réussis) ; suite complète : **85 réussis sur 85** en 6 min 9 s (hors ligne).
