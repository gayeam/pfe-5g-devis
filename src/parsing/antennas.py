"""Lecture du rapport « Antennas Report » (PDF iBwave).

Le rapport contient :
- un tableau : une ligne par antenne et par système (opérateur, bande, techno).
  Selon la version d'iBwave, le tableau a 8 colonnes (2023) ou 12 (2026) ;
  on lit les colonnes communes et on laisse vides les autres ;
- une légende « System legend » qui donne, pour chaque opérateur, la liste de
  ses systèmes (techno, bande, duplex). C'est la seule source du nom des
  opérateurs dans ce rapport (version 2026).
"""

import re

import pandas as pd
import pdfplumber

from .utils import clean, to_float

ANTENNA_ID_RE = re.compile(r"^ANT\d+$")

COLUMNS = [
    "antenna_id",
    "model",
    "system",
    "gain_dbi",
    "loss_db",
    "eirp_power_channel_dbm",
    "eirp_composite_dbm",
    "rsrp_dbm",
    "azimuth_deg",
    "tilt_deg",
    "orientation_deg",
    "height_m",
]

LEGEND_COLUMNS = ["operator", "technology", "generation", "band", "band_label", "duplex", "bandwidth"]

# Exemple dans le texte du rapport : « BOUYGUES / LTE-A / 1800 MHz - DCS / FDD - 20 MHz - Band 3 »
LEGEND_RE = re.compile(
    r"(?P<operator>[A-Z][A-Z\-]{2,}) / (?P<technology>LTE-A|LTE|UMTS|GSM|5G NR) / "
    r"(?P<band_label>[^/]+?) / (?P<duplex>FDD|TDD) - (?P<bandwidth>\d+ MHz) - (?P<band>Band \d+|n\d+)"
)

GENERATION = {"GSM": "2G", "UMTS": "3G", "LTE": "4G", "LTE-A": "4G", "5G NR": "5G"}


def _num(cells, index):
    """Nombre de la cellule à cet index, ou None si la colonne n'existe pas dans ce format."""
    return to_float(cells[index]) if len(cells) > index else None


def parse_antennas(path):
    """Renvoie un DataFrame : une ligne par antenne et par système.

    Les lignes d'en-tête répétées sur chaque page sont ignorées.
    Les lignes « All systems » (total par antenne) sont conservées ici.
    """
    rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for raw in table:
                    cells = [clean(c) for c in raw]
                    if len(cells) < 3 or not ANTENNA_ID_RE.match(cells[0]):
                        continue
                    rows.append(
                        {
                            "antenna_id": cells[0],
                            "model": cells[1],
                            "system": cells[2],
                            "gain_dbi": _num(cells, 3),
                            "loss_db": _num(cells, 4),
                            "eirp_power_channel_dbm": _num(cells, 5),
                            "eirp_composite_dbm": _num(cells, 6),
                            "rsrp_dbm": _num(cells, 7),
                            "azimuth_deg": _num(cells, 8),
                            "tilt_deg": _num(cells, 9),
                            "orientation_deg": _num(cells, 10),
                            "height_m": _num(cells, 11),
                        }
                    )
    return pd.DataFrame(rows, columns=COLUMNS)


def parse_legend(path):
    """Renvoie un DataFrame : une ligne par (opérateur, techno, bande) de la légende.

    La légende est lue dans le texte brut des pages, car elle n'est pas un tableau.
    Les doublons (la légende est parfois répétée) sont supprimés.
    Dans les rapports 2023, la légende n'a pas ce format : le DataFrame est vide.
    """
    with pdfplumber.open(path) as pdf:
        text = " ".join((page.extract_text() or "") for page in pdf.pages)
    text = clean(text)

    rows, seen = [], set()
    for m in LEGEND_RE.finditer(text):
        key = (m["operator"], m["technology"], m["band"])
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "operator": m["operator"],
                "technology": m["technology"],
                "generation": GENERATION[m["technology"]],
                "band": m["band"],
                "band_label": m["band_label"].strip(),
                "duplex": m["duplex"],
                "bandwidth": m["bandwidth"],
            }
        )
    return pd.DataFrame(rows, columns=LEGEND_COLUMNS)


def antennas_units(df):
    """Une ligne par antenne physique (identifiant ANTn) : modèle et systèmes servis.

    Les lignes « All systems » ne sont pas comptées comme des systèmes.
    Une antenne listée plusieurs fois (répétitions entre pages) n'est comptée qu'une fois.
    """
    rows = []
    for antenna_id, group in df.groupby("antenna_id", sort=True):
        systems = sorted({s for s in group["system"] if s and s != "All systems"})
        rows.append(
            {
                "antenna_id": antenna_id,
                "model": group["model"].iloc[0],
                "n_systems": len(systems),
                "systems": systems,
            }
        )
    return pd.DataFrame(rows, columns=["antenna_id", "model", "n_systems", "systems"])


def antennas_summary(df):
    """Nombre d'antennes distinctes par modèle (une antenne = un identifiant ANTn)."""
    return (
        df.drop_duplicates("antenna_id")
        .groupby("model")
        .size()
        .rename("antennas")
        .reset_index()
    )


def legend_summary(legend):
    """Par opérateur : nombre de systèmes et liste des générations (2G, 3G, 4G, 5G)."""
    if legend.empty:
        return legend
    return (
        legend.groupby("operator")
        .agg(systems=("band", "count"), generations=("generation", lambda g: "/".join(sorted(set(g)))))
        .reset_index()
    )