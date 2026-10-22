## 1. Rôle et mission

Agis comme un ingénieur logiciel senior spécialisé en Python, traitement vidéo, OCR, NLP, traduction automatique et applications locales Windows.

Développe une application complète, robuste, testable et documentée permettant de :

1. Importer une ou plusieurs vidéos contenant des sous-titres chinois traditionnels (繁體中文) incrustés directement dans l'image.
2. Extraire automatiquement ces sous-titres grâce à l'OCR.
3. Identifier leurs périodes d'affichage et reconstruire des segments temporels.
4. Traduire les sous-titres en français à l'aide d'outils gratuits fonctionnant localement.
5. Générer de nouveaux fichiers vidéo affichant simultanément les sous-titres chinois originaux et leur traduction française.
6. Traiter automatiquement plusieurs vidéos successivement.
7. Exporter les fichiers de sous-titres, les traductions et un rapport de traitement.

**Le livrable principal est une vidéo directement visionnable avec les sous-titres chinois originaux et les traductions françaises affichés simultanément.**

Tu dois implémenter réellement l'application dans le dépôt de travail. Ne te contente pas de proposer une architecture, du pseudo-code ou des extraits isolés.

## 2. Contexte d'utilisation

L'utilisateur consulte des vidéos Instagram, notamment des Reels en cambodgien accompagnés de sous-titres chinois traditionnels incrustés dans l'image.

Les sous-titres automatiques français d'Instagram sont trop peu fiables. L'objectif est donc de créer une solution indépendante de cette fonctionnalité.

L'application doit exploiter en priorité le texte chinois déjà présent dans les vidéos, plutôt que de retranscrire systématiquement l'audio cambodgien.

Le flux principal est :

**Vidéo source → OCR chinois traditionnel → regroupement temporel → traduction française → incrustation bilingue → vidéo finale.**

La vidéo source contient déjà les sous-titres chinois. Ceux-ci doivent rester visibles dans le résultat final. Le français doit être ajouté simultanément, de préférence dans une zone distincte située sous les sous-titres chinois.

La reconnaissance vocale du cambodgien n'est pas nécessaire au fonctionnement principal. Elle peut être proposée comme extension facultative, sans devenir une dépendance obligatoire.

## 3. Contraintes impératives

### 3.1 Gratuité et traitement local

Utilise exclusivement des outils gratuits et des composants open source ou librement utilisables localement, sans facturation à l'usage.

Sont interdits :
- Les API payantes d'OCR, de traduction ou de génération vidéo.
- Les services cloud payants.
- Les clés API payantes ou obligatoires.
- Les abonnements nécessaires au fonctionnement.
- Les dépendances à un fournisseur dont l'utilisation normale entraîne une facturation.

Privilégie un traitement local pour préserver la confidentialité des vidéos.

Les modèles d'IA utilisés doivent pouvoir être téléchargés gratuitement et exécutés localement, si leur licence et leurs conditions d'utilisation le permettent.

Vérifie les licences des bibliothèques, des modèles et des dépendances externes. Documente les restrictions éventuelles.

Distingue clairement la gratuité, l'open source, la licence commerciale éventuelle et la nécessité d'une connexion Internet lors de l'installation.

### 3.2 Environnement technique

- Python comme langage principal.
- Windows 10/11.
- Fonctionnement sur CPU, sans GPU obligatoire.
- Interface accessible à un utilisateur non développeur.
- Dépendances limitées.
- Installation reproductible.
- Pas de Docker obligatoire.
- Aucun service cloud obligatoire.
- Environnement Conda isolé obligatoire.

### 3.3 Environnement Conda isolé — obligatoire

Toute l'application doit être développée, installée, testée et exécutée dans un environnement Conda dédié nommé `video_ocr`.

Exigences :

