"""Une ligne de dataset par étude, à partir des rapports iBwave.

Usage :
    python -m src.parsing.dataset --dir data/HOTEL_CELESTE
    python -m src.parsing.dataset --dir data/HOTEL_CELESTE --out ligne.csv

Les colonnes qui ne viennent pas des rapports (surface, typologie d'environnement
par étage, hauteur sous plafond) ne sont pas produites ici : elles seront saisies
à part pour chaque étude.

Hauteur des antennes : lue dans le rapport antennes (2026). Ce rapport ne la
contient pas en 2023 : on la lit alors dans le rapport électromagnétique (EM),
s'il est présent dans le dossier de l'étude.
"""

import argparse
import re
from pathlib import Path

import pandas as pd
import pdfplumber

from .check import controls
from .utils import to_float

EM_FILE = "Electromagnetic Field Report.pdf"
# Dans le rapport EM, chaque ligne d'antenne finit par « Pass - Pass <hauteur> ».
EM_HEIGHT_RE = re.compile(r"Pass - Pass ([\d,]+)")


def _join(values):
    """Liste lisible : « a; b; c » (ignore les valeurs vides)."""
    return "; ".join(str(v) for v in values if v is not None and v == v)


def em_heights(study_dir):
    """Hauteurs d'antennes (m) lues dans le rapport EM. Liste vide si le rapport est absent."""
    path = Path(study_dir) / EM_FILE
    if not path.exists():
        return []
    heights = set()
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for match in EM_HEIGHT_RE.finditer(page.extract_text() or ""):
                value = to_float(match.group(1))
                if value is not None:
                    heights.add(value)
    return sorted(heights)


def antenna_height(study_dir, antennas):
    """Renvoie (hauteurs, source) : rapport antennes d'abord, sinon rapport EM."""
    heights = sorted({h for h in antennas["height_m"].dropna()}) if len(antennas) else []
    if heights:
        return heights, "rapport antennes"
    heights = em_heights(study_dir)
    if heights:
        return heights, "rapport EM"
    return [], ""


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


def study_row(study_dir, site_name=None):
    """Renvoie un dictionnaire : une ligne du dataset pour l'étude."""
    res = controls(study_dir, site_name)
    routing = res["routing"]
    bts = res["bts"]
    site = res["site"]
    units = res["units"]
    legend = res["legend"]

    coax = routing[routing["kind"] == "coax"]
    jumpers = routing[routing["kind"] == "jumper"]
    n_coax = len(coax)
    n_antennas = len(units)
    coax_length = round(float(coax["length_est_m"].sum()), 2)

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
    to_antenna = routing[(routing["kind"] == "coax") & routing["dest_node"].str.startswith("ANT")]
    antennas_per_floor = to_antenna.dropna(subset=["dest_floor"]).groupby("dest_floor")["dest_node"].nunique()
    antennas_floor_text = _join(f"{f}:{n}" for f, n in antennas_per_floor.items())
    all_floors = set(routing["source_floor"].dropna()) | set(routing["dest_floor"].dropna())

    heights, height_source = antenna_height(study_dir, res["antennas"])
    manufacturers = manufacturers_by_type(res["elr"])
    operators_names = _join(sorted(legend["operator"].unique())) if len(legend) else ""

    return {
        "study": Path(study_dir).name,
        "site": site["site"],
        "das_type": site["das_type"],
        "das_active_families": _join(site["active_families"]),
        "das_passive_families": _join(site["passive_families"]),
        "bands_modes": _join(site["band_modes"]),
        "bands": _join(site["bands"]),
        "operators_estimate": site["operators_estimate"],
        "operators_names": operators_names,
        "local_floors": _join(site["floors"]),
        "bts_count": len(bts),
        "mimo_count": int((bts["mode"] == "MIMO").sum()),
        "siso_count": int((bts["mode"] == "SISO").sum()),
        "floors_total": len(all_floors),
        "floors_list": _join(sorted(all_floors)),
        "floors_with_antennas": len(antennas_per_floor),
        "antennas_by_floor": antennas_floor_text,
        "antennas": n_antennas,
        "antenna_height_m": _join(heights),
        "antenna_height_source": height_source,
        "manufacturers_by_type": manufacturers,
        "coax_count": n_coax,
        "coax_length_m": coax_length,
        "coax_length_per_antenna_m": round(coax_length / n_antennas, 2) if n_antennas else None,
        "coax_length_by_floor": floor_text,
        "coax_by_diameter": diameter_text,
        "jumpers": len(jumpers),
        "connectors": 2 * n_coax,
    }


def main():
    parser = argparse.ArgumentParser(description="Une ligne de dataset pour une étude")
    parser.add_argument("--dir", required=True, help="dossier de l'étude (ex. data/HOTEL_CELESTE)")
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