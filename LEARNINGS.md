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
- À spécifier par niveau ? Nicolas dit "à voir"

**Action** : À valider lors du questionnaire audit

---

### Apprentissage 4 : Extraction iBwave & Identification Type DAS (12 oct 2026)

**Date** : 12 oct 2026  
**Constat** : Hilda/Yanis ont clarifié workflow extraction données et heuristiques d'identification DAS.

**Points clés** :
- Fichiers `.ibw` (iBwave natifs) contiennent la surface → à extraire directement
- Paramètres clés : surface, étages (max ~10), config/étage (open space, dense, etc.), fréquence (basse/haute), MIMO, technos (4G/5G mix)
- **Type DAS non mentionné dans ELR** → à déduire depuis designs
  - RosenBerger ou SoliD → Actif OU Hybride
  - Fibre end-to-end → Actif
  - Coupleurs/Splitters → Passif OU Hybride
- **Contrainte opérateurs** : Bouygues Télécom refuse répéteurs/atténuateurs (critère sélection)
- **Complexité conception** : DAS Passif difficile (équilibrage puissance, pertes coax, position baies selon étage/pièce) ; Actif/Hybride simplifié (fibre)
- **Procédure extraction surface** : À déterminer (manuel vs auto ?) + valider approche AMina

**Action** : Phase 2 — Parser `.ibw` pour extraction surface + équipementiers + opérateurs ; clarifier procédure extraction

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

---

## 📚 Références

- **CDC** : Cahier des charges initial (à enrichir avec état de l'art)
- **Retours** : Charles Olivier (Teams), Nicolas (mail)
- **Questionnaires** : `/docs/Questionnaire_Audit_PFE.docx` + `/docs/Questionnaire_Chiffrage_PFE.docx`

---

**Dernière mise à jour** : 12 oct 2026

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
