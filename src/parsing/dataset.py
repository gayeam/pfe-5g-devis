"""Une ligne de dataset par étude, à partir des rapports iBwave.

Usage :
    python -m src.parsing.dataset --dir data/ETUDE_A
    python -m src.parsing.dataset --dir data/ETUDE_A --out ligne.csv

La ligne contient :
- des caractéristiques (entrées du modèle) : type de DAS, bandes, opérateurs, secteurs,
  étages, bâtiments, hauteur des antennes, systèmes BTS et modes MIMO/SISO ;
- des mesures du design (routage) : coax, bretelles, linéaire par étage ;
- les quantités cibles tirées de l'ELR (colonnes « elr_… »), qui font foi.

Les colonnes qui ne viennent pas des rapports (surfaces, environnements) sont
ajoutées par le corpus (corpus.py), à partir de la saisie manuelle.

Sources, par ordre de priorité :
- opérateurs : légende du rapport antennes ; sinon estimation par les BTS du routage ;
- bandes : légende ; sinon systèmes du rapport antennes ; sinon BTS du routage ;
- hauteur des antennes : rapport antennes ; sinon rapport EM s'il est présent ;
  sinon 2,5 m par défaut (la colonne antenna_height_source l'indique).
"""

import argparse
import re
from pathlib import Path

import pandas as pd
import pdfplumber

from .antennas import antenna_systems
from .check import controls
from .elr_targets import elr_targets
from .synthese import band_label
from .systems import parse_system
from .utils import to_float

DEFAULT_ANTENNA_HEIGHT_M = 2.5

# Dans le rapport EM, chaque ligne d'antenne finit par « Pass - Pass <hauteur> ».
EM_HEIGHT_RE = re.compile(r"Pass - Pass ([\d,]+)")
# Bâtiment dans un nom d'étage : « BAT 10S R0 », « Bâtiment A - R+1 ».
BUILDING_RE = re.compile(r"\bB[AÂ]T(?:IMENT)?\.?\s*([A-Z0-9]+)", re.IGNORECASE)


def _join(values):
    """Liste lisible : « a; b; c » (ignore les valeurs vides)."""
    return "; ".join(str(v) for v in values if v is not None and v == v)


def em_heights(path):
    """Hauteurs d'antennes (m) lues dans le rapport EM. Liste vide si le rapport est absent."""
    if path is None or not Path(path).exists():
        return []
    heights = set()
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for match in EM_HEIGHT_RE.finditer(page.extract_text() or ""):
                value = to_float(match.group(1))
                if value is not None:
                    heights.add(value)
    return sorted(heights)


def antenna_height(antennas, em_path):
    """Renvoie (hauteurs, source) : rapport antennes, sinon rapport EM, sinon valeur par défaut."""
    heights = sorted({h for h in antennas["height_m"].dropna()}) if len(antennas) else []
    if heights:
        return heights, "rapport antennes"
    heights = em_heights(em_path)
    if heights:
        return heights, "rapport EM"
    return [DEFAULT_ANTENNA_HEIGHT_M], "valeur par défaut"


def manufacturers_by_type(elr):
    """« antenna: A, B ; cable: C » : fabricants de l'ELR par type d'équipement."""
    if elr.empty:
        return ""
    parts = []
    for type_name, group in elr.groupby(elr["type"].str.lower()):
        makers = sorted({m for m in group["manufacturer"] if m})
        if type_name and makers:
            parts.append(f"{type_name}: {', '.join(makers)}")
    return " ; ".join(parts)


def bands_and_source(legend, antennas, bts):
    """Bandes présentes (« 1800 MHz (4G) »…) et leur source."""
    if len(legend):
        labels = set()
        for row in legend.itertuples(index=False):
            info = parse_system(row.band_label)
            labels.add(band_label(info["freq_mhz"], row.generation))
        return sorted(labels), "légende"
    systems = antenna_systems(antennas) if len(antennas) else []
    if systems:
        labels = set()
        for label in systems:
            info = parse_system(label)
            labels.add(band_label(info["freq_mhz"], info["generation"]))
        return sorted(labels), "rapport antennes"
    if len(bts):
        return sorted({band_label(r.freq_mhz, r.generation) for r in bts.itertuples(index=False)}), "routage"
    return [], ""


def sectors_count(antennas, bts):
    """Nombre de secteurs : plus grand numéro de secteur vu dans les systèmes (antennes ou BTS)."""
    sectors = set()
    if len(antennas):
        for label in antenna_systems(antennas):
            sector = parse_system(label)["sector"]
            if sector:
                sectors.add(sector)
    if len(bts):
        sectors |= {int(s) for s in bts["sector"].dropna()}
    return max(sectors) if sectors else None


def buildings(floors):
    """Bâtiments repérés dans les noms d'étage. Liste vide si aucun nom de bâtiment."""
    found = set()
    for floor in floors:
        found |= {b.upper() for b in BUILDING_RE.findall(str(floor))}
    return sorted(found)


