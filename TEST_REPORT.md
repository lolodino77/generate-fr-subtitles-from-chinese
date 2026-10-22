# Rapport de tests — video_ocr

Date : 2026-10-22. Machine : Windows 11 Pro, Intel i7-10510U (4 cœurs / 8 threads, 1,8 GHz), 16 Go RAM, sans GPU utilisé.
Environnement : Conda `video_ocr` (Python 3.11.17, FFmpeg 9.0.2 conda-forge), créé pendant cette session ; aucun autre environnement n'a été modifié.

Légende : ✅ exécuté et réussi · ❌ exécuté et échoué · ⏸️ **non exécuté**.

---

## 0. Synthèse

| Élément | Statut |
|---|---|
| Suite automatisée (41 tests, hors ligne `HF_HUB_OFFLINE=1`) | ✅ 41/41 |
| Recréation de l'environnement depuis `environment.yml` + tests | ✅ 40/41 (1 échec attendu, voir §2) |
| Chaîne complète sur vidéos synthétiques (chinois traditionnel incrusté) | ✅ texte OCR exact 5/5, erreur temporelle max 0,067 s |
| Inspection visuelle des vidéos **exportées** (images extraites des MP4) | ✅ (2 défauts trouvés puis corrigés, §4) |
| Interface Streamlit (aperçu OCR, lancement, annulation, reprise, résultats) | ✅ testée dans le navigateur |
| **Test sur 10 vidéos du compte Instagram jinnyteochew_th** | ⏸️ **NON EXÉCUTÉ — fichiers vidéo nécessaires (§6)** |

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
- `scripts/install.ps1` : ⏸️ **pas exécuté de bout en bout** ; ses étapes (création, `pip install`, `download_models.py`, `check`) ont été exécutées séparément.
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

## 6. Test sur 10 vidéos Instagram — ⏸️ NON EXÉCUTÉ

**Ce test n'a pas été exécuté.**

- Le profil public est consultable (vérifié dans le navigateur, cookies optionnels refusés, sans connexion).
- Instagram ne propose pas de téléchargement des Reels d'autrui sur le web, et ses conditions d'utilisation interdisent la collecte automatisée (yt-dlp, extraction d'URL CDN). Je n'ai donc téléchargé aucune vidéo.

Observations faites en regardant 2 Reels dans le navigateur, et prises en compte dans la conception :

- Le chinois y est **simplifié** (ex. 没本事没关系), pas traditionnel.
- Il est suivi d'une ligne de prononciation teochew en thaï et d'une traduction thaïe.
- La langue parlée est le **teochew/thaï**, pas le cambodgien.
- La position des sous-titres varie : haut de l'image sur un Reel, tiers inférieur sur l'autre.

Les 10 Reels les plus récents listés sur le profil :

1. https://www.instagram.com/jinnyteochew_th/reel/DeyYW7qDQiZ/
2. https://www.instagram.com/jinnyteochew_th/reel/DewaCrmHFcM/
3. https://www.instagram.com/jinnyteochew_th/reel/Devm500DwjZ/
4. https://www.instagram.com/jinnyteochew_th/reel/Detr9vXCpnB/
5. https://www.instagram.com/jinnyteochew_th/reel/DetCsEFCqkB/
6. https://www.instagram.com/jinnyteochew_th/reel/Des3v1LDJIa/
7. https://www.instagram.com/jinnyteochew_th/reel/DermDTjgqrz/
8. https://www.instagram.com/jinnyteochew_th/reel/DerIojFALtk/
9. https://www.instagram.com/jinnyteochew_th/reel/Deql7rCjNsx/
10. https://www.instagram.com/jinnyteochew_th/reel/DeqaVjljIVb/

**Fichiers nécessaires** : les MP4 de ces Reels, obtenus par exemple via le bouton « Télécharger » de l'application mobile si le créateur l'autorise, ou auprès du créateur. À déposer dans `data/instagram/`. Le test se lancera ensuite avec :

```powershell
python -m video_ocr process data\instagram -o data\output_instagram
python -m video_ocr verify data\output_instagram
```

Il sera suivi d'une inspection des planches `verification_frames.png` et des vidéos, puis de corrections éventuelles.

## 7. Définition du « terminé » (spec §12)

| Critère | État |
|---|---|
| S'exécute dans `video_ocr` | ✅ |
| Environnement recréable depuis les fichiers | ✅ (§2) |
| Vidéo locale à sous-titres traditionnels traitée de bout en bout | ✅ (synthétique) ; ⏸️ vidéos réelles |
| Chinois extrait avec horodatages | ✅ |
| Traduction sans API payante | ✅ (Qwen3-4B, NLLB, Argos, hors ligne) |
| Vidéo exportée avec chinois et français simultanés | ✅ (inspecté) |
| Français synchronisé et lisible | ✅ synthétique ; ⏸️ réel |
| Source inchangée | ✅ |
| Lot de plusieurs vidéos, une erreur ne bloque pas le lot | ✅ |
| SRT, JSON, rapports valides | ✅ |
| Tests exécutés et documentés | ✅ |
| Instructions d'installation et de lancement vérifiées | ✅ partiellement (étapes exécutées une à une ; `install.ps1` non lancé d'un bloc) |
| **Validation sur vidéos Instagram réelles** | ⏸️ **en attente des fichiers** |
