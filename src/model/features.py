"""Entrées (X) et sorties (Y) du modèle, à partir du corpus produit par src.parsing.corpus.

Entrées : ce qu'on connaît avant la conception.
- bandes : nombre de bandes, et présence de la 5G ;
- opérateurs : nombre d'opérateurs ;
- MIMO : au moins un système en MIMO (oui / non) ;
- étages : nombre d'étages du bâtiment ;
- locaux techniques : nombre, et niveau du plus bas (sous-sol négatif, RDC 0, R+n positif) ;
- hauteur des antennes (2,5 m par défaut) ;
- méthode : VPLE ou FRT ;
- surface prédite (m²) et nombre d'étages couverts (surface prédite non nulle) : utilisés quand
  la surface est connue pour la plupart des études de train (MIN_SURFACE_SHARE). Les études
  de train sans surface sont alors écartées de l'apprentissage.

Le type de DAS (passif, actif, hybride) n'est pas une entrée saisie : c'est un scénario.
Le modèle l'apprend sur les études passées, puis donne une estimation pour chacun des
trois types, pour les comparer.

Sorties : le nombre d'éléments rayonnants (antennes, ou unités radio en DAS actif) et les
quantités de l'ELR (colonnes « elr_… » du corpus).
"""

import re
from pathlib import Path

import numpy as np
import pandas as pd

DAS_TYPES = ["passif", "actif", "hybride"]
BASE_FEATURES = [
    "bandes",
    "bande_5g",
    "operateurs",
    "mimo",
    "etages",
    "locaux_techniques",
    "niveau_local",
    "hauteur_antennes",
    "methode_frt",
]
DAS_FEATURES = [f"das_{t}" for t in DAS_TYPES]
SURFACE_FEATURE = "surface_predite_m2"
COVERED_FEATURE = "etages_couverts"
SURFACE_FEATURES = [SURFACE_FEATURE, COVERED_FEATURE]
# Part minimale des études de train avec une surface pour s'en servir comme entrée.
MIN_SURFACE_SHARE = 0.6
DEFAULT_HEIGHT_M = 2.5

# Sorties prédites, avec leur unité (pour l'affichage).
TARGETS = {
    "design_elements": "u",
    "elr_coax_m_total": "m",
    "elr_coax_m_1_2": "m",
    "elr_coax_m_7_8": "m",
    "elr_coax_m_1_1_4": "m",
    "elr_bretelles": "u",
    "elr_connecteurs_coax": "u",
    "elr_coupleurs": "u",
    "elr_splitters": "u",
    "elr_hybrides": "u",
    "elr_filtres": "u",
    "elr_charges": "u",
    "elr_fibre_m": "m",
    "elr_unites_radio": "u",
    "elr_equipements_actifs": "u",
}


def load_corpus(root):
    """Lit data/corpus/train/dataset.csv et data/corpus/test/dataset.csv (colonne split conservée)."""
    base = Path(root) / "corpus"
    frames = []
    for split in ("train", "test"):
        path = base / split / "dataset.csv"
        if path.exists():
            frames.append(pd.read_csv(path, sep=";", encoding="utf-8-sig"))
    if not frames:
        raise FileNotFoundError(f"Aucun corpus dans {base} : lancer d'abord « python -m src.parsing.corpus build ».")
    return pd.concat(frames, ignore_index=True)


# Repère de niveau à l'intérieur d'un nom (« BAN R1 », « Bataclan_RDC », « Building 1 | R3 »).
LEVEL_TOKEN_RE = re.compile(
    r"(?:^|[\s_|/\-])(RDC|RDJ|REZ|(?:SS|NIVS)-?\d+|(?:R|N|NIV|NIVEAU|ET|ETAGE|ÉTAGE|FLOOR|DECK)\s?[+-]?\d+)(?=$|[\s_|/\-])",
    re.IGNORECASE,
)


def _level_of(text):
    if text in ("SS", "SOUS-SOL", "SOUSSOL"):
        return -1
    match = re.match(r"^(?:SS|R|N|NIV|NIVEAU)-(\d+)$", text) or re.match(r"^(?:SS|NIVS|S)-?(\d+)$", text)
    if match:
        return -int(match.group(1))
    if text.startswith(("RDC", "RDJ", "REZ")) or text in ("R0", "N0", "NIV0"):
        return 0
    match = (re.match(r"^(?:R|N|NIV|NIVEAU|ET|ETAGE|ÉTAGE|FLOOR|DECK)\+?(\d+)$", text)
             or re.match(r"^([+-]?\d+)$", text))
    if match:
        return int(match.group(1))
    return None


