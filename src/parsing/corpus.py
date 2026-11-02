"""Constitution du corpus d'apprentissage : une étude par dossier, découpage train / test par site.

Trois étapes :

1. template : liste les dossiers d'études dans le dossier racine (ex. data/) et écrit
   - etudes.xlsx : une ligne par étude (site_id pré-rempli ; split et methode en liste déroulante) ;
   - etages.xlsx : une ligne par étude et par étage (surfaces à saisir) ;
   - zones.xlsx : une ligne par zone (environnement en liste déroulante, VPLE seulement).

2. split (facultatif) : remplit automatiquement la colonne split de etudes.xlsx,
   en tirant au sort des sites entiers pour le test (20 % des études par défaut).

   À la main, dans Excel :
   - etudes.xlsx : methode (VPLE par défaut, à passer à FRT si besoin),
     et split si on ne lance pas la commande split ;
   - etages.xlsx : surface_totale_m2 et surface_predite_m2 (vide = même valeur que la totale) ;
   - zones.xlsx : une ligne par zone, avec sa surface et, pour une étude VPLE, son environnement.
     Pour une étude FRT, les zones ne se renseignent que par leur surface : pas d'environnement.

3. build : vérifie la saisie, calcule les agrégats, écrit train/dataset.csv et test/dataset.csv.

Règles :
- toutes les études d'un même site vont du même côté (split au niveau du site) ;
- une étude qui couvre plusieurs bâtiments (étages nommés « BAT … ») est écartée :
  son ELR est global et ne peut pas être réparti par bâtiment.

Usage :
    python -m src.parsing.corpus template --root data
    python -m src.parsing.corpus split --root data                  (20 % de test, graine 42)
    python -m src.parsing.corpus split --root data --test-ratio 0.25 --seed 7 --force
    python -m src.parsing.corpus build --root data
    python -m src.parsing.corpus build --root data --no-cache      (relit tous les rapports)

Cache : la lecture des rapports de chaque étude est gardée dans data/cache/ et réutilisée
tant que ni les rapports de l'étude ni le code de lecture n'ont changé. Surfaces, split et
méthode sont relus dans data/saisie/ à chaque build : une modification y est prise en compte
immédiatement.
"""

import argparse
import hashlib
import json
import random
import re
import time
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.worksheet.datavalidation import DataValidation

from .check import is_study, study_files
from .dataset import _join, buildings, study_row
from .routing import parse_routing

# Organisation du dossier racine (ex. data/) :
#   data/etudes/  études brutes, un dossier par étude (ELR, rapports, .ibw…)
#   data/saisie/  fichiers à remplir : etudes.xlsx, etages.xlsx, zones.xlsx
#   data/corpus/  corpus produit : train/dataset.csv, test/dataset.csv
#   data/cache/   lecture des rapports déjà faite (une fiche par étude), réutilisée par build
STUDIES_DIR = "etudes"
INPUTS_DIR = "saisie"
OUTPUT_DIR = "corpus"
CACHE_DIR = "cache"

ETUDES_FILE = "etudes.xlsx"
ETAGES_FILE = "etages.xlsx"
ZONES_FILE = "zones.xlsx"


def _dirs(root):
    """Renvoie (dossier des études brutes, dossier de saisie, dossier du corpus)."""
    root = Path(root)
    return root / STUDIES_DIR, root / INPUTS_DIR, root / OUTPUT_DIR

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

# Le nom du site est le nom du dossier, sans ce qui distingue les versions d'une même étude :
# - un numéro final séparé : « SITE A 2 », « SITE_A_3 », « SITE A-2 », « SITE A V12-V13 »,
#   « SITE A V10 avec parking » ;
# - un numéro final collé : « SITE A1 », « SITE A2 » ;
# - un suffixe d'opérateur ou de méthode : « SITE A_BYT », « SITE A_SFR2 », « SITE A_BYT_FRT ».
# Un nom de site qui finit lui-même par un nombre (« BAT 207 ») perd ce nombre : deux sites
# peuvent alors être regroupés, ce qui est sans danger pour le découpage (ils restent du même
# côté). La colonne site_id de etudes.xlsx peut être corrigée à la main si besoin, et la commande
# split signale les noms proches à vérifier.
TRAILING_VERSION_RE = re.compile(
    r"(?:[\s\-]+(?:V|VERSION\s*)?\d+(?:-V?\d+)?)+(?:\s+avec parking)?\s*$", re.IGNORECASE
)
OPERATOR_SUFFIX_RE = re.compile(
    r"(?:[\s\-]+(?:BYT|BT|BOUYGUES|SFR|OFR|ORANGE|FREE|FRT|VPLE)\d*)+\s*$", re.IGNORECASE
)
ATTACHED_NUMBER_RE = re.compile(r"(?<=[A-Za-z])\d+\s*$")


