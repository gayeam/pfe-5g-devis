"""Constitution du corpus d'apprentissage : une étude par dossier, découpage train / test par site.

Trois étapes :

1. template : liste les dossiers d'études dans le dossier racine (ex. data/) et écrit
   - etudes.xlsx : une ligne par étude (site_id pré-rempli ; split et methode en liste déroulante) ;
   - etages.xlsx : une ligne par étude et par étage (surfaces à saisir) ;
   - zones.xlsx : une ligne par zone (environnement en liste déroulante, VPLE seulement).

2. À la main, dans Excel :
   - etudes.xlsx : split (train ou test), methode (VPLE ou FRT) ;
   - etages.xlsx : surface_totale_m2 et surface_predite_m2 (vide = même valeur que la totale) ;
   - zones.xlsx : une ligne par zone, avec sa surface et, pour une étude VPLE, son environnement.
     Pour une étude FRT, les zones ne se renseignent que par leur surface : pas d'environnement.

3. build : vérifie la saisie, calcule les agrégats, écrit train/dataset.csv et test/dataset.csv.

Règle : toutes les études d'un même site vont du même côté (split au niveau du site).

Usage :
    python -m src.parsing.corpus template --root data
    python -m src.parsing.corpus build --root data
"""

import argparse
import re
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.worksheet.datavalidation import DataValidation

from .check import ELR_FILE, ROUTING_FILE
from .dataset import _join, study_row
from .routing import parse_routing

ETUDES_FILE = "etudes.xlsx"
ETAGES_FILE = "etages.xlsx"
ZONES_FILE = "zones.xlsx"

ETUDES_COLUMNS = ["study_folder", "site_id", "split", "methode"]
ETAGES_COLUMNS = ["study_folder", "etage", "surface_totale_m2", "surface_predite_m2"]
ZONES_COLUMNS = ["study_folder", "etage", "zone", "surface_m2", "environnement"]

SPLITS = ["train", "test"]
METHODS = ["VPLE", "FRT"]
ENVIRONMENTS = [
    "Dense RF environment",
    "Medium RF environment",
    "Light RF environment",
    "Semi-open space",
    "Open space",
]
DENSE_LABEL = "Dense RF environment"

# Suffixe de version en fin de nom de dossier : « HOTEL CELESTE V12-V13 », « HOTEL CELESTE V10 avec parking ».
# Un nom qui ne se termine pas par un numéro de version n'est pas modifié (« CC V2 Villeneuve… » reste tel quel).
TRAILING_VERSION_RE = re.compile(r"(\s+V\d+(-V?\d+)?)+(\s+avec parking)?\s*$", re.IGNORECASE)


def site_from_folder(name):
    """Nom du site à partir du nom du dossier, sans le suffixe de version."""
    return TRAILING_VERSION_RE.sub("", name.replace("_", " ")).strip()


