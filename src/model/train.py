"""Premier modèle : prédire le nombre d'antennes et les quantités de l'ELR.

Usage :
    python -m src.model.train --root data
    python -m src.model.train --root data --multi-bat   (garde les études sur plusieurs bâtiments)

Entrées et sorties : voir src/model/features.py. Le type de DAS sert de scénario :
le modèle l'apprend sur les études passées, et la prédiction donne une estimation par type.

Pour chaque sortie, trois modèles sont comparés :
- mediane : médiane des études de train du même type de DAS. C'est la référence simple :
  un modèle plus complexe doit faire mieux pour être retenu ;
- ratio_surface (si la surface est utilisée) : densité au m² du même type de DAS × surface ;
- ridge : régression linéaire régularisée ;
- foret : forêt aléatoire.

Évaluation, sans tricher :
1. validation croisée sur le train, groupée par site : à chaque tour, des sites entiers sont
   mis de côté, le modèle apprend sur les autres et prédit ceux-là ;
2. le meilleur modèle de chaque sortie (en validation croisée) est réentraîné sur tout le train ;
3. il est évalué une seule fois sur le test, qu'il n'a jamais vu, avec le vrai type de DAS
   de chaque étude.

Indicateurs :
- WAPE : somme des écarts absolus / somme des quantités réelles (erreur relative globale) ;
- ±20 % : part des études (quantité réelle non nulle) prédites à ±20 % près.

Sorties (dans data/modeles/, ignoré par Git) :
- modele_v1.joblib : les modèles retenus, utilisés par src.model.predict ;
- evaluation_v1.csv : le tableau des résultats ;
- predictions_test_v1.csv : quantités réelles et prédites, étude par étude, sur le test.
"""

import argparse
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .estimators import MedianByDas, RatioSurfaceByDas
from .features import MIN_SURFACE_SHARE, TARGETS, features, has_surface, load_corpus, surface_available, targets

MODEL_DIR = "modeles"
VERSION = "v1"


def candidate_models(use_surface=False):
    models = {"mediane": MedianByDas()}
    if use_surface:
        models["ratio_surface"] = RatioSurfaceByDas()
    return {
        **models,
        "ridge": make_pipeline(StandardScaler(), Ridge(alpha=1.0)),
        "foret": RandomForestRegressor(n_estimators=300, min_samples_leaf=2, random_state=0),
    }


def wape(y_true, y_pred):
    total = float(np.sum(np.abs(y_true)))
    return float(np.sum(np.abs(y_true - y_pred)) / total) if total > 0 else np.nan


def within(y_true, y_pred, tolerance=0.2):
    mask = y_true > 0
    if not mask.any():
        return np.nan
    return float(np.mean(np.abs(y_pred[mask] - y_true[mask]) <= tolerance * y_true[mask]))


