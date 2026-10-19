# LEARNINGS — Décisions & Apprentissages PFE

Ce fichier trace les **décisions clés**, **apprentissages** et **changements** pour faciliter la rédaction du PFE à la fin.

---

## 📌 Décisions Clés

### 1. Inputs vs Outputs (12 oct 2026)

**Décision** : Le **nombre d'antennes N'EST PAS un input utilisateur** — c'est un OUTPUT généré par l'outil.

**Contexte** :
- Charles & Nicolas ont clarifié que les antennes, RRH, BBU sont calculés par l'outil
- L'utilisateur entre les **paramètres de son bâtiment** (surfaces, niveaux, cloisonnement)
- L'outil **prédit** la composition de l'infrastructure

**Impact** :
- Simplification de l'UX (moins d'inputs à saisir)
- L'outil devient plus **orienté métier** (le chiffrage décide de la config)
- Données d'entraînement : liaison entre (surfaces, niveaux, cloisonnement) → (nb antennes, coûts)

**Statut** : ✅ Validé par Olivier, Nicolas

---

### 2. Type de DAS = Output (12 oct 2026)

**Décision** : L'outil doit sortir **des estimatifs pour CHAQUE type de DAS** (passif, actif, hybride).

**Contexte** :
- Nicolas : "Le choix du DAS ne doit pas être un input. L'outil doit proposer les trois solutions."
- Permet au client de **comparer** : équipements, coûts, complexité
- Chaque type de DAS a sa propre BoM

**Impact** :
- L'interface affiche **3 solutions en parallèle**
- Les modèles ML doivent pouvoir prédire pour chaque scénario
- Dataset d'entraînement doit inclure la solution DAS utilisée

**Statut** : ✅ Validé

---

### 3. Indicateurs de Confiance (12 oct 2026)

**Décision** : Afficher un **score de confiance** + **liste des études similaires** retrouvées.

**Contexte** :
- Nicolas : "Bien vu ! On ne l'avait pas évoqué au départ."
- Validation implicite : si l'outil retrouve des cas similaires, la prédiction est + fiable
- k-NN va naturellement générer cette liste

**Impact** :
- k-NN fournit les N études les plus proches
- Afficher : "La prédiction s'appuie sur X études similaires"
- Confiance = f(distance, volume données, variance prédictions)

**Statut** : ✅ À implémenter dans Phase 3

---

### 4. Gestion du Catalogue Équipementiers (12 oct 2026)

**Décision** : Interface simple pour **ajouter / supprimer / mettre à jour** les équipements et constructeurs.

**Contexte** :
- Nicolas : "L'interface doit permettre d'alimenter facilement la base d'équipement."
- Le catalogue évolue : nouveaux équipements, tarifs changent, fournisseurs disparaissent
- Besoin d'une base de données versionnable

**Impact** :
- Table "Equipements" : modèle, constructeur, coûts, caractéristiques
- CRUD simple dans le backend (+ validation)
- Possibilité d'importer/exporter le catalogue

**Statut** : ⏳ À détailler après audit dataset

---

## 💡 Apprentissages

### Apprentissage 1 : Importance de l'État de l'Art

**Date** : 09 oct 2026  
**Constat** : Charles a signalé que l'état de l'art manquait au CDC.

**Points clés** :
- Il y a probablement d'autres outils / approches déjà existantes
- Besoin de poser la question : "Pourquoi cette approche ML plutôt qu'une autre ?"
- L'innovation attendue : plans 3D/2D, calcul automatique surfaces

