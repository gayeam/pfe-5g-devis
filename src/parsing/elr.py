"""Lecture de l'Equipment List Report (ELR) livré par iBwave, en Excel ou en PDF.

L'ELR a une ligne par modèle : type, fabricant, modèle, description,
numéro d'inventaire et quantité. La quantité est un nombre, sauf pour les
câbles où elle est écrite avec son unité (« 1245,22 m »).

Le rapport est découpé en pages : chaque page répète l'en-tête (Type, Model, Qty…)
et se termine par un pied de page « Created on … Page n / N ». On ignore ces lignes
et on continue jusqu'à la fin du fichier.
"""

from pathlib import Path

import openpyxl
import pandas as pd
import pdfplumber

from .utils import clean, split_unit

REQUIRED = {"Type", "Model", "Qty"}
COLUMNS = ["type", "manufacturer", "model", "description", "inventory", "qty", "unit"]


def _pdf_cell(value):
    """Cellule PDF sur plusieurs lignes : « 43M43MS12-\\n0500FFP » -> « 43M43MS12-0500FFP »."""
    if value is None:
        return ""
    return clean(str(value).replace("-\n", "-"))


def _make_row(cells, cols):
    """Construit une ligne de l'ELR à partir des cellules et de l'index des colonnes. None si pas de modèle."""

    def get(name):
        i = cols.get(name)
        return cells[i] if i is not None and i < len(cells) else ""

    model = get("Model")
    if not model:
        return None
    qty, unit = split_unit(get("Qty"))
    return {
        "type": get("Type"),
        "manufacturer": get("Manufacturer"),
        "model": model,
        "description": get("Description"),
        "inventory": get("Inventory#"),
        "qty": qty,
        "unit": unit,
    }


def _is_header(cells):
    return REQUIRED.issubset(cells)


def _is_footer(cells):
    first = next((c for c in cells if c), "")
    return first.lower().startswith("created on")


def _parse_excel(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    rows, cols = [], None
    for ws in wb.worksheets:
        for raw in ws.iter_rows(values_only=True):
            cells = [clean(v) for v in raw]
            if _is_header(cells):
                cols = {name: cells.index(name) for name in cells if name}
                continue
            if cols is None or _is_footer(cells):
                continue
            row = _make_row(cells, cols)
            if row:
                rows.append(row)
    if cols is None:
        raise ValueError(f"En-tête ELR introuvable dans {path} (colonnes Type, Model, Qty attendues).")
    return rows


def _parse_pdf(path):
    rows, cols = [], None
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for raw in table:
                    cells = [_pdf_cell(v) for v in raw]
                    if _is_header(cells):
                        cols = {name: cells.index(name) for name in cells if name}
                        continue
                    if cols is None or _is_footer(cells):
                        continue
                    row = _make_row(cells, cols)
                    if row:
                        rows.append(row)
    if cols is None:
        raise ValueError(f"En-tête ELR introuvable dans {path} (colonnes Type, Model, Qty attendues).")
    return rows


def parse_elr(path):
    """Renvoie un DataFrame : une ligne par modèle du bordereau (Excel ou PDF selon l'extension)."""
    path = Path(path)
    rows = _parse_pdf(path) if path.suffix.lower() == ".pdf" else _parse_excel(path)
    return pd.DataFrame(rows, columns=COLUMNS)