def evaluate(root, multi_bat=False):
    root = Path(root)
    corpus = load_corpus(root)
    if not multi_bat and "buildings_count" in corpus:
        # Leur ELR est global : les liaisons entre bâtiments dépendent de distances inconnues.
        several = pd.to_numeric(corpus["buildings_count"], errors="coerce").fillna(1) > 1
        if several.any():
            print(f"{int(several.sum())} étude(s) sur plusieurs bâtiments écartée(s) (option --multi-bat pour les garder).")
        corpus = corpus[~several]
    train = corpus[corpus["split"] == "train"].reset_index(drop=True)
    test = corpus[corpus["split"] == "test"].reset_index(drop=True)

    use_surface = surface_available(train)
    if use_surface:
        # Les études sans surface ne peuvent pas servir : on les écarte (train et test).
        missing_train, missing_test = (~has_surface(train)).sum(), (~has_surface(test)).sum()
        train = train[has_surface(train)].reset_index(drop=True)
        test = test[has_surface(test)].reset_index(drop=True)
        if missing_train or missing_test:
            print(f"Surface inconnue : {missing_train} étude(s) de train et {missing_test} de test écartées.")
    X_train, Y_train = features(train, use_surface), targets(train)
    X_test, Y_test = features(test, use_surface), targets(test)
    groups = train["site_id"].astype(str).to_numpy()
    n_sites = len(set(groups))
    n_folds = min(5, n_sites)

    print(f"Corpus : {len(train)} étude(s) en train ({n_sites} sites), {len(test)} en test.")
    print("Études de train par type de DAS :", train["das_type"].value_counts().to_dict())
    print(f"Surface : {'utilisée' if use_surface else f'non utilisée (connue pour moins de {MIN_SURFACE_SHARE:.0%} des études de train)'}.")
    if n_folds < 2:
        print("Pas assez de sites en train pour une validation croisée (2 au minimum).")
        return
    print(f"Validation croisée : {n_folds} plis, groupés par site.\n")

    rows, chosen, predictions = [], {}, {}
    for target, unit in TARGETS.items():
        y = Y_train[target].to_numpy(dtype=float)
        row = {"sortie": target, "unite": unit, "moyenne_train": round(float(y.mean()), 1)}
        if not (y > 0).any():
            chosen[target] = MedianByDas().fit(X_train, y)
            row["modele_retenu"] = "mediane (toujours 0 en train)"
            predictions[target] = np.zeros(len(test))
            rows.append(row)
            continue

        scores = {}
        for name, model in candidate_models(use_surface).items():
            pred = cross_val_predict(model, X_train, y, groups=groups, cv=GroupKFold(n_splits=n_folds))
            pred = np.clip(pred, 0, None)
            scores[name] = wape(y, pred)
            row[f"wape_cv_{name}"] = round(100 * scores[name], 1)
        best = min(scores, key=lambda k: scores[k] if not np.isnan(scores[k]) else np.inf)
        model = candidate_models(use_surface)[best].fit(X_train, y)
        chosen[target] = model
        row["modele_retenu"] = best

        if len(test):
            pred_test = np.clip(model.predict(X_test), 0, None)
            predictions[target] = pred_test
            y_test = Y_test[target].to_numpy(dtype=float)
            row["wape_test"] = round(100 * wape(y_test, pred_test), 1) if y_test.sum() > 0 else None
            share = within(y_test, pred_test)
            row["test_a_20pct"] = None if np.isnan(share) else f"{100 * share:.0f} %"
        rows.append(row)

    table = pd.DataFrame(rows)
    out_dir = root / MODEL_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    bundle = {
        "version": VERSION,
        "features": list(X_train.columns),
        "use_surface": use_surface,
        "models": chosen,
        "units": TARGETS,
        "train_size": len(train),
        "das_counts": train["das_type"].value_counts().to_dict(),
        "feature_ranges": {c: (float(X_train[c].min()), float(X_train[c].max())) for c in X_train.columns},
        "evaluation": table,
    }
    joblib.dump(bundle, out_dir / f"modele_{VERSION}.joblib")
    table.to_csv(out_dir / f"evaluation_{VERSION}.csv", index=False, sep=";", encoding="utf-8-sig")

    if len(test):
        detail = test[["study_folder", "site_id", "das_type"]].copy()
        for target in TARGETS:
            detail[f"{target}_reel"] = Y_test[target].round(2)
            detail[f"{target}_predit"] = np.round(predictions[target], 2)
        detail.to_csv(out_dir / f"predictions_test_{VERSION}.csv", index=False, sep=";", encoding="utf-8-sig")

    pd.set_option("display.width", 220)
    print("Erreur relative globale (WAPE, en %) : plus c'est bas, mieux c'est.")
    print(table.to_string(index=False))
    print(f"\nModèles enregistrés dans {out_dir / f'modele_{VERSION}.joblib'}")
    print(f"Détail du test dans {out_dir / f'predictions_test_{VERSION}.csv'}")


def main():
    parser = argparse.ArgumentParser(description="Entraîne et évalue le premier modèle")
    parser.add_argument("--root", default="data")
    parser.add_argument("--multi-bat", action="store_true", help="garder les études sur plusieurs bâtiments")
    args = parser.parse_args()
    evaluate(args.root, args.multi_bat)


if __name__ == "__main__":
    main()