def site_from_folder(name):
    """Nom du site à partir du nom du dossier, sans numéro de version ni suffixe d'opérateur."""
    text = name.replace("_", " ").strip()
    previous = None
    while text != previous:
        previous = text
        for pattern in (TRAILING_VERSION_RE, OPERATOR_SUFFIX_RE, ATTACHED_NUMBER_RE):
            stripped = pattern.sub("", text).strip(" -")
            if stripped:
                text = stripped
    return text


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


INLINE_LIST_MAX = 250  # Excel n'accepte pas plus de 255 caractères dans une liste écrite en clair


def _write_xlsx(df, path, dropdowns):
    """Écrit un tableau Excel ; chaque colonne de « dropdowns » devient une liste déroulante.

    Une liste courte est écrite en clair ; une liste longue (ex. tous les étages du corpus)
    est rangée dans une feuille cachée « listes » et référencée par plage.
    """
    df.to_excel(path, index=False)
    wb = load_workbook(path)
    ws = wb.active
    letters = {cell.value: cell.column_letter for cell in ws[1]}
    last_row = max(len(df) + 200, 500)
    lists_ws = None
    for column, values in dropdowns.items():
        values = [str(v) for v in values]
        inline = '"' + ",".join(values) + '"'
        if len(inline) <= INLINE_LIST_MAX and not any("," in v for v in values):
            formula = inline
        else:
            if lists_ws is None:
                lists_ws = wb.create_sheet("listes")
                lists_ws.sheet_state = "hidden"
            col = lists_ws.max_column + 1 if lists_ws.max_row > 1 or lists_ws["A1"].value else 1
            for i, v in enumerate(values, start=1):
                lists_ws.cell(row=i, column=col, value=v)
            letter = lists_ws.cell(row=1, column=col).column_letter
            formula = f"listes!${letter}$1:${letter}${len(values)}"
        validation = DataValidation(type="list", formula1=formula, allow_blank=True)
        ws.add_data_validation(validation)
        validation.add(f"{letters[column]}2:{letters[column]}{last_row}")
    wb.save(path)


def _merge_existing(new, path, keys, keep):
    """Reprend dans « new » les valeurs déjà saisies dans le fichier existant (même clé).

    keys : colonnes qui identifient une ligne ; keep : colonnes saisies à la main à conserver.
    Une valeur vide dans l'ancien fichier ne remplace pas la valeur par défaut.
    """
    if not Path(path).exists():
        return new
    old = _read(path)
    if not set(keys + keep).issubset(old.columns):
        return new
    old = old.drop_duplicates(keys).set_index(keys)
    merged = new.copy()
    for i, row in merged.iterrows():
        key = tuple(row[k] for k in keys) if len(keys) > 1 else row[keys[0]]
        if key in old.index:
            for column in keep:
                value = old.at[key, column]
                if value != "":
                    merged.at[i, column] = value
    return merged


EXCLUDED_DIRS = {"train", "test"}


def list_studies(root):
    """Dossiers qui contiennent un ELR (Excel ou PDF), à n'importe quelle profondeur sous root.

    Renvoie les chemins relatifs à root (« ETUDE_A/ETUDE A » si l'étude est
    dans un sous-dossier, comme après extraction d'un zip).
    """
    root = Path(root)
    found = []
    for d in sorted(p for p in root.rglob("*") if p.is_dir()):
        rel = d.relative_to(root)
        if rel.parts and rel.parts[0] in EXCLUDED_DIRS:
            continue
        if is_study(d):
            found.append(rel.as_posix())
    return found


def floors_of(study_dir):
    """Étages présents dans le routage de l'étude (source ou destination), triés."""
    routing = parse_routing(study_files(study_dir)["routing"])
    return sorted(set(routing["source_floor"].dropna()) | set(routing["dest_floor"].dropna()))