**Action** : À inclure dans la rédaction du PFE (chapitre État de l'art)

---

### Apprentissage 2 : Données Géographiques Existent

**Date** : 09 oct 2026  
**Constat** : Olivier a mentionné une **base géographique 3D du gouvernement** (+ précise qu'OSM).

**Points clés** :
- France a une base 3D publique disponible
- À privilégier pour les bâtiments existants
- Fallback sur plans 2D pour nouvelles constructions

**Action** : À explorer Phase 2 (optionnel si temps)

---

### Apprentissage 3 : Cloisonnement = Paramètre Clé

**Date** : 09 oct 2026  
**Constat** : Nicolas a insisté sur l'**indice de cloisonnement** comme input.

**Points clés** :
- Les matériaux du bâtiment impactent fortement l'atténuation radio
- Catégories : semi-ouvert, léger, moyen, dense, très dense
- À spécifier par niveau ?

**Action** : À valider lors du questionnaire audit

---

### Apprentissage 4 : Extraction iBwave & Identification Type DAS (12 oct 2026)

**Date** : 12 oct 2026  
**Constat** : Workflow standardisé + heuristiques d'identification DAS + contraintes opérateurs.

**Points clés** :

**Format livrables** :
- PDF rapport ELR + Excel iBwave (pour faciliter après Yoann)
- JPEG : plans étages, designs, simulations RSRP
- Fichiers `.ibw` : iBwave natifs (contiennent la surface)

**Paramètres à extraire/documenter** :
- Surface : Depuis fichiers `.ibw` (⏳ procédure extraction à déterminer)
- Étages : Max ~10 étages observés
- Configurations par étage : Open space, dense, autres variants
- Fréquence : Basse (portée) vs Haute (débit)
- MIMO : Activé oui/non
- Technos : 4G vs 5G (mix possible)
- Opérateur(s) : Avec contraintes spéciales

**Contraintes opérateurs** :
- Bouygues Télécom : ❌ Pas de répéteurs / atténuateurs (critère sélection)
- À documenter pour chaque étude

**Type DAS — Identification** :
- ELR ne mentionne PAS le type DAS → À déduire des designs
- Heuristiques :
  - RosenBerger ou SoliD → Actif OU Hybride
  - Fibre end-to-end → Actif
  - Coupleurs / Splitters → Passif OU Hybride
- Déduction : Lire schémas connecteurs

**Complexité conception par type** :
- DAS Passif : Difficile (équilibrage puissance, pertes coax, position baies opérateur complexe selon étage/pièce)
- DAS Actif/Hybride : Simplifié (fibre)

**Action** :
- Phase 2 : Parser `.ibw` pour surface + équipementiers + opérateurs
- À clarifier : Extraction surface (manuel vs auto ?) + procédure Amina

---

### Apprentissage 5 : Contraintes Équipementiers & Topologie Bâtiment (13 oct 2026)

**Date** : 13 oct 2026  
**Constat** : Yanis a clarifié contraintes équipementiers + impact topologie bâtiment sur dimensionnement.

**Points clés** :

**Contraintes équipementiers** :
- SoliD : limité en puissance si plusieurs opérateurs, voir techno
- RosenBerger : typiquement Actif/Hybride, NON accepté par Bouygues Télécom
- SoliD : souvent retrouvé en Actif/Hybride
- Bouygues Télécom : accepte Actif mais pas avec des équipements RosenBerger
- Type DAS restreint choix équipementiers disponibles

**Surface & Topologie : Impact sur Routing Câbles** :
- **Open space sans étages** : Raccordement horizontal long → pertes coax élevées si DAS passif
- **Multi-étages** : Possibilité passer câbles verticalement (plafond/toit) → raccordement + court → moins de pertes
- **Contraintes structure** : Béton (faut contourner) vs béton armé (peut percer) → affecte routing possible
- **Impact** : Type DAS possible, nb antennes, placement baies, coûts équipements
- ⏳ À documenter : structure bâtiment (matériaux) + possibilités de routing (vertical vs horizontal)

**Localisation baie opérateur** :
- Position baie (zone technique) impacte raccordement principal
- Passage câbles entre étages (ex. via toit en passif) → affecte pertes coax
- Routing câbles → nb/type antennes à dimensionner

**Type DAS & architecture réseau** :
- **Passif** : moins de pertes si raccordement coax optimisé (routing toit/étages)
- **Actif/Hybride** : nécessite "master" de combinaison/relais (équipement spécifique)
  - SoliD fréquent en Actif/Hybride
  - Équipements spécifiques selon config

**Action** :
- Phase 2 : Parser localisation baie + routing câbles depuis designs
- À documenter : surface en hauteur vs surface en largeur (2 paramètres distincts)
- Raffiner heuristiques DAS selon contraintes équipementiers + opérateur

---

### Apprentissage 6 : Sources de Données & Contexte Métier (13 oct 2026)

**Date** : 13 oct 2026  
**Constat** : Nicolas a clarifié sources de données, timeline études, et business model devis.

**Points clés** :

**Dataset & Timeline** :
- ✅ Exploiter études Indoor après 2023 (Amina a couvert avant)
- ✅ Sous-traitants peuvent faire études → OK si mêmes livrables format
- ✅ Docs disponibles SharePoint (Eiffage)

**APS (Avant Projet Sommaire)** :
- Particularité début 2025 : demandes APS commencent
- Contenu : résumé conception + études de mesure (si faites) + choix config détaillé
- Timing : avant signature contrat client (si intéressé)

**Sources Infos Complémentaires** :
- **Livrables finaux** : complets pour etre livrés, mais certaines infos parfois non renseignées dedans
  - Solution : retourner sur **tickets clients** pour extraire infos manquantes
- **Fichiers `.ibwave` natifs** : ouvrir avec logiciel iBwave pour extraire infos (ex. surface si pas renseignée dans extraits)
- **Excel exemple Nicolas** : référence de structure / où chercher les infos (pas format exact)
- Infos clés à récupérer : multi-op vs mono-op, bandes fréq, choix tech, surface, etc.

**Business Model Devis** :
- **Opérateur demande** (ex. Bouygues) : Eiffage devis SANS certains équipements (ex. SoliD)
- Opérateur fait devis AVEC ces équipements + marge → transfert client
- **Contact direct client** : réseaux privés non-opérés (hôtels, industrie 5G privée)
- Devis approximatif par conception

**Action** :
- ✅ Utiliser devis Eiffage "habituels" comme référence
- ✅ **À valider avec Yoann** : quelles infos devis sont critiques pour le ML, comment les exploiter
- ✅ À voir Yoann : comment raffiner chiffrage exact + validation approche
- ⏳ Retrouver documents Excel exemple (Nicolas) + comprendre structure infos tickets clients

---

### Apprentissage 7 : IGN Data Extractor (14 oct 2026)

**Date** : 14 oct 2026  
**Constat** : Données publiques IGN exploitables via Overpass API pour extraire surfaces/types/hauteurs.

**Points clés** :
- BD TOPO : couverture nationale, format vecteur (WFS)
- LiDAR HD : déploiement national en cours
- Overpass API : accès facile, pas de clé API requise
- Fichiers PDF/CAO/DWG : exploitable mais semi-manuel (à voir après)

**Action** : Module Python créé (`src/ign_extractor.py`), à tester sur études réelles

---

### Apprentissage 8 : IGN Data Extractor (15 oct 2026)

## Phase 2 : BD TOPO et LiDAR HD

### Notions
- **WFS** : service qui renvoie des données vectorielles (ici les contours des bâtiments BD TOPO) en JSON.
- **WMS** : service qui renvoie une image. Ici, `image/geotiff` permet de récupérer les valeurs de hauteur du MNH pour une emprise donnée.
- **MNT / MNS / MNH** : modèle de terrain (sol nu), modèle de surface (toits et arbres compris), et modèle de hauteur (MNS − MNT = hauteur au-dessus du sol).
- **Lambert 93 (EPSG:2154)** : projection en mètres pour la France métropolitaine. On l'utilise pour les surfaces et les distances, à la place du GPS (EPSG:4326).
- **Pixel LiDAR** : carré de 0,5 m × 0,5 m, soit 0,25 m². Nombre de pixels × 0,25 = surface couverte.
- **Nodata (-9999)** : valeur conventionnelle des nœuds sans donnée, à ignorer.
- **Médiane et percentiles** : plus robustes que le max pour résumer une hauteur hétérogène.

### Pièges rencontrés
- L'ordre des axes compte : bbox en `lon,lat` pour le WFS en EPSG:4326 ; `x,y` (est, nord) pour le WMS en EPSG:2154.
- Une URL devinée ne fonctionne pas : prendre les URL dans la documentation officielle (descriptif de contenu LiDAR HD).
- Nominatim prend le premier résultat : vérifier l'adresse trouvée.
- La surface au sol n'est pas la surface de plancher.

### Ressources
- Descriptif de contenu LiDAR HD (IGN), section 3 « Modèles numériques » et section 3.3 « Accès aux données ».
- Service WMS de la Géoplateforme : `https://data.geopf.fr/wms-r/ows?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities`
- Service WFS de la Géoplateforme : `https://data.geopf.fr/wfs/ows`
- Téléchargement des MNx LiDAR HD : https://cartes.gouv.fr/telechargement/IGNF_MNH-LIDAR-HD
- Norme WMS (OGC) : https://www.ogc.org/standards/wms/
- Overpass API (OSM) : https://wiki.openstreetmap.org/wiki/Overpass_API
- Politique d'usage de Nominatim : https://operations.osmfoundation.org/policies/nominatim/
- Documentation rasterio : https://rasterio.readthedocs.io
- Documentation shapely : https://shapely.readthedocs.io

---

### Apprentissage 9 : Zones non couvertes et exclusions de périmètre (19 oct 2026)

**Date** : 19 oct 2026  
**Constat** : Hilda a signalé que la surface brute d'un bâtiment n'est pas toujours la surface à couvrir par le DAS.

**Points clés** :
- Certaines zones ne sont pas couvertes par conception (ex. navires, locaux avec moteurs ou matériel).
- Des exclusions volontaires peuvent être faites pour respecter un seuil (ex. ascenseurs, cages).
- Les espaces creux et la structure de chaque étage influencent le périmètre à couvrir, et varient d'un niveau à l'autre.
- Des zones peuvent déjà être couvertes par le réseau existant, identifiées après les mesures radio sur site : elles ne sont alors pas prises en compte dans le dimensionnement.

**Action** :
- Distinguer trois surfaces par étage : surface brute, surface exclue (avec motif), surface à couvrir.
- Ajouter au modèle de données une liste de zones exclues par étage, avec leur motif.
- Prévoir la prise en compte des zones déjà couvertes à partir des résultats de mesures radio, quand ils existent.

---

## ❓ Questions Ouvertes

| Question | État | À faire |
|----------|------|---------|
| Cloisonnement : par niveau, par section ou par bâtiment ? | ⏳ | Exploiter les données brutes |
| Volume de données disponibles ? | ⏳ | Audit dataset (en moyenne une cinquantaine par an) |
| Précision acceptable du devis ? | ⏳ | Poser a Yoann |
| Base géographique 3D : comment y accéder ? | ⏳ | Recherche sur le net |
| Constructeur fait partie des inputs ? | ✅ | Oui (Nicolas confirmé) |

---

## 🚨 Risques Identifiés

| Risque | Sévérité | Mitigation |
|--------|----------|-----------|
| Surface non apparente | 🔴 Critique | Audit dataset urgent |
| Données de coûts manquantes | 🔴 Critique | Valider avec le chiffrage |
| Cloisonnement non documenté dans ELR | 🟠 Haute | Voir comment exploiter les données brutes |
| Surface brute différente de la surface à couvrir | 🟠 Haute | Modéliser les exclusions par étage |

---

## 📚 Références

- **CDC** : Cahier des charges initial (à enrichir avec état de l'art)
- **Retours** : Charles Olivier (Teams), Nicolas (mail)
- **Etat de l'art** : `/docs/etat_de_lart_chiffrage.md`

---

**Dernière mise à jour** : 19 oct 2026

---

## Format d'ajout

À chaque apprentissage ou décision importante, ajouter une section :

```
### Apprentissage X : [Titre court]

**Date** : [JJ mois AAAA]  
**Constat** : [Qu'est-ce qu'on a découvert ?]

**Points clés** :
- Point 1
- Point 2

**Action** : [Qu'est-ce qu'on fait maintenant ?]
```

Cela permettra de **redécouvrir le contexte** lors de la rédaction du PFE.
