"""Lecture du rapport « Area Report » (iBwave, menu Reports > Area), en PDF ou en export Excel.

Le rapport donne, par bâtiment et par étage :
- Plan area (Sq. m) : surface du plan de l'étage ;
- Pred area (Sq. m) : surface de prédiction (la partie à couvrir).
Il se termine par des lignes de total (« Total Floors », « Overall Project »), ignorées ici.

Exemple de ligne : « Building 1 | RDC | 8816,18 | 8735,46 ». Le nom du bâtiment n'est écrit
que sur la première ligne de chaque bâtiment (cellule fusionnée) : on le reporte sur les suivantes.
"""

import re
from pathlib import Path

import openpyxl
import pandas as pd
import pdfplumber

from .utils import clean, to_float

COLUMNS = ["batiment", "etage", "surface_plan_m2", "surface_predite_m2"]
# Ligne de total, même collée à un autre texte (« DA_DE_DB_E Overall Project »).
TOTAL_RE = re.compile(r"total floors|overall project|^total\b", re.IGNORECASE)
BUILDING_RE = re.compile(r"^(building|bâtiment|batiment|bat)\b", re.IGNORECASE)
NUMBER_RE = re.compile(r"^-?\d[\d\s\xa0 ]*(?:[.,]\d+)?$")
# Ligne de texte : « [Building 1] RDC 8816,18 8735,46 »
# En-tête commun aux rapports iBwave : « Project name: X Design company: … », « Project creation date: 03/08/2026 ».
PROJECT_NAME_RE = re.compile(r"Project name:\s*(.*?)\s*(?:Design company:|$)", re.IGNORECASE | re.MULTILINE)
PROJECT_DATE_RE = re.compile(r"Project creation date:\s*(\d{1,2}/\d{1,2}/\d{2,4})", re.IGNORECASE)
TEXT_LINE_RE = re.compile(
    r"^(?:(?P<building>(?:Building|Bâtiment|Batiment)\s+\S+)\s+)?(?P<floor>.+?)\s+"
    r"(?P<plan>\d[\d\s]*,\d+)\s+(?P<pred>\d[\d\s]*,\d+)$",
    re.IGNORECASE,
)


def _is_number(text):
    return bool(text) and bool(NUMBER_RE.match(text))


def _rows_from_table(table_rows):
    """Lignes d'un tableau PDF à 4 colonnes : bâtiment | étage | surface plan | surface prédite.

    Lecture par position : un étage peut lui-même s'appeler « BAT 43S R1 ».
    La cellule bâtiment n'est remplie que sur la première ligne de chaque bâtiment.
    """
    rows, building = [], ""
    for cells in table_rows:
        if len(cells) < 4:
            continue
        label_building, floor, plan, pred = cells[0], cells[1], cells[-2], cells[-1]
        if not (_is_number(plan) and _is_number(pred)):
            continue
        if TOTAL_RE.search(f"{label_building} {floor}"):
            continue
        if label_building:
            building = label_building
        if not floor:
            continue
        rows.append(
            {
                "batiment": building or "Building 1",
                "etage": floor,
                "surface_plan_m2": to_float(plan),
                "surface_predite_m2": to_float(pred),
            }
        )
    return rows


def _rows_from_cells(lines_of_cells):
    """Lignes de cellules (non vides, dans l'ordre) -> lignes du rapport (export Excel)."""
    rows, building = [], ""
    for cells in lines_of_cells:
        cells = [c for c in cells if c]
        if len(cells) < 3 or not (_is_number(cells[-1]) and _is_number(cells[-2])):
            continue
        labels = cells[:-2]
        if any(TOTAL_RE.search(label) for label in labels):
            continue
        if len(labels) >= 2:
            building, floor = labels[0], labels[-1]
        elif BUILDING_RE.match(labels[0]):
            continue  # ligne de bâtiment sans étage
        else:
            floor = labels[0]
        rows.append(
            {
                "batiment": building or "Building 1",
                "etage": floor,
                "surface_plan_m2": to_float(cells[-2]),
                "surface_predite_m2": to_float(cells[-1]),
            }
        )
    return rows


def _norm(text):
    return re.sub(r"[\s_\-]+", " ", str(text)).strip().casefold() if text else None


def report_header(path):
    """Nom et date de création du projet iBwave lus dans l'en-tête d'un rapport (PDF ou Excel).

    Renvoie {"nom": …, "date": …} ; une valeur vaut None si elle n'a pas pu être lue.
    """
    path = Path(path)
    name = date = None
    try:
        if path.suffix.lower() == ".xlsx":
            ws = openpyxl.load_workbook(path, read_only=True, data_only=True).worksheets[0]
            for raw in ws.iter_rows(max_row=20, values_only=True):
                cells = [clean(v) for v in raw if v not in (None, "")]
                for i, cell in enumerate(cells[:-1]):
                    if cell.lower().startswith("project name"):
                        name = name or cells[i + 1]
                    elif cell.lower().startswith("project creation date"):
                        date = date or cells[i + 1].split()[0]
        else:
            with pdfplumber.open(path) as pdf:
                text = pdf.pages[0].extract_text() or "" if pdf.pages else ""
            m = PROJECT_NAME_RE.search(text)
            name = m.group(1) if m and m.group(1) else None
            m = PROJECT_DATE_RE.search(text)
            date = m.group(1) if m else None
    except Exception:  # en-tête illisible : la concordance ne pourra pas être vérifiée
        pass
    return {"nom": name, "date": date}


def same_project(header_a, header_b):
    """True si les deux en-têtes désignent le même projet, False s'ils diffèrent,
    None si on ne peut pas le dire (nom absent d'un des deux rapports). Seul le nom est comparé."""
    name_a, name_b = _norm(header_a["nom"]), _norm(header_b["nom"])
    if not name_a or not name_b:
        return None
    return name_a == name_b


def _pdf_rows(path):
    with pdfplumber.open(path) as pdf:
        table_cells, text_lines = [], []
        for page in pdf.pages:
            for table in page.extract_tables():
                table_cells.extend([clean(c) for c in raw] for raw in table)
            text_lines.extend((page.extract_text() or "").splitlines())
    rows = _rows_from_table(table_cells)
    if rows:
        return rows
    # À défaut de tableau reconnu, lecture ligne par ligne du texte.
    rows, building = [], ""
    for line in text_lines:
        m = TEXT_LINE_RE.match(clean(line))
        if not m or TOTAL_RE.search(m["floor"]):
            continue
        building = m["building"] or building
        rows.append(
            {
                "batiment": building or "Building 1",
                "etage": m["floor"],
                "surface_plan_m2": to_float(m["plan"]),
                "surface_predite_m2": to_float(m["pred"]),
            }
        )
    return rows


def _excel_rows(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    lines = []
    for ws in wb.worksheets:
        for raw in ws.iter_rows(values_only=True):
            lines.append([clean(v) for v in raw if v not in (None, "")])
    return _rows_from_cells(lines)


def parse_area_report(path):
    """Renvoie un DataFrame : une ligne par bâtiment et par étage, avec les deux surfaces (m²)."""
    path = Path(path)
    rows = _excel_rows(path) if path.suffix.lower() == ".xlsx" else _pdf_rows(path)
    df = pd.DataFrame(rows, columns=COLUMNS)
    return df.drop_duplicates(["batiment", "etage"]).reset_index(drop=True)