def study_row(study_dir, site_name=None):
    """Renvoie un dictionnaire : une ligne du dataset pour l'étude."""
    res = controls(study_dir, site_name)
    routing = res["routing"]
    bts = res["bts"]
    site = res["site"]
    legend = res["legend"]
    antennas = res["antennas"]

    cables = routing[routing["kind"] == "coax"]
    coax = cables[cables["medium"] == "coax"]
    jumpers = routing[routing["kind"].isin(["jumper", "cable_jumper"])]
    n_coax = len(coax)
    coax_length = round(float(coax["length_est_m"].sum()), 2)
    n_elements = len(res["elements"])

    per_floor = (
        coax.groupby("source_floor")
        .agg(n=("record_id", "count"), length=("length_est_m", "sum"))
        .reset_index()
    )
    floor_text = _join(f"{r.source_floor}:{r.length:g} m" for r in per_floor.itertuples(index=False))

    per_diameter = (
        coax.groupby("cable_diameter", dropna=False)
        .agg(n=("record_id", "count"), length=("length_est_m", "sum"))
        .reset_index()
    )
    diameter_text = _join(
        f"{r.cable_diameter}:{r.n} ({r.length:g} m)" for r in per_diameter.itertuples(index=False)
    )

    # Étage de chaque antenne : étage de destination du câble qui y arrive.
    to_antenna = routing[routing["dest_node"].str.startswith("ANT")]
    antennas_per_floor = to_antenna.dropna(subset=["dest_floor"]).groupby("dest_floor")["dest_node"].nunique()
    antennas_floor_text = _join(f"{f}:{n}" for f, n in antennas_per_floor.items())
    all_floors = set(routing["source_floor"].dropna()) | set(routing["dest_floor"].dropna())
    building_list = buildings(all_floors)

    heights, height_source = antenna_height(antennas, res["files"]["em"])
    operators = sorted(set(legend["operator"])) if len(legend) else []
    bands, bands_source = bands_and_source(legend, antennas, bts)

    row = {
        "study": Path(study_dir).name,
        "site": site["site"],
        "elr_format": res["files"]["elr"].suffix.lower().lstrip("."),
        # --- caractéristiques
        "das_type": site["das_type"],
        "das_active_families": _join(site["active_families"]),
        "das_passive_families": _join(site["passive_families"]),
        "bands": _join(bands),
        "bands_count": len(bands),
        "bands_source": bands_source,
        "bands_modes": _join(site["band_modes"]),
        "operators_count": len(operators) if operators else site["operators_estimate"],
        "operators_names": _join(operators),
        "operators_source": "légende" if operators else ("estimation BTS" if len(bts) else ""),
        "sectors_count": sectors_count(antennas, bts),
        "local_floors": _join(site["floors"]),
        "bts_count": len(bts),
        "mimo_count": int((bts["mode"] == "MIMO").sum()),
        "siso_count": int((bts["mode"] == "SISO").sum()),
        "floors_total": len(all_floors),
        "floors_list": _join(sorted(all_floors)),
        "buildings_count": len(building_list) or 1,
        "buildings_list": _join(building_list),
        "floors_with_antennas": len(antennas_per_floor),
        "antennas_by_floor": antennas_floor_text,
        "antenna_height_m": _join(heights),
        "antenna_height_source": height_source,
        "manufacturers_by_type": manufacturers_by_type(res["elr"]),
        # --- mesures du design (routage, peut être partiel)
        "design_elements": n_elements,
        "design_coax_count": n_coax,
        "design_coax_length_m": coax_length,
        "design_coax_length_per_element_m": round(coax_length / n_elements, 2) if n_elements else None,
        "design_coax_length_by_floor": floor_text,
        "design_coax_by_diameter": diameter_text,
        "design_fibre_m": round(float(cables.loc[cables["medium"] == "fibre", "length_est_m"].sum()), 2),
        "design_cuivre_m": round(float(cables.loc[cables["medium"] == "cuivre", "length_est_m"].sum()), 2),
        "design_jumpers": len(jumpers),
    }
    # --- cibles (ELR)
    row.update(elr_targets(res["elr"]))
    return row


def main():
    parser = argparse.ArgumentParser(description="Une ligne de dataset pour une étude")
    parser.add_argument("--dir", required=True, help="dossier de l'étude (ex. data/ETUDE_A)")
    parser.add_argument("--site", default=None, help="nom du site (sinon nom du dossier)")
    parser.add_argument("--out", default=None, help="fichier CSV de sortie (sinon affichage)")
    args = parser.parse_args()

    df = pd.DataFrame([study_row(args.dir, args.site)])
    if args.out:
        df.to_csv(args.out, index=False, sep=";", encoding="utf-8-sig")
        print(f"Ligne écrite dans {args.out}")
    else:
        print(df.T.to_string())


if __name__ == "__main__":
    main()