- Créer l'environnement Conda `video_ocr` s'il n'existe pas.
- Choisir une version de Python compatible avec toutes les dépendances retenues.
- Python 3.11 est une version candidate, mais la compatibilité réelle de PaddleOCR, PaddlePaddle, FFmpeg et des bibliothèques de traduction doit être vérifiée avant de la retenir.
- Ne jamais installer les dépendances du projet dans l'environnement Conda `base`, dans le Python système ou dans un autre environnement existant.
- Ne jamais modifier les autres environnements Conda de l'utilisateur.
- Si `video_ocr` existe déjà, inspecter son contenu et sa compatibilité avant de le réutiliser.
- Ne jamais supprimer ou recréer destructivement un environnement existant sans autorisation explicite.
- Utiliser `python -m pip` plutôt que `pip` seul.
- Vérifier que l'interpréteur Python et pip utilisés pointent vers `video_ocr`.
- Installer FFmpeg séparément si nécessaire et documenter son installation.
- Stocker les modèles OCR et de traduction dans un répertoire propre au projet ou dans un cache explicitement configuré.
- Éviter toute modification globale inutile du système.

Exemple de commandes PowerShell, à adapter à l'état réel de l'environnement :

```powershell
conda env list
conda create -n video_ocr python=3.11 -y
conda activate video_ocr

python -c "import sys; print(sys.executable)"
python -m pip --version
python -m pip check
```

Ne lance pas aveuglément la commande de création si l'environnement existe déjà. Inspecte d'abord son état.

Fournis obligatoirement :
- Un fichier `environment.yml`.
- Un fichier de dépendances avec des versions maîtrisées, si pertinent.
- Les commandes d'installation, de vérification et de lancement.
- Une procédure de mise à jour non destructive.
- Une vérification de la reproductibilité de l'installation.

Si une dépendance est incompatible avec l'environnement, diagnostique le problème avant toute modification. N'installe jamais arbitrairement des paquets dans `base` pour contourner une erreur.

### 3.4 Qualité logicielle

Le code doit respecter les principes suivants :

- Architecture modulaire.
- Fonctions courtes, typées et documentées.
- Gestion explicite des erreurs.
- Logs exploitables.
- Tests automatisés.
- Configuration centralisée.
- Traitement par lots.
- Reprise après interruption lorsque cela est pertinent.
- Absence de fichiers monolithiques.
- Aucun secret ni identifiant sensible dans le code.
- Aucun résultat déclaré comme testé si le test n'a pas réellement été exécuté.

## 4. Architecture technique

Compare brièvement les solutions gratuites disponibles avant de sélectionner les composants définitifs.

Privilégie les outils suivants, sous réserve de vérifier leur compatibilité, leurs licences et leurs performances réelles.

### Traitement vidéo

- FFmpeg : extraction des images, inspection des flux, génération des vidéos finales et incrustation des sous-titres.
- OpenCV, uniquement si nécessaire, pour le prétraitement d'images ou certaines opérations de détection.

### OCR

- PaddleOCR ou un moteur OCR open source équivalent prenant réellement en charge le chinois traditionnel.
- OpenCC si nécessaire pour les conversions ou normalisations de texte.

Le texte original reconnu doit toujours être conservé. Toute normalisation doit produire une version distincte.

### Traduction

- Argos Translate ou un moteur de traduction local open source équivalent.
- Si la traduction directe chinois traditionnel → français n'est pas disponible, étudier une langue intermédiaire ou un modèle multilingue local.
- Ne pas supposer qu'un moteur gratuit prend en charge la paire de langues requise sans l'avoir vérifié.

### Interface

- Streamlit pour une interface web locale, sauf si une solution desktop plus simple est objectivement préférable.

Aucune clé API ou aucun compte externe ne doit être nécessaire au fonctionnement principal.

## 5. Fonctionnalités requises

### 5.1 Import des vidéos

L'utilisateur doit pouvoir :

- Sélectionner une vidéo locale.
- Sélectionner un dossier contenant plusieurs vidéos.
- Traiter un lot de vidéos successivement.
- Choisir le dossier de sortie.
- Relancer un traitement interrompu.

