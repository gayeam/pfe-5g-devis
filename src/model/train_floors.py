"""Modèle par étage : estimer, étage par étage, les éléments rayonnants et les câbles.

Usage :
    python -m src.model.train_floors --root data

Données : data/corpus/train/etages.csv et test/etages.csv (une ligne par étage, produites par
« python -m src.parsing.corpus build »).

Entrées d'un étage :
- surface prédite (m²) ;
- niveau (SS-1 -> -1, RDC -> 0, R+2 -> 2), local technique sur l'étage, distance au local (niveaux) ;
- de l'étude : type de DAS (scénario), méthode, nombre de bandes, d'opérateurs, de bandes en MIMO,
  plusieurs bâtiments ou non.

Sorties d'un étage : éléments rayonnants (antennes ou unités radio), linéaire coax, linéaire fibre.

Règle fixe : un étage sans surface prédite (0 m²) n'est pas couvert : 0 élément. Ces étages ne
servent pas à apprendre le nombre d'éléments, mais restent pour les câbles (une colonne montante
peut desservir ou traverser un étage non couvert).

Estimation en deux temps, comme un concepteur :
1. éléments de l'étage, à partir de la surface et du reste. Modèles comparés :
   - ratio_m2 : densité au m² médiane du même type de DAS × surface (référence simple) ;
   - ridge : régression linéaire sur les logarithmes ;
   - gbm : arbres de décision boostés (HistGradientBoosting), sur le logarithme de la quantité ;
2. câbles de l'étage, à partir du nombre d'éléments (prédit à l'étape 1), de la distance au local
   et du reste. Le coax n'est appris que sur les DAS passifs et hybrides, la fibre sur les actifs
   et hybrides ; l'autre cas vaut 0. Modèles comparés :
   - ratio_element : longueur médiane par élément du même type de DAS × éléments ;
   - ridge, gbm : comme ci-dessus, avec le nombre d'éléments en entrée ;
   - gbm_direct : sans le nombre d'éléments (l'ancienne façon, pour comparer).
   En validation croisée, l'étape 2 reçoit les éléments prédits par l'étape 1 sur des sites
   qu'elle n'a pas vus : l'erreur mesurée inclut celle de l'étape 1, comme en vrai.

Évaluation, sans tricher : validation croisée groupée par site sur le train, puis une seule
évaluation sur le test. Deux niveaux d'erreur (WAPE, en %) :
- par étage ;
- par étude : somme des étages prédits comparée au total réel de l'étude. C'est ce chiffre
  qui se compare au modèle par étude (python -m src.model.train).

Sorties (dans data/modeles/, ignoré par Git) :
- modele_etages_v1.joblib, evaluation_etages_v1.csv, predictions_test_etages_v1.csv.
"""

import argparse
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .estimators import LogTarget, RatioM2ByDas, RatioPerElement
from .features import DAS_TYPES

MODEL_DIR = "modeles"
VERSION = "v1"
FLOORS_FILE = "etages.csv"

FEATURES = [
    "log_surface",
    "niveau",
    "local_technique",
    "distance_local",
    "methode_frt",
    "bandes",
    "operateurs",
    "bandes_mimo",
    "multi_batiments",
] + [f"das_{t}" for t in DAS_TYPES]

# Types de bâtiment (etudes.xlsx, colonne type_batiment) : une colonne 0/1 par type.
BUILDING_TYPES = [
    "Hôpital / santé", "Hôtel / résidence", "Bureaux / administration", "Commerce",
    "Industrie / logistique", "Aéroport / gare", "Salle de spectacle / sport", "Enseignement",
    "Parking", "Autre",
]
TYPE_FEATURES = [f"type_{i}" for i in range(len(BUILDING_TYPES))]

# Sorties : nom de colonne -> (libellé, unité)
TARGETS = {
    "elements": ("Éléments rayonnants", "u"),
    "coax_m": ("Coax", "m"),
    "fibre_m": ("Fibre", "m"),
}


def load_floors(root):
    base = Path(root) / "corpus"
    frames = []
    for split in ("train", "test"):
        path = base / split / FLOORS_FILE
        if path.exists():
            frames.append(pd.read_csv(path, sep=";", encoding="utf-8-sig"))
    if not frames:
        raise FileNotFoundError(f"Aucun {FLOORS_FILE} dans {base} : lancer d'abord « python -m src.parsing.corpus build ».")
    return pd.concat(frames, ignore_index=True)


