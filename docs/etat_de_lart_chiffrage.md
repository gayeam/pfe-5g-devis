# État de l'art : chiffrage d'un réseau DAS / 5G privé

Ce document décrit comment un chiffrage est construit dans le domaine des DAS (Distributed Antenna Systems) et des réseaux 5G privés, quels fichiers interviennent, et sur quelle logique repose le calcul. Il sert de base à la modélisation du projet. Les valeurs chiffrées (coefficients, taux, prix) ne sont pas publiées : elles dépendent de l'entreprise et sont paramétrées séparément.

## 1. Objectif d'un chiffrage

Un chiffrage transforme une description technique (inventaire de matériel, périmètre de travaux) en un prix de vente pour un client. Il doit répondre à trois questions :

- quoi poser (matériel et consommables),
- combien de temps cela prend (main d'œuvre, véhicules, déplacements),
- à quel prix vendre (marge, frais, aléas).

## 2. Chaîne de traitement

```
Conception radio (outil de simulation)
        │
        ▼
Équipment List Report (ELR) : modèle, description, quantité
        │
        ▼
Correspondance modèle → référence fournisseur → prix unitaire
        │                         ▲
        │                  bases de prix (catalogue, achats ponctuels)
        ▼
Temps unitaires par prestation (temps méthode)
        │
        ▼
Calcul du coût direct : matériel + main d'œuvre + véhicules + divers
        │
        ▼
Frais généraux, prix de revient, prix de vente, marge
        │
        ▼
Feuille de vente (devis)
```

## 3. Les fichiers qui interviennent

### 3.1 Équipment List Report (ELR)

Inventaire produit par la conception radio. Une ligne par modèle :

| Colonne | Contenu |
|---|---|
| Type | antenne, atténuateur, câble, connecteur, filtre, coupleur, splitter… |
| Fabricant | constructeur de l'équipement |
| Modèle | référence constructeur |
| Description | caractéristiques (fréquences, puissance, connectique) |
| Inventaire | numéro d'inventaire ou N/A |
| Quantité | nombre d'unités, ou longueur pour les câbles |

L'ELR ne contient pas les éléments de mise en œuvre : baies, chemins de câble, mises à la terre, supports, étiquetage, consommables. Ils sont ajoutés par le chiffreur.

Les longueurs de câble de l'ELR sont des longueurs de conception. Le chiffrage applique une marge de sécurité sur les cheminements : un écart entre longueur de conception et longueur chiffrée est normal et doit être paramétré.

### 3.2 Bases de prix

Trois sources de prix coexistent :

- **Tarifs publics fabricant** (liste installateur) : point de départ.
- **Tarifs négociés** de l'entreprise : listes internes qui regroupent les prix de plusieurs fournisseurs.
- **Devis ponctuels** : offres reçues pour une affaire, par exemple un fournisseur qui livre sur site.

Un dossier fournisseurs peut être incomplet : certaines références ne figurent dans aucune liste et doivent être demandées au constructeur par mail. Ces lignes restent à compléter à la main.

### 3.3 Feuille de vente (devis)

Fichier Excel qui transforme les coûts en prix de vente. Elle contient généralement :

- une **feuille de synthèse** avec les paramètres (frais généraux, risque, négociation, inflation, marge cible),
- une **feuille de calcul** qui additionne achats, main d'œuvre, véhicules, divers et frais généraux, puis calcule le prix de vente,
- des **forfaits** : un onglet par périmètre de travaux, avec son matériel, sa main d'œuvre et son total,
- des **listes de produits** (référencés et achats ponctuels),
- une **liste de temps méthode** (temps unitaire par prestation),
- une **feuille de répartition** (diamètres de câble, majorations de complexité).

## 4. Notions de base

### 4.1 Unités de mesure dans les devis

| Unité | Signification | Exemple |
|---|---|---|
| ml | mètre linéaire (câble, chemin de câble) | longueur de câble coaxial |
| U | unité (pièce) | connecteur, antenne |
| F | forfait : prestation globale sans quantité mesurée | installation d'une baie |
| JR | journée de travail | mesure radio |
| h/ml, h/U | temps unitaire par mètre ou par pièce | pose de câble |
| M3 | volume de véhicule | utilitaire 3 m³ |

### 4.2 Forfait et option

- **Forfait** : prix global pour un périmètre défini. L'entreprise porte le risque sur la quantité réelle.
- **Option** : travaux hors périmètre de base, chiffrés séparément. Le client peut les accepter ou les refuser.
- **Lot** : numéro de lot d'un marché public ou privé. Les documents d'appel d'offres associés sont le bordereau des prix unitaires (BPU), le détail quantitatif estimatif (DQE) et la décomposition du prix global forfaitaire (DPGF).

### 4.3 Coûts et prix

| Terme | Définition |
|---|---|
| Achats | coût du matériel |
| Main d'œuvre | heures × taux horaire chargé, par rôle |
| Véhicules | heures d'équipe × tarif du véhicule |
| Divers | pilotage, négociation, aléas, logistique (en pourcentage) |
| Coût direct | achats + main d'œuvre + véhicules + divers |
| Frais généraux (FG) | coûts de structure de l'entreprise non imputables à un chantier, récupérés par un pourcentage du chiffre d'affaires |
| Prix de revient | coût direct + frais généraux |
| CA (chiffre d'affaires) | prix de vente HT facturé au client |
| Marge | CA − prix de revient |

### 4.4 Frais généraux

Les frais généraux couvrent les coûts de structure : locaux, fonctions support (RH, comptabilité, direction, commercial), outils, assurances. Ils existent que le chantier soit en cours ou non.

Ils ne sont pas calculés chantier par chantier. Le modèle usuel est un pourcentage appliqué au CA, qui répartit les charges annuelles sur l'ensemble des affaires. Conséquence : un gros projet absorbe plus de frais généraux qu'un petit. Ce choix doit être noté comme hypothèse dans le modèle.

Les frais généraux sont distincts des frais de déplacement : les frais de repas et d'hébergement d'une équipe éloignée (grand déplacement) se chiffrent à part.

### 4.5 Coefficients

Les achats et la main d'œuvre sont souvent multipliés par un coefficient de vente, qui couvre une partie des frais et la marge. Un coefficient global peut ensuite faire passer du prix de revient au prix de vente.

Dans un modèle simplifié :

```
coût direct    = (achats + main d'œuvre) × k_vente + véhicules + divers
prix de revient = coût direct + FG% × CA
CA              = prix de revient × k_global
```

Les valeurs de `k_vente`, `k_global` et `FG%` sont à paramétrer.

## 5. Calcul de la main d'œuvre

La main d'œuvre se calcule en heures, à partir de temps méthode :

```
heures d'une prestation = quantité × temps unitaire
coût main d'œuvre     = Σ (heures par rôle × taux horaire chargé par rôle)
```

Exemple : 540 m de câble × 0,047 h/m = 25,2 h. Les temps unitaires sont des valeurs d'entreprise à paramétrer.

Principes :

- les rôles (technicien d'études, chef d'équipe, technicien ou chef de chantier, conducteur de travaux, chef de projet, chargé d'affaires) ont chacun un taux horaire ;
- une équipe type sur une journée = deux personnes sur sept heures ;
- certaines prestations sont forfaitaires (installation d'une baie, mesure radio) ;
- les versions « avec nacelle » ont des temps unitaires plus longs ;
- les véhicules sont liés aux heures d'équipe.

### 5.1 Majorations

- **Complexité du site** : trois niveaux, sans majoration puis +15 % environ, puis +40 % environ sur le temps. Les valeurs réelles sont internes.
- **Travail en hauteur (nacelle)** : majoration de quelques dizaines de pourcent sur les prestations concernées.

## 6. Équipements hors ELR

Un chiffrage ajoute systématiquement des éléments que l'ELR ne contient pas :

- baies et armoires,
- chemins de câble,
- mises à la terre et câbles de terre,
- supports d'antenne,
- étiquetage, coloris, pictogrammes,
- consommables (colliers, cosses, chevilles).

Dans les exemples étudiés, ces ajouts représentent une part significative des achats (de l'ordre d'un quart). Ils doivent être modélisés comme des règles dépendant du nombre d'antennes, de baies ou de niveaux, plutôt que comme des lignes ponctuelles.

## 7. Types de DAS et impact sur le coût

- **DAS passif** : pas d'électronique active, mais beaucoup de câbles, coupleurs et connecteurs. La pose et la main d'œuvre pèsent fortement.
- **DAS actif** : électronique (unités actives, alimentation) dans les locaux techniques. Le matériel pèse davantage.
- **DAS hybride** : mélange des deux ; le surcoût dépend des équipements ajoutés.

Un résultat contre-intuitif remonté par le terrain : le passif peut coûter plus cher que l'actif, car la pose dévore les heures. Ce point reste à vérifier sur plusieurs projets.

## 8. Précision attendue

- Devis approximatif : ±10 % acceptable sur un petit chantier.
- Sur un gros projet, un écart de quelques pourcents représente un montant important : il faut affiner la marge d'erreur selon le montant.

## 9. Entrées d'un modèle prédictif

| Entrée | Source |
|---|---|
| Surface, nombre d'étages, hauteur | plans, bâtiment |
| Indice de pénétration / cloisonnement | conception radio |
| Type de DAS | choix de conception |
| Environnement (typologie) | description du site |
| Nombre et type d'équipements | ELR |
| Longueurs de câble | ELR, avec marge de cheminement |
| Nombre de baies, chemins de câble | règles ou saisie |

Sorties attendues : inventaire complété, heures par rôle, coût direct, prix de revient, prix de vente, plage d'incertitude.

## 10. Points à valider avec un professionnel du chiffrage

- Comment le coefficient de vente et le coefficient de main d'œuvre sont-ils articulés ?
- Quelle est la formule complète du devis (la réponse reçue est incomplète) ?
- À quelle hauteur se situent les frais généraux par rapport au CA ?
- Comment les ajouts hors ELR sont-ils estimés sur un nouveau projet ?
- Quelle est la part des achats couverte par les tarifs négociés, par rapport aux tarifs publics ?