Formats attendus : MP4, MOV et MKV, selon les capacités de FFmpeg.

L'import depuis des URLs Instagram peut être ajouté en option si une méthode gratuite, techniquement viable et conforme aux conditions applicables est disponible.

Cette fonctionnalité doit rester séparée du traitement vidéo principal. L'application doit fonctionner intégralement sur des fichiers locaux, même si Instagram modifie ses mécanismes d'accès.

Ne contourne pas les restrictions d'accès, les mécanismes d'authentification ou les protections techniques.

### 5.2 Échantillonnage des images

Ne traite pas systématiquement chaque image de la vidéo si cela n'est pas nécessaire.

Implémente un échantillonnage temporel configurable, par exemple une image toutes les 0,5 à 2 secondes.

Le système doit :

- Permettre de modifier la fréquence d'échantillonnage.
- Détecter les changements de texte.
- Éviter de retraiter les images identiques ou quasi identiques.
- Préserver les horodatages d'origine.
- Gérer les sous-titres qui apparaissent, disparaissent ou changent rapidement.
- Éviter de manquer systématiquement les phrases courtes.

Prévois une stratégie pour améliorer l'échantillonnage lorsque les changements de texte sont fréquents.

### 5.3 OCR du chinois traditionnel

L'application doit :

- Détecter les zones de texte.
- Reconnaître le chinois traditionnel (繁體中文).
- Préserver les caractères et la ponctuation reconnus.
- Conserver la position des zones de texte dans l'image.
- Fournir un score de confiance si le moteur le permet.
- Gérer les sous-titres sur plusieurs lignes.
- Éviter de créer un nouveau segment à chaque image lorsque le texte n'a pas changé.
- Signaler les caractères ou segments incertains.

Les sous-titres doivent être distingués autant que possible des autres textes visibles dans la vidéo.

Prévois une région d'intérêt (ROI) configurable pour limiter l'OCR à une zone particulière de l'image.

Permets à l'utilisateur de prévisualiser les détections OCR sur quelques images avant de lancer le traitement complet.

Conserve au minimum :
- Le texte OCR brut.
- Le texte éventuellement normalisé.
- Les coordonnées de la zone de texte.
- L'horodatage de l'image.
- Le score de confiance disponible.

### 5.4 Regroupement temporel et déduplication

Une phrase reste souvent affichée sur plusieurs images successives. L'application doit regrouper ces observations en un seul segment.

Implémente une logique permettant :

- De regrouper les détections identiques ou presque identiques.
- De déterminer les débuts et fins d'affichage estimés.
- De préserver l'ordre chronologique.
- De distinguer les phrases différentes.
- D'éviter les doublons.
- De conserver les informations nécessaires pour diagnostiquer les erreurs.

Les seuils de similarité et les paramètres temporels doivent être configurables.

La précision des horodatages dépendra de la fréquence d'échantillonnage. Documente cette limite et n'affirme pas que les temps sont exacts à l'image près si ce n'est pas vérifié.

### 5.5 Traduction française locale

Traduis les segments chinois en français avec un moteur gratuit fonctionnant localement.

Exigences :

- Préserver le texte chinois original.
- Produire une traduction française naturelle.
- Exploiter le contexte des segments voisins lorsque cela est possible.
- Conserver la correspondance entre chaque segment chinois et sa traduction.
- Mettre en cache les traductions pour éviter les calculs inutiles.
- Gérer les erreurs sans interrompre tout le lot.
- Signaler les traductions manquantes ou incertaines.
- Ne pas remplacer silencieusement les traductions impossibles par des chaînes vides.

La traduction doit fonctionner sans API payante et, après installation et téléchargement des modèles, sans connexion Internet.

Si aucun moteur local gratuit ne donne de résultats satisfaisants, documente les alternatives et leurs compromis avant de choisir une solution.

### 5.6 Génération de vidéos bilingues — fonctionnalité principale obligatoire