def write_templates(root):
    """Écrit etudes.xlsx, etages.xlsx et zones.xlsx à partir des dossiers présents.

    Si les fichiers existent déjà, la saisie est conservée : site_id, split et methode pour
    chaque étude, surfaces pour chaque étage, toutes les lignes de zones déjà présentes.
    Seules les nouvelles études et les nouveaux étages sont ajoutés.
    """
    studies_dir, inputs_dir, _ = _dirs(root)
    if not studies_dir.is_dir():
        print(f"Dossier des études introuvable : {studies_dir} (y ranger un dossier par étude)")
        return
    inputs_dir.mkdir(parents=True, exist_ok=True)
    floors, incomplete = {}, []
    for s in list_studies(studies_dir):
        try:
            floors[s] = floors_of(studies_dir / s)
        except (FileNotFoundError, NotImplementedError) as e:
            incomplete.append((s, str(e)))
    excluded = [s for s, f in floors.items() if len(buildings(f)) > 1]
    studies = [s for s in floors if s not in excluded]
    for s, reason in incomplete:
        print(f"Étude ignorée ({reason}) : {s}")
    for s in excluded:
        print(f"Étude écartée (plusieurs bâtiments : {', '.join(buildings(floors[s]))}) : {s}")

    etudes = pd.DataFrame(
        {
            "study_folder": studies,
            # Site : nom du dossier de premier niveau, sans suffixe de version.
            "site_id": [site_from_folder(s.split("/")[0]) for s in studies],
            "split": "",
            # VPLE par défaut (cas le plus courant) ; passer à FRT à la main si besoin.
            "methode": "VPLE",
        },
        columns=ETUDES_COLUMNS,
    )
    etudes_path = inputs_dir / ETUDES_FILE
    known = set(_read(etudes_path)["study_folder"]) if etudes_path.exists() else set()
    etudes = _merge_existing(etudes, etudes_path, ["study_folder"], ["site_id", "split", "methode"])
    _write_xlsx(etudes, etudes_path, {"split": SPLITS, "methode": METHODS})

    etages_rows = []
    for s in studies:
        for floor in floors[s]:
            etages_rows.append({"study_folder": s, "etage": floor, "surface_totale_m2": "", "surface_predite_m2": ""})
    etages = pd.DataFrame(etages_rows, columns=ETAGES_COLUMNS)
    etages = _merge_existing(
        etages, inputs_dir / ETAGES_FILE, ["study_folder", "etage"], ["surface_totale_m2", "surface_predite_m2"]
    )
    _write_xlsx(etages, inputs_dir / ETAGES_FILE, {})

    # Zones : on garde toutes les lignes déjà saisies (études encore présentes) et on ajoute
    # une ligne préremplie pour chaque étage qui n'en a pas encore.
    # Pour un étage avec plusieurs zones, copier la ligne et compléter zone, surface et environnement.
    zones_path = inputs_dir / ZONES_FILE
    kept = pd.DataFrame(columns=ZONES_COLUMNS)
    if zones_path.exists():
        old_zones = _read(zones_path)
        if set(ZONES_COLUMNS).issubset(old_zones.columns):
            kept = old_zones[old_zones["study_folder"].isin(studies)][ZONES_COLUMNS]
    covered = set(zip(kept["study_folder"], kept["etage"]))
    added = [
        {"study_folder": r["study_folder"], "etage": r["etage"], "zone": "", "surface_m2": "", "environnement": ""}
        for r in etages_rows
        if (r["study_folder"], r["etage"]) not in covered
    ]
    zones = pd.concat([kept, pd.DataFrame(added, columns=ZONES_COLUMNS)], ignore_index=True)
    zones = zones.sort_values(["study_folder", "etage"], kind="stable").reset_index(drop=True)
    all_floors = sorted({r["etage"] for r in etages_rows})
    _write_xlsx(zones, zones_path, {"environnement": ENVIRONMENTS, "etage": all_floors})

    new_studies = [s for s in studies if s not in known]
    print(f"{len(studies)} étude(s) listée(s) dans {etudes_path}" + (f", dont {len(new_studies)} nouvelle(s)" if known else ""))
    print(f"{len(etages)} étage(s) dans {inputs_dir / ETAGES_FILE}")
    print(f"{len(zones)} ligne(s) de zone dans {zones_path} ({len(added)} ajoutée(s))")


