"""Constitution du corpus : plusieurs études, découpées en train / test par site.

Trois étapes :

1. template : liste les dossiers d'études dans le dossier racine (ex. data/) et écrit
   - etudes.csv : une ligne par étude, avec le site_id pré-rempli ;
   - surfaces_par_etage.csv : une ligne par étude et par étage, à compléter à la main.

2. À la main, dans Excel :
   - etudes.csv : remplir la colonne split (train ou test) ;
   - surfaces_par_etage.csv : remplir surface_m2 et environnement
     (open_space, semi_ouvert ou cloisonne).

3. build : lit tout, vérifie la cohérence, écrit train/dataset.csv et test/dataset.csv.

Règle : toutes les études d'un même site vont du même côté (split au niveau du site).

Usage :
    python -m src.parsing.corpus template --root data
    python -m src.parsing.corpus build --root data

Les fichiers CSV utilisent « ; » comme séparateur, pour s'ouvrir directement dans Excel.
"""

import argparse
import re
from pathlib import Path

import pandas as pd

from .check import ELR_FILE, ROUTING_FILE
from .dataset import _join, study_row
from .routing import parse_routing

ETUDES_FILE = "etudes.csv"
SURFACES_FILE = "surfaces_par_etage.csv"
SPLITS = {"train", "test"}
ENVIRONMENTS = {"open_space", "semi_ouvert", "cloisonne"}

# Suffixe de version en fin de nom de dossier : « HOTEL CELESTE V12-V13 », « HOTEL CELESTE V10 avec parking ».
# Un nom qui ne se termine pas par un numéro de version n'est pas modifié (« CC V2 Villeneuve… » reste tel quel).
TRAILING_VERSION_RE = re.compile(r"(\s+V\d+(-V?\d+)?)+(\s+avec parking)?\s*$", re.IGNORECASE)


def site_from_folder(name):
    """Nom du site à partir du nom du dossier, sans le suffixe de version."""
    return TRAILING_VERSION_RE.sub("", name.replace("_", " ")).strip()


def list_studies(root):
    """Dossiers de premier niveau qui contiennent un ELR : une étude par dossier."""
    return sorted(p for p in Path(root).iterdir() if p.is_dir() and (p / ELR_FILE).exists())


def floors_of(study_dir):
    """Étages présents dans le routage de l'étude (source ou destination), triés."""
    routing = parse_routing(Path(study_dir) / ROUTING_FILE)
    return sorted(set(routing["source_floor"].dropna()) | set(routing["dest_floor"].dropna()))


def write_templates(root):
    """Écrit etudes.csv et surfaces_par_etage.csv à partir des dossiers présents."""
    root = Path(root)
    studies = list_studies(root)
    etudes = pd.DataFrame(
        {
            "study_folder": [p.name for p in studies],
            "site_id": [site_from_folder(p.name) for p in studies],
            "split": "",
        }
    )
    etudes.to_csv(root / ETUDES_FILE, index=False, sep=";", encoding="utf-8-sig")

    rows = []
    for p in studies:
        for floor in floors_of(p):
            rows.append({"study_folder": p.name, "etage": floor, "surface_m2": "", "environnement": ""})
    pd.DataFrame(rows, columns=["study_folder", "etage", "surface_m2", "environnement"]).to_csv(
        root / SURFACES_FILE, index=False, sep=";", encoding="utf-8-sig"
    )
    print(f"{len(studies)} étude(s) listée(s) dans {root / ETUDES_FILE}")
    print(f"{len(rows)} étage(s) à compléter dans {root / SURFACES_FILE}")


def _read(path):
    return pd.read_csv(path, sep=";", encoding="utf-8-sig", dtype=str).fillna("")


def check_inputs(etudes, surfaces):
    """Renvoie la liste des erreurs à corriger avant la construction. Liste vide si tout est bon."""
    errors = []
    bad_split = etudes[~etudes["split"].isin(SPLITS)]
    for r in bad_split.itertuples():
        errors.append(f"{r.study_folder} : split « {r.split} » invalide (train ou test attendu)")
    per_site = etudes.groupby("site_id")["split"].nunique()
    for site in per_site[per_site > 1].index:
        errors.append(f"site « {site} » : ses études sont réparties entre train et test")
    bad_env = surfaces[(surfaces["environnement"] != "") & ~surfaces["environnement"].isin(ENVIRONMENTS)]
    for r in bad_env.itertuples():
        errors.append(f"{r.study_folder} étage {r.etage} : environnement « {r.environnement} » inconnu")
    return errors


def build(root):
    """Construit train/dataset.csv et test/dataset.csv."""
    root = Path(root)
    etudes = _read(root / ETUDES_FILE)
    surfaces = _read(root / SURFACES_FILE)

    errors = check_inputs(etudes, surfaces)
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

        floors = surfaces[surfaces["study_folder"] == r.study_folder]
        surface_values = pd.to_numeric(floors["surface_m2"], errors="coerce")
        complete = len(floors) > 0 and surface_values.notna().all()
        row["surface_total_m2"] = round(float(surface_values.sum()), 2) if complete else None
        row["surface_par_etage"] = _join(
            f"{f.etage}:{f.surface_m2} m2" for f in floors.itertuples() if f.surface_m2
        )
        row["environnement_par_etage"] = _join(
            f"{f.etage}:{f.environnement}" for f in floors.itertuples() if f.environnement
        )
        rows.append(row)

    df = pd.DataFrame(rows)
    for split in sorted(SPLITS):
        out = root / split
        out.mkdir(exist_ok=True)
        part = df[df["split"] == split]
        part.to_csv(out / "dataset.csv", index=False, sep=";", encoding="utf-8-sig")
        print(f"{split} : {len(part)} étude(s) -> {out / 'dataset.csv'}")


def main():
    parser = argparse.ArgumentParser(description="Constitution du corpus train / test")
    sub = parser.add_subparsers(dest="command", required=True)
    p_template = sub.add_parser("template", help="écrit etudes.csv et surfaces_par_etage.csv")
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