**L'application doit produire une nouvelle vidéo dans laquelle les sous-titres chinois traditionnels originaux restent visibles et sont accompagnés simultanément de leur traduction française.**

Il ne suffit pas de générer deux fichiers SRT distincts. La vidéo finale bilingue est un livrable obligatoire.

#### Principe visuel

La vidéo source contient déjà les sous-titres chinois incrustés dans les pixels de l'image.

L'application doit conserver ces sous-titres chinois et ajouter le français dans une zone distincte.

Disposition par défaut souhaitée :

- Ligne supérieure : sous-titres chinois traditionnels originaux, conservés tels qu'ils apparaissent dans la vidéo.
- Ligne inférieure : traduction française correspondante, ajoutée par l'application.

Le rendu doit permettre de lire simultanément les deux langues pendant le visionnage.

#### Préservation des sous-titres chinois

Ne supprime pas, ne masque pas et ne remplace pas les sous-titres chinois originaux.

Puisqu'ils sont incrustés dans l'image, ils ne peuvent pas être déplacés ou modifiés comme un fichier SRT indépendant.

Par conséquent :

- Conserve l'image d'origine.
- Ajoute uniquement les sous-titres français.
- Identifie la position des sous-titres chinois grâce aux coordonnées de l'OCR ou à une zone configurable.
- Place le français sous les caractères chinois si une zone suffisamment libre existe.
- Si le français risque de masquer le chinois ou une information importante, propose une stratégie de repli.

#### Stratégies de placement

Implémente au minimum deux stratégies de rendu.

**Stratégie A — Incrustation dans l'image originale**

Ajouter le français dans une zone libre de l'image, idéalement juste sous le chinois.

Avantages :
- Résolution et dimensions originales conservées.
- Fichier final plus proche de la source.
- Pas de modification du cadrage.

Limites :
- L'espace disponible peut être insuffisant.
- La position des sous-titres chinois peut varier.
- Le français peut masquer une partie du contenu si le placement est incorrect.

**Stratégie B — Ajout d'une bande de sous-titres**

Ajouter une bande dédiée en bas de la vidéo, lorsque la stratégie A ne permet pas une lecture confortable.

La vidéo originale est conservée dans son intégralité et une bande supplémentaire affiche les traductions françaises.

Cette stratégie peut modifier les dimensions de sortie. Documente les compromis et préserve le ratio d'image de la vidéo originale dans sa zone de contenu.

Pour les Reels verticaux, évite autant que possible de produire un résultat excessivement haut ou mal adapté à un écran de téléphone.

#### Lisibilité

Permets de configurer :

- La taille de police.
- La couleur du texte français.
- Le contour du texte.
- Le fond opaque ou semi-transparent.
- Les marges.
- La position verticale.
- L'espacement des lignes.
- La hauteur éventuelle de la bande supplémentaire.

Prévois des paramètres par défaut adaptés aux vidéos verticales.

Le texte français doit rester lisible sur des arrière-plans clairs ou sombres.

La police choisie doit prendre en charge les accents français. Le système doit gérer correctement les chemins de polices Windows et les caractères Unicode.

#### Synchronisation

Les traductions françaises doivent correspondre aux segments chinois identifiés par l'OCR.

- Réutilise les horodatages calculés précédemment.
- Affiche la traduction pendant la période d'affichage correspondante.
- Gère les changements de phrase et les segments courts.
- Évite les chevauchements entre traductions successives.
- Signale les segments dont la synchronisation est incertaine.
- Ne modifie pas inutilement la durée de la vidéo originale.

Si le texte chinois reste affiché pendant plusieurs secondes, la traduction française correspondante doit rester visible pendant la même période.

#### Implémentation technique

Utilise FFmpeg pour produire la vidéo finale.

Privilégie une solution compatible avec Windows et avec les caractères Unicode.

Vérifie :
- La compatibilité des filtres FFmpeg.
- Le rendu des accents français.
- Les chemins de fichiers et de polices sous Windows.
- La synchronisation audio-vidéo.
- La conservation de la fréquence d'images.
- Le maintien de la résolution lorsque la stratégie A est utilisée.

