"""Estimation pour une nouvelle étude : nombre d'antennes et quantités de l'ELR, par type de DAS.

Usage :
    python -m src.model.predict --bandes 4 --operateurs 3 --etages 6
    python -m src.model.predict --bandes 5 --5g --operateurs 1 --mimo --etages 3 --locaux 1 --niveau-local -1 --hauteur 3.6
    python -m src.model.predict --bandes 4 --operateurs 2 --etages 8 --surface 12000

Le modèle doit avoir été entraîné avant (python -m src.model.train --root data).
Le résultat donne une colonne par type de DAS (passif, actif, hybride), pour les comparer.
Un avertissement s'affiche si une valeur sort de ce qui a été vu à l'entraînement, ou si
un type de DAS est représenté par trop peu d'études : l'estimation y est moins fiable.
"""

import argparse
from pathlib import Path

import joblib
import numpy as np

from .features import DAS_TYPES, DEFAULT_HEIGHT_M, features_from_inputs
from .train import MODEL_DIR, VERSION

LABELS = {
    "design_elements": "Antennes (ou unités radio)",
    "elr_coax_m_total": "Coax (total)",
    "elr_coax_m_1_2": "Coax 1/2\"",
    "elr_coax_m_7_8": "Coax 7/8\"",
    "elr_coax_m_1_1_4": "Coax 1\"1/4",
    "elr_bretelles": "Bretelles",
    "elr_connecteurs_coax": "Connecteurs coax",
    "elr_coupleurs": "Coupleurs",
    "elr_splitters": "Splitters",
    "elr_hybrides": "Hybrides / matrices",
    "elr_filtres": "Filtres / combineurs",
    "elr_charges": "Charges",
    "elr_fibre_m": "Fibre",
    "elr_unites_radio": "Unités radio (LRN…)",
    "elr_equipements_actifs": "Équipements actifs (tête)",
}
MIN_STUDIES_PER_DAS = 5


def predict_all(bundle, **inputs):
    """Renvoie {type de DAS: {sortie: valeur}}."""
    result = {}
    for das in DAS_TYPES:
        X = features_from_inputs(bundle["features"], das=das, **inputs)
        result[das] = {t: float(np.clip(m.predict(X)[0], 0, None)) for t, m in bundle["models"].items()}
    return result


def _show(value, unit):
    return f"{value:,.0f} m".replace(",", " ") if unit == "m" else f"{round(value):d}"


def main():
    parser = argparse.ArgumentParser(description="Estime antennes et quantités de l'ELR, par type de DAS")
    parser.add_argument("--root", default="data")
    parser.add_argument("--bandes", type=int, required=True, help="nombre de bandes")
    parser.add_argument("--5g", dest="bande_5g", action="store_true", help="une des bandes est en 5G")
    parser.add_argument("--operateurs", type=int, required=True, help="nombre d'opérateurs")
    parser.add_argument("--mimo", action="store_true", help="au moins un système en MIMO")
    parser.add_argument("--etages", type=int, required=True, help="nombre d'étages")
    parser.add_argument("--locaux", type=int, default=1, help="nombre de locaux techniques (défaut 1)")
    parser.add_argument("--niveau-local", type=int, default=0, help="niveau du local technique : -1 sous-sol, 0 RDC, 2 R+2…")
    parser.add_argument("--hauteur", type=float, default=DEFAULT_HEIGHT_M, help="hauteur des antennes en m (défaut 2,5)")
    parser.add_argument("--methode", choices=["VPLE", "FRT"], default="VPLE")
    parser.add_argument("--surface", type=float, default=None, help="surface prédite en m² (si le modèle l'utilise)")
    args = parser.parse_args()

    path = Path(args.root) / MODEL_DIR / f"modele_{VERSION}.joblib"
    if not path.exists():
        print(f"Modèle introuvable ({path}) : lancer d'abord « python -m src.model.train --root data ».")
        return
    bundle = joblib.load(path)
    if bundle["use_surface"] and args.surface is None:
        print("Ce modèle utilise la surface : ajouter --surface (m²).")
        return

    inputs = {
        "bandes": args.bandes,
        "bande_5g": args.bande_5g,
        "operateurs": args.operateurs,
        "mimo": args.mimo,
        "etages": args.etages,
        "locaux_techniques": args.locaux,
        "niveau_local": args.niveau_local,
        "hauteur_antennes": args.hauteur,
        "methode": args.methode,
        "surface": args.surface,
    }
    checks = {"bandes": "bandes", "operateurs": "operateurs", "etages": "etages",
              "locaux_techniques": "locaux_techniques", "hauteur_antennes": "hauteur_antennes"}
    if bundle["use_surface"]:
        checks["surface"] = "surface_predite_m2"
    for key, column in checks.items():
        low, high = bundle["feature_ranges"][column]
        if not low <= inputs[key] <= high:
            print(f"Attention : {key} = {inputs[key]:g} est hors de ce qui a été vu à l'entraînement ({low:g} à {high:g}).")

    result = predict_all(bundle, **inputs)
    counts = bundle["das_counts"]
    header = "".join(f"{das:>14s}" for das in DAS_TYPES)
    print(f"\nEstimation (modèle {bundle['version']}, entraîné sur {bundle['train_size']} études) :")
    print(f"  {'':34s}{header}")
    for target, unit in bundle["units"].items():
        cells = "".join(f"{_show(result[das][target], unit):>14s}" for das in DAS_TYPES)
        print(f"  {LABELS.get(target, target):34s}{cells}")
    print(f"  {'Études de train de ce type':34s}" + "".join(f"{counts.get(das, 0):>14d}" for das in DAS_TYPES))
    few = [das for das in DAS_TYPES if counts.get(das, 0) < MIN_STUDIES_PER_DAS]
    if few:
        print(f"\nPeu d'études de type {', '.join(few)} (moins de {MIN_STUDIES_PER_DAS}) : estimation peu fiable.")
    print("Ce sont des estimations moyennes à partir des études passées, pas un relevé de conception.")


if __name__ == "__main__":
    main()