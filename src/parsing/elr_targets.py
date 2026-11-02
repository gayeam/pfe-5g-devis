"""Quantités cibles tirées de l'ELR : ce que le modèle devra prédire.

L'ELR fait foi pour les quantités : les rapports (antennes, routage) peuvent être
partiels, l'ELR est la liste du matériel commandé.

Chaque ligne de l'ELR est rangée dans une catégorie, à partir de son type, de son
modèle et de sa description. Les règles sont des heuristiques construites sur les
études disponibles : une ligne non reconnue va dans « autres », et la fonction
`unclassified` permet de les relire pour compléter les règles.
"""

import re

import pandas as pd

TARGET_COLUMNS = [
    "elr_antennes",
    "elr_unites_radio",
    "elr_equipements_actifs",
    "elr_coax_m_total",
    "elr_coax_m_1_4",
    "elr_coax_m_1_2",
    "elr_coax_m_7_8",
    "elr_coax_m_1_1_4",
    "elr_coax_m_autre",
    "elr_fibre_m",
    "elr_cuivre_m",
    "elr_bretelles",
    "elr_connecteurs_coax",
    "elr_connecteurs_fibre",
    "elr_coupleurs",
    "elr_splitters",
    "elr_hybrides",
    "elr_filtres",
    "elr_charges",
    "elr_autres",
]

ACTIVE_TYPES = {"fiber bda hub", "fiber repeater hub", "riu", "bda"}
ACTIVE_RE = re.compile(
    r"GENESIS|Master Unit|Network Extender|Remote Unit|Radio Node|Hub Optic|Main Unit|"
    r"Fiber Repeater|Expansion PSU|PSU module",
    re.IGNORECASE,
)
FIBER_RE = re.compile(r"fiber|fibre|optic|pigtail|\bFO\b|SC-APC|LC-UPC|vers HOU|vers HRN", re.IGNORECASE)
COPPER_RE = re.compile(r"CAT-?\d|RJ-?45", re.IGNORECASE)
JUMPER_RE = re.compile(r"jumper|bretelle|cordon", re.IGNORECASE)
COUPLER_RE = re.compile(r"coupler|coupleur", re.IGNORECASE)
SPLITTER_RE = re.compile(r"splitter|divider|\d-way", re.IGNORECASE)
HYBRID_RE = re.compile(r"hybrid", re.IGNORECASE)
LOAD_RE = re.compile(r"\bload\b|charge", re.IGNORECASE)

# Diamètre d'un coax, lu dans le modèle ou la description.
DIAMETERS = [
    ("1_1_4", re.compile(r'1[ -]1/4|\b114R?\b|LCFS?114', re.IGNORECASE)),
    ("7_8", re.compile(r'7/8|LCF78|\b078R?\b', re.IGNORECASE)),
    ("1_4", re.compile(r'1/4"|LSF2', re.IGNORECASE)),
    ("1_2", re.compile(r'1/2|LCF12|SCF12|\b012R?\b', re.IGNORECASE)),
]


def _diameter(text):
    for name, pattern in DIAMETERS:
        if pattern.search(text):
            return name
    return "autre"


def classify(row):
    """Catégorie d'une ligne de l'ELR (clé de TARGET_COLUMNS, sans le préfixe « elr_ »)."""
    kind = str(row["type"]).strip().lower()
    text = f"{row['model']} {row['description']}"
    unit = str(row["unit"]).strip().lower()

    if kind == "antenna":
        return "antennes"
    if kind == "media converter":
        return "unites_radio"
    if kind in ACTIVE_TYPES or ACTIVE_RE.search(text):
        return "equipements_actifs"
    if kind == "connector":
        return "connecteurs_fibre" if FIBER_RE.search(text) or COPPER_RE.search(text) else "connecteurs_coax"
    if kind == "cable" and unit == "m":
        if FIBER_RE.search(text):
            return "fibre_m"
        if COPPER_RE.search(text):
            return "cuivre_m"
        return f"coax_m_{_diameter(text)}"
    if kind == "cable" and JUMPER_RE.search(text):
        return "bretelles"
    if HYBRID_RE.search(text):
        return "hybrides"
    if kind == "splitter" and COUPLER_RE.search(text):
        return "coupleurs"
    if kind == "splitter" and SPLITTER_RE.search(text):
        return "splitters"
    if kind == "attenuator" or LOAD_RE.search(text):
        return "charges"
    if kind == "filter":
        return "filtres"
    return "autres"


def elr_targets(elr):
    """Renvoie un dictionnaire {colonne cible: quantité} pour une étude."""
    result = {name: 0.0 for name in TARGET_COLUMNS}
    if elr.empty:
        return result
    categories = elr.apply(classify, axis=1)
    for category, qty in zip(categories, elr["qty"].fillna(0)):
        result[f"elr_{category}"] += float(qty)
    result["elr_coax_m_total"] = sum(
        result[k] for k in ("elr_coax_m_1_4", "elr_coax_m_1_2", "elr_coax_m_7_8", "elr_coax_m_1_1_4", "elr_coax_m_autre")
    )
    return {k: round(v, 2) for k, v in result.items()}


def unclassified(elr):
    """Lignes rangées dans « autres » : à relire pour compléter les règles."""
    if elr.empty:
        return elr
    return elr[elr.apply(classify, axis=1) == "autres"]