N'effectue pas plusieurs réencodages inutiles.

Utilise un encodage vidéo et audio adapté à une lecture courante sur PC et smartphone. Documente les compromis entre vitesse, taille de fichier et qualité.

Le fichier source doit toujours rester intact.

#### Aperçu et validation

Avant ou après l'export, affiche un aperçu du rendu bilingue.

Permets à l'utilisateur de vérifier que :

- Les sous-titres chinois sont toujours présents.
- Le français est visible simultanément.
- Les deux langues correspondent aux mêmes passages.
- Le français ne masque pas inutilement le chinois.
- Le texte est lisible sur les vidéos verticales.

L'aperçu ne remplace pas le test du fichier réellement exporté.

#### Résultat par vidéo

Pour chaque vidéo traitée, génère :

1. La vidéo source inchangée.
2. Une nouvelle vidéo avec les sous-titres chinois originaux et les traductions françaises affichés simultanément.
3. Un fichier SRT chinois.
4. Un fichier SRT français.
5. Un fichier JSON contenant les segments, les textes, les traductions, les horodatages et les informations de confiance disponibles.
6. Un fichier TXT ou Markdown présentant les phrases chinoises et françaises côte à côte.
7. Un rapport sur les éventuelles erreurs OCR, les traductions manquantes et les incertitudes de synchronisation.

La génération des vidéos bilingues doit fonctionner sur un lot entier, sans intervention manuelle entre les vidéos.

### 5.7 Interface utilisateur

L'interface doit proposer :

- La sélection d'une ou plusieurs vidéos.
- La sélection d'un dossier source.
- Le choix du dossier de sortie.
- Le réglage de la fréquence d'échantillonnage.
- La configuration de la région OCR.
- Le choix de la stratégie de placement du français.
- Le réglage de la police et du style des sous-titres français.
- Le lancement, l'annulation et la reprise des traitements.
- La progression globale et par vidéo.
- L'affichage des erreurs et avertissements.
- Un aperçu des segments OCR.
- Un aperçu des traductions.
- Un aperçu du rendu bilingue.
- L'ouverture du dossier contenant les résultats.

L'interface ne doit pas bloquer pendant le traitement. Les opérations longues doivent être exécutées dans des tâches adaptées à l'architecture retenue.

Une vidéo en échec ne doit pas empêcher les autres vidéos du lot de continuer à être traitées.

### 5.8 Traitement par lots et reprise

Pour les lots importants :

- Conserve un état de traitement par vidéo.
- Permets de reprendre les vidéos inachevées.
- Évite de retraiter une vidéo si son contenu et ses paramètres n'ont pas changé.
- Enregistre les paramètres utilisés.
- Distingue les résultats complets, partiels et échoués.
- Génère un rapport récapitulatif du lot.

La reprise doit être fiable sans introduire un système complexe disproportionné.

## 6. Performance et optimisation

L'application doit fonctionner sur un PC Windows courant sans GPU dédié.

Optimise en priorité :

- Le nombre d'images traitées.
- La réutilisation des résultats OCR.
- La déduplication avant traduction.
- Le cache des traductions.
- Le traitement séquentiel ou parallèle selon les performances mesurées.
- La génération des vidéos sans réencodage inutile.

Mesure les performances sur un petit jeu de vidéos et indique les limites observées.

Documente :
- Le temps de traitement par minute de vidéo.
- La mémoire vive nécessaire.
- L'espace disque nécessaire pour les modèles.
- Le temps d'export des vidéos bilingues.
- Les effets de la résolution et de la fréquence d'échantillonnage.
- Les limites de la traduction locale sur CPU.

Ne garantis aucun débit sans mesure réelle.

## 7. Tests et critères d'acceptation

Crée des tests unitaires et d'intégration couvrant :