def assign_splits(etudes, test_ratio=0.2, seed=42, force=False):
    """Renvoie une copie de etudes avec la colonne split remplie, site par site.

    - Les sites sont tirés au sort (graine fixe : même résultat à chaque lancement).
    - On ajoute des sites au test jusqu'à atteindre test_ratio × nombre d'études.
    - Toutes les études d'un site reçoivent la même valeur.
    - Sans force, un site dont une étude a déjà un split garde ce split.
    - S'il y a au moins deux sites, il y en a au moins un de chaque côté.
    """
    df = etudes.copy()
    sizes = df.groupby("site_id").size()
    if force:
        fixed = {}
    else:
        done = df[df["split"].isin(SPLITS)]
        fixed = done.groupby("site_id")["split"].first().to_dict()

    free_sites = sorted(set(sizes.index) - set(fixed))
    random.Random(seed).shuffle(free_sites)

    target = round(len(df) * test_ratio)
    n_test = sum(int(sizes[s]) for s, v in fixed.items() if v == "test")
    assignment = dict(fixed)
    for site in free_sites:
        if n_test < target:
            assignment[site] = "test"
            n_test += int(sizes[site])
        else:
            assignment[site] = "train"

    values = set(assignment.values())
    if len(assignment) >= 2 and values == {"train"} and free_sites:
        assignment[free_sites[0]] = "test"
    elif len(assignment) >= 2 and values == {"test"} and free_sites:
        assignment[free_sites[-1]] = "train"

    df["split"] = df["site_id"].map(assignment)
    return df


def split_studies(root, test_ratio=0.2, seed=42, force=False):
    """Remplit la colonne split de etudes.xlsx et affiche le résultat."""
    _, inputs_dir, _ = _dirs(root)
    etudes = _read(inputs_dir / ETUDES_FILE)
    result = assign_splits(etudes, test_ratio, seed, force)
    _write_xlsx(result, inputs_dir / ETUDES_FILE, {"split": SPLITS, "methode": METHODS})

    for split in SPLITS:
        part = result[result["split"] == split]
        print(f"{split} : {len(part)} étude(s), {part['site_id'].nunique()} site(s)")
    test_sites = sorted(set(result.loc[result["split"] == "test", "site_id"]))
    print("Sites en test :", ", ".join(test_sites) if test_sites else "aucun")

    close = similar_sites(result)
    if close:
        print("\nNoms de sites proches, à vérifier (même premier mot) :")
        for word, sites in close:
            print(f"  {word} : " + " | ".join(sites))
        print(
            "Si deux de ces noms désignent le même site, mettez le même site_id dans etudes.xlsx,"
            " puis relancez : python -m src.parsing.corpus split --root data --force"
        )


def similar_sites(etudes):
    """Groupes de site_id différents qui commencent par le même mot (ex. « ZENITH NANCY » / « ZENITH SOLID »)."""
    groups = {}
    for site in sorted(set(etudes["site_id"])):
        first = re.split(r"[\s\-]+", site.strip().upper())[0]
        groups.setdefault(first, []).append(site)
    return [(word, sites) for word, sites in sorted(groups.items()) if len(sites) > 1]


def _empty_zone(r):
    """Ligne de zone préremplie et laissée vide (seuls l'étude et l'étage sont renseignés)."""
    return not (r.zone or r.surface_m2 or r.environnement)