def _num(value):
    """Nombre saisi dans Excel (virgule ou point décimal), ou None si vide ou invalide."""
    text = str(value).strip().replace(",", ".")
    if text in ("", "nan", "None"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _read(path):
    return pd.read_excel(path, dtype=str).fillna("")


def _write_xlsx(df, path, dropdowns):
    """Écrit un tableau Excel ; chaque colonne de « dropdowns » devient une liste déroulante (500 lignes)."""
    df.to_excel(path, index=False)
    wb = load_workbook(path)
    ws = wb.active
    letters = {cell.value: cell.column_letter for cell in ws[1]}
    for column, values in dropdowns.items():
        validation = DataValidation(type="list", formula1='"' + ",".join(values) + '"', allow_blank=True)
        ws.add_data_validation(validation)
        validation.add(f"{letters[column]}2:{letters[column]}500")
    wb.save(path)


def list_studies(root):
    """Dossiers de premier niveau qui contiennent un ELR : une étude par dossier."""
    return sorted(p for p in Path(root).iterdir() if p.is_dir() and (p / ELR_FILE).exists())


def floors_of(study_dir):
    """Étages présents dans le routage de l'étude (source ou destination), triés."""
    routing = parse_routing(Path(study_dir) / ROUTING_FILE)
    return sorted(set(routing["source_floor"].dropna()) | set(routing["dest_floor"].dropna()))


def write_templates(root):
    """Écrit etudes.xlsx, etages.xlsx et zones.xlsx à partir des dossiers présents."""
    root = Path(root)
    studies = list_studies(root)

    etudes = pd.DataFrame(
        {
            "study_folder": [p.name for p in studies],
            "site_id": [site_from_folder(p.name) for p in studies],
            "split": "",
            "methode": "",
        },
        columns=ETUDES_COLUMNS,
    )
    _write_xlsx(etudes, root / ETUDES_FILE, {"split": SPLITS, "methode": METHODS})

    etages_rows = []
    for p in studies:
        for floor in floors_of(p):
            etages_rows.append({"study_folder": p.name, "etage": floor, "surface_totale_m2": "", "surface_predite_m2": ""})
    _write_xlsx(pd.DataFrame(etages_rows, columns=ETAGES_COLUMNS), root / ETAGES_FILE, {})

        # Zones : une ligne préremplie par étage (étude et étage déjà renseignés).
    # Pour un étage avec plusieurs zones, copier la ligne et compléter zone, surface et environnement.
    zones_rows = [
        {"study_folder": r["study_folder"], "etage": r["etage"], "zone": "", "surface_m2": "", "environnement": ""}
        for r in etages_rows
    ]
    all_floors = sorted({r["etage"] for r in etages_rows})
    _write_xlsx(
        pd.DataFrame(zones_rows, columns=ZONES_COLUMNS),
        root / ZONES_FILE,
        {"environnement": ENVIRONMENTS, "etage": all_floors},
    )

    print(f"{len(studies)} étude(s) listée(s) dans {root / ETUDES_FILE}")
    print(f"{len(etages_rows)} étage(s) à compléter dans {root / ETAGES_FILE}")
    print(f"{len(zones_rows)} ligne(s) de zone préremplie(s) dans {root / ZONES_FILE}")


def check_inputs(etudes, etages, zones):
    """Renvoie la liste des erreurs à corriger avant la construction. Liste vide si tout est bon."""
    errors = []

    for r in etudes.itertuples():
        if r.split not in SPLITS:
            errors.append(f"{r.study_folder} : split « {r.split} » invalide (train ou test attendu)")
        if r.methode not in METHODS:
            errors.append(f"{r.study_folder} : méthode « {r.methode} » invalide (VPLE ou FRT attendu)")
    per_site = etudes.groupby("site_id")["split"].nunique()
    for site in per_site[per_site > 1].index:
        errors.append(f"site « {site} » : ses études sont réparties entre train et test")
    methods = dict(zip(etudes["study_folder"], etudes["methode"]))

    floor_totals = {}
    for r in etages.itertuples():
        if r.study_folder not in methods:
            errors.append(f"{r.study_folder} : étude absente de etudes.xlsx")
            continue
        total = _num(r.surface_totale_m2)
        if total is None or total <= 0:
            errors.append(f"{r.study_folder} étage {r.etage} : surface totale manquante ou invalide")
            continue
        floor_totals[(r.study_folder, r.etage)] = total
        if r.surface_predite_m2:
            pred = _num(r.surface_predite_m2)
            if pred is None:
                errors.append(f"{r.study_folder} étage {r.etage} : surface de prédiction invalide")
            elif pred > total:
                errors.append(f"{r.study_folder} étage {r.etage} : surface de prédiction supérieure à la totale")

    zone_sums = {}
    for r in zones.itertuples():
        key = (r.study_folder, r.etage)
        label = f"{r.study_folder} étage {r.etage} zone « {r.zone} »"
        if r.study_folder not in methods:
            errors.append(f"{label} : étude absente de etudes.xlsx")
            continue
        if key not in floor_totals:
            errors.append(f"{label} : étage absent de etages.xlsx")
            continue
        surface = _num(r.surface_m2)
        if surface is None or surface <= 0:
            errors.append(f"{label} : surface invalide")
            continue
        zone_sums[key] = zone_sums.get(key, 0) + surface

        if methods[r.study_folder] == "VPLE":
            if r.environnement not in ENVIRONMENTS:
                errors.append(f"{label} : environnement « {r.environnement} » inconnu (VPLE)")
        elif r.environnement:
            errors.append(f"{label} : environnement renseigné sur une étude FRT (à laisser vide)")

    for key, total_zones in zone_sums.items():
        if total_zones > floor_totals[key] * 1.05:
            errors.append(
                f"{key[0]} étage {key[1]} : somme des zones ({total_zones:g} m2) "
                f"supérieure à la surface de l'étage ({floor_totals[key]:g} m2)"
            )
    return errors


def study_surfaces(study, methode, etages, zones):
    """Agrégats par étude : surfaces ; pour le VPLE, environnement dominant et part dense par étage."""
    floors = etages[etages["study_folder"] == study]
    study_zones = zones[zones["study_folder"] == study].copy()
    study_zones["surface"] = study_zones["surface_m2"].map(_num)

    totals, predicted, pred_parts = [], [], []
    env_parts, dense_parts = [], []
    for f in floors.itertuples():
        total = _num(f.surface_totale_m2)
        pred = _num(f.surface_predite_m2)
        pred = total if pred is None else pred
        totals.append(total)
        predicted.append(pred)
        pred_parts.append(f"{f.etage}:{pred:g} m2")

        z = study_zones[study_zones["etage"] == f.etage]
        if z.empty or methode != "VPLE":
            continue
        by_env = z.groupby("environnement")["surface"].sum()
        if len(by_env):
            env_parts.append(f"{f.etage}:{by_env.idxmax()}")
        zone_total = z["surface"].sum()
        dense_total = z.loc[z["environnement"] == DENSE_LABEL, "surface"].sum()
        if zone_total > 0:
            dense_parts.append(f"{f.etage}:{100 * dense_total / zone_total:.0f} %")

    result = {
        "surface_totale_m2": round(sum(totals), 2),
        "surface_predite_m2": round(sum(predicted), 2),
        "surface_predite_par_etage": _join(pred_parts),
        "zones_nb": len(study_zones),
    }
    if methode == "VPLE":
        result["environnement_dominant_par_etage"] = _join(env_parts)
        result["pct_dense_rf_par_etage"] = _join(dense_parts)
    return result


def build(root):
    """Construit train/dataset.csv et test/dataset.csv."""
    root = Path(root)
    etudes = _read(root / ETUDES_FILE)
    etages = _read(root / ETAGES_FILE)
    zones = _read(root / ZONES_FILE)

    errors = check_inputs(etudes, etages, zones)
    if errors:
        print("Corrigez ces points avant de construire le corpus :")
        for e in errors:
            print(f"  - {e}")
        return

    rows = []
    for r in etudes.itertuples():
        row = study_row(root / r.study_folder, site_name=r.site_id)
        row["site_id"] = r.site_id
        row["split"] = r.split
        row["methode"] = r.methode
        row.update(study_surfaces(r.study_folder, r.methode, etages, zones))
        rows.append(row)

    df = pd.DataFrame(rows)
    for split in SPLITS:
        out = root / split
        out.mkdir(exist_ok=True)
        part = df[df["split"] == split]
        part.to_csv(out / "dataset.csv", index=False, sep=";", encoding="utf-8-sig")
        print(f"{split} : {len(part)} étude(s) -> {out / 'dataset.csv'}")


def main():
    parser = argparse.ArgumentParser(description="Constitution du corpus d'apprentissage")
    sub = parser.add_subparsers(dest="command", required=True)
    p_template = sub.add_parser("template", help="écrit etudes.xlsx, etages.xlsx et zones.xlsx")
    p_template.add_argument("--root", default="data")
    p_build = sub.add_parser("build", help="construit train/ et test/")
    p_build.add_argument("--root", default="data")
    args = parser.parse_args()

    if args.command == "template":
        write_templates(args.root)
    else:
        build(args.root)


if __name__ == "__main__":
    main()