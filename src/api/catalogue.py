"""Familles du catalogue et import des références depuis les ELR des études."""

from pathlib import Path

from ..parsing.check import find_files
from ..parsing.corpus import STUDIES_DIR, list_studies
from ..parsing.elr import parse_elr
from ..parsing.elr_targets import classify

# Catégorie de l'ELR (elr_targets.classify) -> famille du catalogue.
CATEGORY_TO_FAMILY = {
    "antennes": "Antenne",
    "unites_radio": "Unité radio",
    "equipements_actifs": "Équipement actif",
    "coax_m_1_4": "Coax 1/4\"",
    "coax_m_1_2": "Coax 1/2\"",
    "coax_m_7_8": "Coax 7/8\"",
    "coax_m_1_1_4": "Coax 1\"1/4",
    "coax_m_autre": "Coax (autre)",
    "fibre_m": "Fibre",
    "cuivre_m": "Câble cuivre",
    "bretelles": "Bretelle",
    "connecteurs_coax": "Connecteur coax",
    "connecteurs_fibre": "Connecteur fibre / cuivre",
    "coupleurs": "Coupleur",
    "splitters": "Splitter",
    "hybrides": "Hybride / matrice",
    "filtres": "Filtre / combineur",
    "charges": "Charge",
    "autres": "Autre",
}
FAMILIES = list(dict.fromkeys(CATEGORY_TO_FAMILY.values()))


def references_from_elr(root):
    """Références distinctes des ELR des études (data/etudes). Renvoie (liste de dicts, erreurs)."""
    studies_dir = Path(root) / STUDIES_DIR
    if not studies_dir.is_dir():
        return [], [f"Dossier introuvable : {studies_dir}"]
    found, seen, errors = [], set(), []
    for folder in list_studies(studies_dir):
        try:
            elr = parse_elr(find_files(studies_dir / folder)["elr"])
        except Exception as e:  # un ELR illisible ne bloque pas les autres
            errors.append(f"{folder} : {e}")
            continue
        for _, line in elr.iterrows():
            key = (line["manufacturer"].strip().lower(), line["model"].strip().lower())
            if key in seen or not line["model"].strip():
                continue
            seen.add(key)
            found.append(
                {
                    "famille": CATEGORY_TO_FAMILY.get(classify(line), "Autre"),
                    "fabricant": line["manufacturer"].strip(),
                    "reference": line["model"].strip(),
                    "description": line["description"].strip()[:500],
                    "unite": "m" if str(line["unit"]).lower() == "m" else "u",
                    "source": "ELR",
                }
            )
    return found, errors