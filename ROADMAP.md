# ROADMAP PFE — Octobre 2026 → Janvier 2027

## Phase 1 : Audit & Cadrage (14 oct — 23 oct)

### Semaine 1 (12–16 oct)
- [ ] Poser les questionnaires à Hilda, Yanis, Nicolas
- [ ] Rencontre avec Yoann pour le chiffrage (structure des devis) le 12 à 14h
- [ ] Documenter les réponses
- [ ] **J1 avec tuteur (16 oct)** — cadrage formel après retours CDC

### Semaine 2 (19–23 oct)
- [ ] Analyser les retours des questionnaires
- [ ] Identifier données manquantes / blocages
- [ ] Rapport d'audit préliminaire
- [ ] Décision : go/no-go sur le dataset

**Livrables** : Rapport d'audit + validation dataset

---

## Phase 2 : Préparation Dataset (26 oct — 13 nov)

### Préparation
- [ ] Accès aux Equipment List Reports
- [ ] Anonymisation/export si nécessaire
- [ ] Structure brute des données
- [ ] 1ère EDA (exploratory data analysis)

### Nettoyage & Structuration
- [ ] Identifier les colonnes clés
- [ ] Gestion des données manquantes
- [ ] Validation de la qualité

### Documentation
- [ ] Data dictionary (description des colonnes)
- [ ] Statistiques dataset (volume, distributions)
- [ ] Limitations/contraintes identifiées

**Livrables** : Dataset structuré + data dictionary

---

## Phase 3 : Modèles ML & Backend (16 nov — 11 déc)

### Exploration ML
- [ ] k-NN pour retrouver études similaires
- [ ] Clustering pour catégoriser projets
- [ ] XGBoost pour prédictions de coûts
- [ ] Validation croisée & métriques

### Backend API
- [ ] Structure FastAPI
- [ ] Endpoints pour inputs utilisateur
- [ ] Logique de prédiction
- [ ] Sérialisation modèles (joblib)

### Tests
- [ ] Tests unitaires
- [ ] Tests API
- [ ] GitHub Actions CI/CD

**Livrables** : API fonctionnelle + modèles entraînés

---

## Phase 4 : Frontend & Intégration (14 déc — 08 jan)

### Interface
- [ ] Design propositions solutions (passif/actif/hybride)
- [ ] Affichage études similaires
- [ ] Indicateurs de confiance
- [ ] Formulaire inputs utilisateur

### Intégration
- [ ] Connexion Frontend ↔ Backend
- [ ] Tests end-to-end
- [ ] Documentation utilisateur

### Optionnel (si temps)
- [ ] Import plans PDF/DWG
- [ ] Base géographique 3D gouvernement

**Livrables** : Tool complet + documentation

---

## Phase 5 : Documentation & Soutenance (11–31 jan)

### Rédaction PFE
- [ ] Résumé exécutif
- [ ] État de l'art
- [ ] Méthodologie
- [ ] Résultats & validations
- [ ] Conclusions & futures améliorations

### Démonstration
- [ ] Préparation présentation
- [ ] Tests finaux
- [ ] Feedback tuteurs

**Livrables** : Mémoire PFE + présentation soutenance

---

## 🎯 Jalons Critiques

| Date | Jalon | Status |
|------|-------|--------|
| 16 oct | **J1 Tuteur** — cadrage après CDC | ⏳ |
| 23 oct | **Décision dataset** — go/no-go | ⏳ |
| 13 nov | **Dataset structuré** — prêt pour ML | ⏳ |
| 11 déc | **API & modèles** — validation | ⏳ |
| 08 jan | **Tool complet** — tests finaux | ⏳ |
| 31 jan | **Soutenance** — défense PFE | ⏳ |

---

## 📝 Notes

- ⚠️ Cette roadmap est **indicative** et évoluera selon les retours
- 🔄 Chaque phase dépend du succès de la précédente
- 📚 Les apprentissages clés seront documentés dans [LEARNINGS.md](./LEARNINGS.md)
- 🚨 **Risque principal** : qualité/volume du dataset → validation prioritaire

---

**Dernière mise à jour** : 12 oct 2026