def check_inputs(etudes, etages, zones):
    """Renvoie (erreurs, avertissements).

    Erreurs : valeurs invalides, à corriger avant la construction.
    Avertissements : surfaces non encore saisies ; la construction se fait quand même,
    avec les colonnes de surface vides pour l'étude concernée.
    """
    errors, warnings = [], []

    for r in etudes.itertuples():
        if r.split not in SPLITS:
            errors.append(f"{r.study_folder} : split « {r.split} » invalide (train ou test attendu)")
        if r.methode not in METHODS:
            errors.append(f"{r.study_folder} : méthode « {r.methode} » invalide (VPLE ou FRT attendu)")
    per_site = etudes.groupby("site_id")["split"].nunique()
    for site in per_site[per_site > 1].index:
        errors.append(f"site « {site} » : ses études sont réparties entre train et test")
    methods = dict(zip(etudes["study_folder"], etudes["methode"]))

    floor_totals, known_floors, missing = {}, set(), {}
    for r in etages.itertuples():
        if r.study_folder not in methods:
            errors.append(f"{r.study_folder} : étude absente de etudes.xlsx")
            continue
        known_floors.add((r.study_folder, r.etage))
        if not r.surface_totale_m2:
            missing[r.study_folder] = missing.get(r.study_folder, 0) + 1
            continue
        total = _num(r.surface_totale_m2)
        if total is None or total <= 0:
            errors.append(f"{r.study_folder} étage {r.etage} : surface totale invalide")
            continue
        floor_totals[(r.study_folder, r.etage)] = total
        if r.surface_predite_m2:
            pred = _num(r.surface_predite_m2)
            if pred is None:
                errors.append(f"{r.study_folder} étage {r.etage} : surface de prédiction invalide")
            elif pred > total:
                errors.append(f"{r.study_folder} étage {r.etage} : surface de prédiction supérieure à la totale")

    for study, n in missing.items():
        warnings.append(f"{study} : surface totale non saisie sur {n} étage(s), surfaces laissées vides")

    zone_sums = {}
    for r in zones.itertuples():
        if _empty_zone(r):
            continue
        key = (r.study_folder, r.etage)
        label = f"{r.study_folder} étage {r.etage} zone « {r.zone} »"
        if r.study_folder not in methods:
            errors.append(f"{label} : étude absente de etudes.xlsx")
            continue
        if key not in known_floors:
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
        if key in floor_totals and total_zones > floor_totals[key] * 1.05:
            errors.append(
                f"{key[0]} étage {key[1]} : somme des zones ({total_zones:g} m2) "
                f"supérieure à la surface de l'étage ({floor_totals[key]:g} m2)"
            )
    return errors, warnings


def study_surfaces(study, methode, etages, zones):
    """Agrégats par étude : surfaces ; pour le VPLE, environnement dominant et part dense par étage."""
    floors = etages[etages["study_folder"] == study]
    study_zones = zones[zones["study_folder"] == study].copy()
    study_zones["surface"] = study_zones["surface_m2"].map(_num)
    study_zones = study_zones[study_zones["surface"].notna()]

    totals, predicted, pred_parts = [], [], []
    env_parts, dense_parts = [], []
    for f in floors.itertuples():
        total = _num(f.surface_totale_m2)
        pred = _num(f.surface_predite_m2)
        pred = total if pred is None else pred
        totals.append(total)
        predicted.append(pred)
        if pred is not None:
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

    # Une somme incomplète serait fausse : vide si un étage n'a pas de surface.
    complete = len(totals) > 0 and all(t is not None for t in totals)
    result = {
        "surface_totale_m2": round(sum(totals), 2) if complete else None,
        "surface_predite_m2": round(sum(predicted), 2) if complete else None,
        "surface_predite_par_etage": _join(pred_parts),
        "zones_nb": len(study_zones),
    }
    if methode == "VPLE":
        result["environnement_dominant_par_etage"] = _join(env_parts)
        result["pct_dense_rf_par_etage"] = _join(dense_parts)
    return result


def _code_signature():
    """Empreinte du code de lecture : si le code change, le cache est refait."""
    digest = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def _study_signature(study_dir):
    """Empreinte des rapports de l'étude (nom, taille, date) : si un fichier change, le cache est refait."""
    digest = hashlib.sha256()
    for path in sorted(Path(study_dir).iterdir()):
        if path.is_file() and path.suffix.lower() in {".pdf", ".xlsx"}:
            stat = path.stat()
            digest.update(f"{path.name}|{stat.st_size}|{int(stat.st_mtime)}".encode())
    return digest.hexdigest()[:16]


def _json_default(value):
    """Convertit les nombres numpy en nombres Python pour l'écriture JSON."""
    return value.item() if hasattr(value, "item") else str(value)


def cached_study_row(study_dir, folder, site_name, cache_dir, code_signature, use_cache=True):
    """Ligne de l'étude lue dans le cache si les rapports et le code n'ont pas changé, sinon relue.

    Renvoie (ligne, True si elle vient du cache). Le cache ne contient que ce qui est lu
    dans les rapports : surfaces, split et méthode sont ajoutés ensuite, à chaque build.
    """
    key = f"{code_signature}-{_study_signature(study_dir)}"
    path = Path(cache_dir) / (re.sub(r"[^\w\-]+", "_", folder) + ".json")
    if use_cache and path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("key") == key:
                row = data["row"]
                row["site"] = site_name
                return row, True
        except (ValueError, KeyError):
            pass  # fiche illisible : on relit l'étude
    row = study_row(study_dir, site_name=site_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"key": key, "row": row}, ensure_ascii=False, default=_json_default), encoding="utf-8")
    return row, False