- L'extraction des images.
- L'OCR du chinois traditionnel.
- La déduplication.
- Les horodatages.
- La traduction.
- La génération des SRT.
- La génération du JSON et du rapport.
- La génération d'une vidéo bilingue.
- La conservation du fichier source.
- Le maintien de la synchronisation audio-vidéo.
- Le traitement par lots.
- Les fichiers invalides.
- Les erreurs d'OCR ou de traduction.
- L'annulation et la reprise.
- L'encodage des caractères chinois et français.
- La configuration de l'environnement Conda.

Prévois un jeu de test comprenant des caractères chinois traditionnels qui diffèrent du chinois simplifié.

Les tests doivent distinguer :
- La réussite technique de l'OCR.
- La qualité linguistique de la traduction.
- La qualité du placement visuel.
- La synchronisation.
- La validité des fichiers exportés.

### Critères mesurables

Définis et mesure, lorsque cela est possible :

- La proportion de sous-titres correctement détectés.
- L'exactitude du texte OCR.
- L'erreur temporelle des segments.
- Le taux d'échec de traduction.
- La proportion de traductions manquantes.
- Le temps de traitement par minute de vidéo.
- Le temps d'export.
- La validité de la vidéo finale.

### Test visuel obligatoire

Sur une vidéo réelle de test :

1. Exécute l'OCR.
2. Génère la traduction française.
3. Exporte la vidéo bilingue.
4. Ouvre ou inspecte le fichier final.
5. Vérifie que le chinois original est toujours visible.
6. Vérifie que le français est visible simultanément.
7. Vérifie que les traductions correspondent aux bons segments.
8. Vérifie qu'aucun problème majeur de police, d'encodage ou de placement ne rend le résultat illisible.

Ne considère pas la fonctionnalité comme validée sur la seule base de l'existence d'un fichier vidéo. Inspecte effectivement le rendu exporté.

N'affirme pas que les tests garantissent la qualité de toutes les vidéos Instagram.

Les tests unitaires doivent pouvoir s'exécuter sans connexion Internet. Sépare-les des tests nécessitant des modèles téléchargés.

## 8. Organisation du code

Propose une architecture simple, par exemple :

- `src/video_ocr/ingestion/` : import des vidéos.
- `src/video_ocr/video/` : extraction et échantillonnage des images.
- `src/video_ocr/ocr/` : reconnaissance des sous-titres.
- `src/video_ocr/segments/` : regroupement et déduplication.
- `src/video_ocr/translation/` : traduction locale et cache.
- `src/video_ocr/subtitles/` : génération et synchronisation des SRT.
- `src/video_ocr/rendering/` : incrustation française et génération des vidéos bilingues.
- `src/video_ocr/export/` : génération des fichiers de sortie et rapports.
- `src/video_ocr/ui/` : interface utilisateur.
- `tests/` : tests unitaires et d'intégration.
- `config/` : configuration.
- `data/` : données temporaires et résultats.
- `scripts/` : installation et lancement.
- `environment.yml` : environnement Conda.
- `README.md` : documentation complète.

Adapte cette structure si une solution plus simple est justifiée. Évite la multiplication inutile des fichiers.

## 9. Installation et documentation

Fournis :

- Un README en français.
- Un fichier `environment.yml`.
- Un fichier de dépendances avec des versions maîtrisées, si pertinent.
- Des instructions exactes pour Windows PowerShell.
- Un script d'installation.
- Un script de lancement.
- Les instructions de téléchargement des modèles.
- Les instructions de fonctionnement hors ligne après installation.
- Les licences des composants.
- Les limites connues.
- Les solutions aux erreurs fréquentes.

### 9.1 Procédure Conda

Documente les commandes permettant de :

1. Vérifier Conda.
2. Inspecter les environnements existants.
3. Créer `video_ocr` si nécessaire.
4. Activer l'environnement.
5. Vérifier l'interpréteur et pip.
6. Installer les dépendances.
7. Télécharger les modèles.
8. Vérifier les imports et les versions.
9. Exécuter les tests.
10. Lancer l'application.