def floor_level(label):
    """Niveau d'un étage : « SS-1 », « R-1 », « SS1 », « N-1 », « -1 » -> -1 ; « RDC », « RDJ » -> 0 ;
    « R+2 », « R2 », « N2 », « NIV 2 », « 2 » -> 2. Un nom composé est lu par son dernier repère
    (« BAN R1 » -> 1, « Bataclan_RDC » -> 0). Renvoie None si aucun repère n'est reconnu."""
    text = str(label).upper().strip()
    level = _level_of(text.replace(" ", ""))
    if level is not None:
        return level
    tokens = LEVEL_TOKEN_RE.findall(text)
    return _level_of(tokens[-1].replace(" ", "")) if tokens else None


def _split_list(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return []
    return [v.strip() for v in str(value).split(";") if v.strip()]


def _max_number(value, default):
    numbers = []
    for part in _split_list(value):
        try:
            numbers.append(float(part.replace(",", ".")))
        except ValueError:
            pass
    return max(numbers) if numbers else default


def features(df, use_surface=False):
    """Tableau des entrées du modèle, à partir des colonnes du corpus."""
    X = pd.DataFrame(index=df.index)
    X["bandes"] = pd.to_numeric(df["bands_count"], errors="coerce").fillna(0)
    X["bande_5g"] = df["bands"].fillna("").astype(str).str.contains(r"\(5G\)").astype(int)
    X["operateurs"] = pd.to_numeric(df["operators_count"], errors="coerce").fillna(1).clip(lower=1)
    X["mimo"] = (pd.to_numeric(df["mimo_count"], errors="coerce").fillna(0) > 0).astype(int)
    X["etages"] = pd.to_numeric(df["floors_total"], errors="coerce").fillna(1).clip(lower=1)
    locals_ = df["local_floors"].map(_split_list)
    X["locaux_techniques"] = locals_.map(lambda f: max(len(f), 1))
    X["niveau_local"] = locals_.map(
        lambda f: min([lv for lv in map(floor_level, f) if lv is not None], default=0)
    )
    X["hauteur_antennes"] = df["antenna_height_m"].map(lambda v: _max_number(v, DEFAULT_HEIGHT_M))
    X["methode_frt"] = (df.get("methode", pd.Series("VPLE", index=df.index)) == "FRT").astype(int)
    for das in DAS_TYPES:
        X[f"das_{das}"] = (df["das_type"] == das).astype(int)
    columns = BASE_FEATURES + DAS_FEATURES
    if use_surface:
        X[SURFACE_FEATURE] = pd.to_numeric(df[SURFACE_FEATURE], errors="coerce")
        covered = pd.to_numeric(df.get(COVERED_FEATURE, pd.Series(np.nan, index=df.index)), errors="coerce")
        # Sans le détail par étage, on suppose tous les étages couverts.
        X[COVERED_FEATURE] = covered.fillna(X["etages"]).clip(lower=1)
        columns = BASE_FEATURES + SURFACE_FEATURES + DAS_FEATURES
    return X[columns]


def has_surface(df):
    """Masque des études dont la surface prédite est connue et non nulle."""
    if SURFACE_FEATURE not in df:
        return pd.Series(False, index=df.index)
    values = pd.to_numeric(df[SURFACE_FEATURE], errors="coerce")
    return values.notna() & (values > 0)


def surface_available(df, min_share=MIN_SURFACE_SHARE):
    """Vrai si la surface prédite est connue pour au moins min_share des études."""
    return bool(len(df)) and float(has_surface(df).mean()) >= min_share


def targets(df):
    """Tableau des sorties. Une colonne absente du corpus vaut 0."""
    Y = pd.DataFrame(index=df.index)
    for name in TARGETS:
        Y[name] = pd.to_numeric(df[name], errors="coerce").fillna(0) if name in df else 0.0
    return Y


def features_from_inputs(columns, das, bandes, bande_5g, operateurs, mimo, etages,
                         locaux_techniques=1, niveau_local=0, hauteur_antennes=DEFAULT_HEIGHT_M,
                         methode="VPLE", surface=None, etages_couverts=None):
    """Entrées du modèle pour une nouvelle étude et un type de DAS (scénario)."""
    values = {
        "bandes": bandes,
        "bande_5g": int(bool(bande_5g)),
        "operateurs": max(operateurs, 1),
        "mimo": int(bool(mimo)),
        "etages": max(etages, 1),
        "locaux_techniques": max(locaux_techniques, 1),
        "niveau_local": niveau_local,
        "hauteur_antennes": hauteur_antennes,
        "methode_frt": int(methode == "FRT"),
        SURFACE_FEATURE: surface,
        COVERED_FEATURE: max(etages_couverts or etages, 1),
    }
    for t in DAS_TYPES:
        values[f"das_{t}"] = int(t == das)
    return pd.DataFrame([values])[columns]