def build(root, use_cache=True):
    """Construit train/dataset.csv et test/dataset.csv."""
    studies_dir, inputs_dir, output_dir = _dirs(root)
    cache_dir = Path(root) / CACHE_DIR
    code_signature = _code_signature()
    etudes = _read(inputs_dir / ETUDES_FILE)
    etages = _read(inputs_dir / ETAGES_FILE)
    zones = _read(inputs_dir / ZONES_FILE)

    errors, warnings = check_inputs(etudes, etages, zones)
    if errors:
        print("Corrigez ces points avant de construire le corpus :")
        for e in errors:
            print(f"  - {e}")
        return
    missing_surfaces = [w for w in warnings if "surface totale non saisie" in w]
    for w in warnings:
        if w not in missing_surfaces:
            print(f"Avertissement : {w}")
    if missing_surfaces:
        print(
            f"Avertissement : surfaces non saisies (en tout ou partie) pour {len(missing_surfaces)} étude(s) ;"
            " leurs colonnes de surface resteront vides."
        )

    n = len(etudes)
    print(f"Lecture de {n} étude(s) (la première lecture des gros rapports peut prendre plusieurs minutes) :")
    rows, start, from_cache = [], time.time(), 0
    for i, r in enumerate(etudes.itertuples(), start=1):
        print(f"  [{i}/{n}] {r.study_folder} ...", end=" ", flush=True)
        t0 = time.time()
        try:
            row, cached = cached_study_row(
                studies_dir / r.study_folder, r.study_folder, r.site_id, cache_dir, code_signature, use_cache
            )
        except Exception as e:  # une étude illisible ne doit pas bloquer les autres
            print(f"ignorée ({type(e).__name__} : {e})", flush=True)
            continue
        if row["buildings_count"] > 1:
            print(f"écartée (plusieurs bâtiments : {row['buildings_list']})", flush=True)
            continue
        from_cache += cached
        print("ok (cache)" if cached else f"ok ({time.time() - t0:.0f} s)", flush=True)
        row = {"study_folder": r.study_folder, **row}  # identifiant unique de l'étude (chemin sous etudes/)
        row["site_id"] = r.site_id
        row["split"] = r.split
        row["methode"] = r.methode
        row.update(study_surfaces(r.study_folder, r.methode, etages, zones))
        rows.append(row)

    print(f"{len(rows)} étude(s) lue(s) en {(time.time() - start) / 60:.1f} min, dont {from_cache} depuis le cache")
    df = pd.DataFrame(rows)
    for split in SPLITS:
        out = output_dir / split
        out.mkdir(parents=True, exist_ok=True)
        part = df[df["split"] == split]
        part.to_csv(out / "dataset.csv", index=False, sep=";", encoding="utf-8-sig")
        print(f"{split} : {len(part)} étude(s) -> {out / 'dataset.csv'}")


def main():
    parser = argparse.ArgumentParser(description="Constitution du corpus d'apprentissage")
    sub = parser.add_subparsers(dest="command", required=True)
    p_template = sub.add_parser("template", help="écrit etudes.xlsx, etages.xlsx et zones.xlsx")
    p_template.add_argument("--root", default="data")
    p_split = sub.add_parser("split", help="remplit la colonne split de etudes.xlsx, site par site")
    p_split.add_argument("--root", default="data")
    p_split.add_argument("--test-ratio", type=float, default=0.2, help="part des études en test (défaut 0.2)")
    p_split.add_argument("--seed", type=int, default=42, help="graine du tirage (défaut 42)")
    p_split.add_argument("--force", action="store_true", help="refait le tirage même pour les splits déjà remplis")
    p_build = sub.add_parser("build", help="construit train/ et test/")
    p_build.add_argument("--root", default="data")
    p_build.add_argument("--no-cache", action="store_true", help="relit tous les rapports sans utiliser le cache")
    args = parser.parse_args()

    if args.command == "template":
        write_templates(args.root)
    elif args.command == "split":
        split_studies(args.root, args.test_ratio, args.seed, args.force)
    else:
        build(args.root, use_cache=not args.no_cache)


if __name__ == "__main__":
    main()