def _count_list(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return 0
    return len([v for v in str(value).split(";") if v.strip()])


def floor_features(df):
    """Tableau des entrées du modèle par étage (les valeurs inconnues restent vides : NaN)."""
    X = pd.DataFrame(index=df.index)
    surface = pd.to_numeric(df["surface_predite_m2"], errors="coerce")
    X["log_surface"] = np.log1p(surface.clip(lower=0))
    X["niveau"] = pd.to_numeric(df["niveau"], errors="coerce")
    X["local_technique"] = pd.to_numeric(df["local_technique"], errors="coerce").fillna(0)
    X["distance_local"] = pd.to_numeric(df["distance_local"], errors="coerce")
    X["methode_frt"] = (df.get("methode", pd.Series("VPLE", index=df.index)) == "FRT").astype(int)
    X["bandes"] = pd.to_numeric(df["bands_count"], errors="coerce").fillna(0)
    X["operateurs"] = pd.to_numeric(df["operators_count"], errors="coerce").fillna(1).clip(lower=1)
    X["bandes_mimo"] = df["mimo_bands"].map(_count_list)
    X["multi_batiments"] = (pd.to_numeric(df["buildings_count"], errors="coerce").fillna(1) > 1).astype(int)
    for das in DAS_TYPES:
        X[f"das_{das}"] = (df["das_type"] == das).astype(int)
    building = df.get("type_batiment", pd.Series("", index=df.index)).fillna("").astype(str).str.strip()
    for column, name in zip(TYPE_FEATURES, BUILDING_TYPES):
        X[column] = (building == name).astype(int)
    return X[FEATURES + TYPE_FEATURES]


def _gbm():
    return HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, min_samples_leaf=10, random_state=0)


def _ridge():
    return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=1.0))


# Modèles des éléments : (modèle, utilise le type de bâtiment)
def element_models():
    return {
        "ratio_m2": (RatioM2ByDas(), False),
        "ridge": (LogTarget(_ridge()), False),
        "gbm": (LogTarget(_gbm()), False),
        "ridge_type": (LogTarget(_ridge()), True),
        "gbm_type": (LogTarget(_gbm()), True),
    }


def _columns(uses_type):
    return FEATURES + (TYPE_FEATURES if uses_type else [])


# Modèles de câbles : (modèle, utilise le nombre d'éléments)
def cable_models():
    return {
        "ratio_element": (RatioPerElement(), True),
        "ridge": (LogTarget(_ridge()), True),
        "gbm": (LogTarget(_gbm()), True),
        "gbm_direct": (LogTarget(_gbm()), False),
    }


# Types de DAS concernés par chaque câble (les autres valent 0).
CABLE_DAS = {"coax_m": ["passif", "hybride"], "fibre_m": ["actif", "hybride"]}
ELEMENT_COLUMNS = ["elements", "log_elements"]


def with_elements(X, elements):
    """Entrées des câbles : celles de l'étage plus le nombre d'éléments (réel ou prédit)."""
    X = X.copy()
    X["elements"] = np.asarray(elements, dtype=float)
    X["log_elements"] = np.log1p(np.clip(X["elements"], 0, None))
    return X


def wape(y_true, y_pred):
    total = float(np.sum(np.abs(y_true)))
    return float(np.sum(np.abs(y_true - y_pred)) / total) if total > 0 else np.nan


def within(y_true, y_pred, tolerance=0.2):
    mask = y_true > 0
    if not mask.any():
        return np.nan
    return float(np.mean(np.abs(y_pred[mask] - y_true[mask]) <= tolerance * y_true[mask]))


def _study_scores(df, y_true, y_pred):
    by_study = pd.DataFrame({"study": df["study_folder"].to_numpy(), "y": y_true, "p": y_pred}).groupby("study").sum()
    return wape(by_study["y"].to_numpy(), by_study["p"].to_numpy()), within(by_study["y"].to_numpy(), by_study["p"].to_numpy())


def _target(df, column):
    return pd.to_numeric(df[column], errors="coerce").fillna(0).to_numpy(dtype=float)


def _das_mask(df, target):
    return df["das_type"].isin(CABLE_DAS[target]).to_numpy()


def _fit_cable(model, uses_elements, X, elements, y):
    columns = FEATURES + (ELEMENT_COLUMNS if uses_elements else [])
    return clone(model).fit(with_elements(X, elements)[columns], y), columns


def _predict_cable(fitted, columns, X, elements, mask):
    pred = np.clip(fitted.predict(with_elements(X, elements)[columns]), 0, None)
    return np.where(mask, pred, 0.0)