Exemple :

```powershell
conda env list
conda activate video_ocr

python -c "import sys; print(sys.executable)"
python -m pip --version
python -m pip check
```

Si l'environnement n'existe pas, crée-le avec la version de Python validée pour les dépendances. Si l'environnement existe, inspecte-le avant toute modification.

Ne supprime pas automatiquement un environnement existant et ne modifie jamais les autres environnements Conda de l'utilisateur.

### 9.2 Fonctionnement hors ligne

Après installation et téléchargement initial des modèles :

- L'OCR doit pouvoir fonctionner sans Internet.
- La traduction doit pouvoir fonctionner sans Internet.
- Le traitement des vidéos locales doit fonctionner sans compte externe.
- La génération des vidéos bilingues doit fonctionner sans service cloud.

Si un composant nécessite encore Internet, indique-le explicitement.

## 10. Méthode de travail de l'agent

Travaille de manière incrémentale.

1. Inspecte le dépôt et l'environnement disponibles.
2. Vérifie Conda et l'état de l'environnement `video_ocr`.
3. Vérifie les licences et la compatibilité des outils envisagés.
4. Présente brièvement les choix techniques et les principaux risques.
5. Implémente un premier flux fonctionnel sur une vidéo locale.
6. Valide l'OCR du chinois traditionnel.
7. Valide une traduction française locale et gratuite.
8. Génère une première vidéo bilingue et inspecte son rendu.
9. Corrige les problèmes de synchronisation, de police et de placement.
10. Ajoute le traitement par lots.
11. Ajoute l'interface.
12. Ajoute les tests, la documentation et les scripts d'installation.
13. Exécute les tests dans l'environnement Conda dédié.
14. Vérifie que l'installation peut être reproduite.
15. Termine par un bilan factuel des fonctionnalités opérationnelles, des limites et des commandes de lancement.

Ne t'arrête pas à un plan théorique. Implémente, teste et corrige le projet dans le dépôt existant.

Si une fonctionnalité ne peut pas être réalisée de manière fiable avec des outils gratuits, explique précisément pourquoi et propose la meilleure solution de repli sans introduire de dépendance payante.

Ne déclare jamais un test réussi sans l'avoir exécuté. Distingue clairement les tests réussis, échoués et non exécutés.

## 11. Priorités de livraison

Ordre de priorité :

1. OCR fiable du chinois traditionnel.
2. Regroupement et horodatages corrects.
3. Traduction française locale et gratuite.
4. **Génération effective d'une vidéo avec chinois original et français visibles simultanément.**
5. Qualité visuelle, lisibilité et synchronisation.
6. Traitement de plusieurs vidéos.
7. Interface simple.
8. Exports SRT, JSON et rapport global.
9. Reprise des traitements.
10. Récupération facultative des vidéos depuis des URLs.

La priorité est un outil réellement utilisable, local, gratuit et maintenable, pas une démonstration technique surdimensionnée.

## 12. Définition du « terminé »

Le projet est considéré comme terminé uniquement si :

- L'application s'exécute dans l'environnement Conda `video_ocr`.
- L'environnement peut être recréé à partir des fichiers fournis.
- Une vidéo locale contenant des sous-titres chinois traditionnels est traitée de bout en bout.
- Le texte chinois est extrait avec des horodatages.
- La traduction française est produite sans API payante.
- Une vidéo exportée affiche simultanément le chinois original et le français.
- Le français est correctement synchronisé et lisible.
- La vidéo source demeure inchangée.
- Le traitement de plusieurs vidéos fonctionne.
- Une erreur sur une vidéo ne bloque pas tout le lot.
- Les fichiers SRT, JSON et les rapports sont valides.
- Les tests automatisés ont été exécutés et leurs résultats documentés.
- Les instructions d'installation et de lancement ont été vérifiées.

Si un critère n'est pas satisfait, indique explicitement ce qui manque, pourquoi et quelle action est nécessaire pour le satisfaire.