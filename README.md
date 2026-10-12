# PFE : Outil de Devis Prédictif pour Réseaux 5G Privés & DAS

**Période :** Octobre 2026 — Janvier 2027 (S1 INSA Lyon)  
**Lieu :** Eiffage Énergie Systèmes, service CARE, Lyon  
**Tuteur académique :** Sébastien Peychet (INSA Lyon)  
**Tuteur entreprise :** Nicolas Phalippon (Eiffage)  

---

## 📋 Objectif

Développer un **outil ML prédictif** capable de :
- Estimer un **devis approximatif** pour des réseaux 5G privés et DAS (Distributed Antenna Systems)
- Générer un **inventaire d'équipements** (BoM : Bill of Materials)
- Proposer **plusieurs solutions** (DAS passif, actif, hybride) avec comparaison des coûts
- Afficher les **études similaires** retrouvées et des indicateurs de confiance

### Données d'entrée (inputs)
- **Bâtiment** : nombre de niveaux, surfaces, indice de cloisonnement (semi-ouvert, léger, moyen, dense, très dense)
- **Technologie** : MIMO/SISO, bandes de fréquences, nombre d'opérateurs
- **Métier** : constructeur/équipementier choisi

### Données de sortie (outputs)
- **Infrastructure** : nombre d'antennes, longueurs de câbles coax/fibre
- **Estimatifs par type de DAS** : équipements et coûts pour chaque solution (passif/actif/hybride)
- **Indicateurs** : confiance de la prédiction, études similaires retrouvées

---

## 🔄 Contexte & Retours

### Retour d'Olivier (Eiffage)
> Le CDC est clair, mais peut-on être plus **innovant** ?  
> Idées : import automatique de plans (PDF/DWG) → calcul des superficies et étages  
> État de l'art manquant au CDC

**Action :** À ajouter au projet dès que possible.

### Echange avec Olivier
> Bonne idée d'exploiter les données géographiques.  
> Piste : base géographique 3D du gouvernement (+ précise qu'OpenStreetMap)  
> Fallback : plans 2D pour les nouvelles constructions

**Action :** Intégrer comme fonctionnalité optionnelle.

### Retour de Nicolas (Eiffage)
> Clarifications importantes sur inputs/outputs  
> ✅ Le choix du **type de DAS doit sortir de l'outil** (pas un input)  
> ✅ Ajouter indicateurs de confiance + liste des études similaires  
> ✅ Interface simple pour gérer le catalogue des constructeurs

**Action :** Intégré dans la conception.

---

## 📊 Stack Technique (Draft)

- **Backend** : FastAPI (Python)
- **ML** : scikit-learn (k-NN, clustering), XGBoost (prédictions coûts)
- **Frontend** : React + Vite
- **Données** : pandas, joblib (sérialisation modèles)
- **DevOps** : Docker, GitHub Actions, CI/CD

---

## 🚀 Phase 1 : Audit Dataset (Semaine du 12 oct)

**Objectif** : Valider que les données nécessaires existent et sont exploitables.

- [ ] Audit des Equipment List Reports (volume, format, structure)
- [ ] Retours du questionnaire auprès de Hilda, Yanis et Nicolas.
- [ ] Retours de Yoann sur le chiffrage (structure des devis, coûts, facteurs clés)
- [ ] Identification des contraintes et blocages
- [ ] Validation : données suffisantes ? Qualité OK ?

**Livrables** : Rapport d'audit + décision "go/no-go"

---

## 📚 Documents & Suivi

- **[ROADMAP.md](./ROADMAP.md)** — Timeline détaillée jusqu'à janvier 2027
- **[LEARNINGS.md](./LEARNINGS.md)** — Tracker des décisions et apprentissages (pour la rédaction du PFE)
- **Questionnaires** : voir dossier `/docs`

---

## 👥 Contacts

| Rôle | Nom | Email/Equipe |
|------|-----|--------------|
| Tuteur académique | Sébastien Peychet | INSA Lyon |
| Tuteur entreprise | Nicolas Phalippon | Eiffage |
| Responsable chiffrage | Yoann Munier | Eiffage |
| Collègues CARE | Hilda, Yanis, Nicolas | Eiffage |

---

## 📝 Notes

- ⚠️ **Pas de code pour l'instant** — focus sur l'audit dataset
- 📅 **Validation CDC attendue** : semaine du 12 oct
- 🎯 **Prochaine étape** : J1 avec le tuteur (16 oct) → cadrage formel

---

**Dernière mise à jour** : 12 oct 2026