def _test_scores(row, test, y_test, pred_test):
    row["test_etage"] = round(100 * wape(y_test, pred_test), 1) if y_test.sum() > 0 else None
    study_wape, study_within = _study_scores(test, y_test, pred_test)
    row["test_etude"] = None if np.isnan(study_wape) else round(100 * study_wape, 1)
    row["test_etude_a_20pct"] = None if np.isnan(study_within) else f"{100 * study_within:.0f} %"


def evaluate(root):
    root = Path(root)
    floors = load_floors(root)
    floors = floors[pd.to_numeric(floors["surface_predite_m2"], errors="coerce").notna()].reset_index(drop=True)
    floors["covered"] = pd.to_numeric(floors["surface_predite_m2"], errors="coerce") > 0
    # Étude dont aucun élément n'a pu être placé sur un étage (routage incomplet) : ses étages
    # diraient « 0 antenne » à tort. On l'écarte.
    placed = floors.groupby("study_folder")["elements"].transform(lambda e: pd.to_numeric(e, errors="coerce").fillna(0).sum())
    unplaced = sorted(floors.loc[placed == 0, "study_folder"].unique())
    if unplaced:
        print(f"Écartée(s), aucun élément placé sur un étage : {', '.join(unplaced)}")
        floors = floors[placed > 0].reset_index(drop=True)
    train = floors[floors["split"] == "train"].reset_index(drop=True)
    test = floors[floors["split"] == "test"].reset_index(drop=True)
    X_train, X_test = floor_features(train), floor_features(test)
    covered_train, covered_test = train["covered"].to_numpy(), test["covered"].to_numpy()
    groups = train["site_id"].astype(str).to_numpy()
    n_folds = min(5, len(set(groups)))
    folds = list(GroupKFold(n_splits=n_folds).split(X_train, groups=groups)) if n_folds >= 2 else []

    print(f"Étages : {len(train)} en train ({train['study_folder'].nunique()} études, {len(set(groups))} sites), "
          f"{len(test)} en test ({test['study_folder'].nunique()} études).")
    print(f"Étages non couverts (0 m²) : {int((~covered_train).sum())} en train -> 0 élément par règle.")
    typed = train.drop_duplicates("study_folder")["type_batiment"].fillna("").astype(str).str.strip().isin(BUILDING_TYPES)
    print(f"Type de bâtiment renseigné : {int(typed.sum())} étude(s) de train sur {len(typed)}.")
    if not folds:
        print("Pas assez de sites pour une validation croisée.")
        return
    print(f"Validation croisée : {n_folds} plis, groupés par site.\n")

    rows, chosen = [], {}
    predictions = {}

    # --- Étape 1 : éléments de l'étage (appris sur les étages couverts)
    y = _target(train, "elements")
    row = {"sortie": "Éléments rayonnants", "unite": "u", "moyenne_par_etage": round(float(y[covered_train].mean()), 1)}
    oof, scores = {}, {}
    for name, (model, uses_type) in element_models().items():
        cols = _columns(uses_type)
        pred = np.zeros(len(train))
        for fit_idx, val_idx in folds:
            fit_idx = fit_idx[covered_train[fit_idx]]
            fitted = clone(model).fit(X_train.iloc[fit_idx][cols], y[fit_idx])
            pred[val_idx] = np.where(covered_train[val_idx], np.clip(fitted.predict(X_train.iloc[val_idx][cols]), 0, None), 0)
        oof[name], scores[name] = pred, wape(y, pred)
        row[f"cv_etage_{name}"] = round(100 * scores[name], 1)
        row[f"cv_etude_{name}"] = round(100 * _study_scores(train, y, pred)[0], 1)
    best = min(scores, key=lambda k: scores[k] if not np.isnan(scores[k]) else np.inf)
    model, uses_type = element_models()[best]
    element_columns = _columns(uses_type)
    element_model = clone(model).fit(X_train.loc[covered_train, element_columns], y[covered_train])
    chosen["elements"] = {"model": element_model, "name": best, "columns": element_columns}
    row["modele_retenu"] = best
    oof_elements = oof[best]  # éléments prédits sur des sites non vus : entrée des câbles en validation
    test_elements = (np.where(covered_test, np.clip(element_model.predict(X_test[element_columns]), 0, None), 0)
                     if len(test) else np.zeros(0))
    if len(test):
        _test_scores(row, test, _target(test, "elements"), test_elements)
    predictions["elements"] = test_elements
    rows.append(row)

    # --- Étape 2 : câbles de l'étage (à partir des éléments prédits)
    true_elements = y
    for target, label in (("coax_m", "Coax"), ("fibre_m", "Fibre")):
        y = _target(train, target)
        mask_train = _das_mask(train, target)
        row = {"sortie": label, "unite": "m",
               "moyenne_par_etage": round(float(y[mask_train].mean()), 1) if mask_train.any() else 0.0}
        if not (y[mask_train] > 0).any():
            row["modele_retenu"] = "aucun (toujours 0)"
            chosen[target] = None
            predictions[target] = np.zeros(len(test))
            rows.append(row)
            continue
        scores = {}
        for name, (model, uses_elements) in cable_models().items():
            pred = np.zeros(len(train))
            for fit_idx, val_idx in folds:
                fit_idx = fit_idx[mask_train[fit_idx]]
                # Apprentissage avec les vrais éléments, validation avec les éléments prédits.
                fitted, columns = _fit_cable(model, uses_elements, X_train.iloc[fit_idx], true_elements[fit_idx], y[fit_idx])
                pred[val_idx] = _predict_cable(fitted, columns, X_train.iloc[val_idx], oof_elements[val_idx], mask_train[val_idx])
            scores[name] = wape(y, pred)
            row[f"cv_etage_{name}"] = round(100 * scores[name], 1)
            row[f"cv_etude_{name}"] = round(100 * _study_scores(train, y, pred)[0], 1)
        best = min(scores, key=lambda k: scores[k] if not np.isnan(scores[k]) else np.inf)
        model, uses_elements = cable_models()[best]
        fitted, columns = _fit_cable(model, uses_elements, X_train[mask_train], true_elements[mask_train], y[mask_train])
        chosen[target] = {"model": fitted, "name": best, "columns": columns, "das": CABLE_DAS[target]}
        row["modele_retenu"] = best
        if len(test):
            pred_test = _predict_cable(fitted, columns, X_test, test_elements, _das_mask(test, target))
            predictions[target] = pred_test
            _test_scores(row, test, _target(test, target), pred_test)
        rows.append(row)

    table = pd.DataFrame(rows)
    names = ["ratio_m2", "ratio_element", "ridge", "ridge_type", "gbm", "gbm_type", "gbm_direct"]
    order = ["sortie", "unite", "moyenne_par_etage"]
    order += [f"cv_{level}_{n}" for n in names for level in ("etage", "etude") if f"cv_{level}_{n}" in table]
    order += [c for c in ("modele_retenu", "test_etage", "test_etude", "test_etude_a_20pct") if c in table]
    table = table[order]
    out_dir = root / MODEL_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {"version": VERSION, "features": FEATURES, "models": chosen, "targets": TARGETS,
         "train_floors": len(train), "evaluation": table},
        out_dir / f"modele_etages_{VERSION}.joblib",
    )
    table.to_csv(out_dir / f"evaluation_etages_{VERSION}.csv", index=False, sep=";", encoding="utf-8-sig")
    if len(test):
        detail = test[["study_folder", "das_type", "etage", "niveau", "surface_predite_m2", "distance_local"]].copy()
        for target in TARGETS:
            detail[f"{target}_reel"] = _target(test, target).round(2)
            detail[f"{target}_predit"] = np.round(predictions[target], 2)
        detail.to_csv(out_dir / f"predictions_test_etages_{VERSION}.csv", index=False, sep=";", encoding="utf-8-sig")

    pd.set_option("display.width", 260)
    pd.set_option("display.max_columns", 40)
    print("Erreur relative globale (WAPE, en %) : plus c'est bas, mieux c'est.")
    print("cv_etage_* : erreur étage par étage ; cv_etude_* : somme des étages comparée au total de l'étude.")
    print("Câbles : ratio_element, ridge et gbm partent des éléments prédits ; gbm_direct non (pour comparer).")
    print(table.set_index("sortie").T.fillna("-").to_string())
    print(f"\nModèles enregistrés dans {out_dir / f'modele_etages_{VERSION}.joblib'}")
    print(f"Détail du test dans {out_dir / f'predictions_test_etages_{VERSION}.csv'}")


def main():
    parser = argparse.ArgumentParser(description="Entraîne et évalue le modèle par étage")
    parser.add_argument("--root", default="data")
    args = parser.parse_args()
    evaluate(args.root)


if __name__ == "__main__":
    main()