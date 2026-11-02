"""Lecture du rapport « Antennas Report » (iBwave), en PDF ou en export Excel.

Le rapport contient :
- un tableau : une ligne par élément rayonnant et par système (opérateur, bande, techno).
  L'identifiant est « ANTn » pour une antenne passive, mais peut être « MCn » ou autre
  pour une unité distante à antenne intégrée (DAS actif).
  Selon la version d'iBwave, le tableau a 8 colonnes (sans hauteur) ou 12 ;
  on lit les colonnes communes et on laisse vides les autres ;
- une légende « System legend » : une entrée par opérateur et par système
  (techno, bande, canal, secteurs, nombre de sources). C'est la source du nom
  des opérateurs. Elle peut manquer (certains rapports 2023).

Le rapport peut être partiel (sélection d'antennes) : le nombre d'antennes de l'ELR
fait foi pour les quantités.

Le PDF est lu une seule fois (tableau et légende), car certains rapports font
plusieurs centaines de pages.
"""

import re
from pathlib import Path

import openpyxl
import pandas as pd
import pdfplumber

from .utils import clean, to_float

# Identifiant d'élément rayonnant : lettres puis chiffres (ANT12, MC3, LRN4…).
ELEMENT_ID_RE = re.compile(r"^[A-Za-z][A-Za-z_\-]*\d+$")
SUMMARY_SYSTEMS = {"All systems", "Selected systems"}

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

LEGEND_COLUMNS = [
    "operator",
    "operator_raw",
    "technology",
    "generation",
    "band_label",
    "channel",
    "duplex",
    "bandwidth",
    "band",
    "sectors",
    "n_sources",
]

TECHNOLOGIES = r"GSM|HSPA PLUS|HSPA\+?|WCDMA|UMTS|LTE-A|LTE|5G NR|NR"

# Début d'une entrée de légende : « BOUYGUES / LTE / … ».
ENTRY_START_RE = re.compile(rf"^[^/]+? / (?:{TECHNOLOGIES}) / ")

# Entrée complète, par exemple :
# « BYT / LTE / 1800 MHz - DCS / FDD - 20 MHz - Band 3 / Sector number: 1 / Nb. of channels: 1 / Nb. of sources: 1 »
# « BOUYGUES / GSM / 900 MHz - GSM / E-GSM900 / Sector number: 1 / 1 / Nb. of channels: 1 / Nb. of sources: 1 »
ENTRY_RE = re.compile(
    rf"^(?P<operator>[^/]+?) / (?P<technology>{TECHNOLOGIES}) / (?P<band_label>[^/]+?) / "
    r"(?P<channel>[^/]+?) / Sector number:*\s*(?P<sectors>[\d /]*?)\s*/ "
    r"Nb\. of channels:\s*\d+\s*/ Nb\. of sources:\s*(?P<sources>\d+)"
)

CHANNEL_RE = re.compile(r"^(?P<duplex>FDD|TDD) - (?P<bandwidth>[\d.,]+ MHz) - (?:Band )?(?P<band>\S+)")

GENERATION = {
    "GSM": "2G",
    "HSPA": "3G",
    "HSPA+": "3G",
    "HSPA PLUS": "3G",
    "WCDMA": "3G",
    "UMTS": "3G",
    "LTE": "4G",
    "LTE-A": "4G",
    "5G NR": "5G",
    "NR": "5G",
}

# Noms d'opérateurs normalisés (abréviations et variantes vues dans les rapports).
OPERATOR_ALIASES = {
    "BYT": "BOUYGUES",
    "BT": "BOUYGUES",
    "BOUYGUES": "BOUYGUES",
    "BOUYGUES TELECOM": "BOUYGUES",
    "OFR": "ORANGE",
    "ORANGE": "ORANGE",
    "SFR": "SFR",
    "FREE": "FREE",
    "FREE MOBILE": "FREE",
}


def normalize_operator(name):
    key = clean(name).upper()
    return OPERATOR_ALIASES.get(key, key)


def _num(cells, index):
    """Nombre de la cellule à cet index, ou None si la colonne n'existe pas dans ce format."""
    return to_float(cells[index]) if len(cells) > index else None


def _antenna_row(cells):
    if len(cells) < 3 or not ELEMENT_ID_RE.match(cells[0]) or not cells[2]:
        return None
    return {
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


def _legend_entries(lines):
    """Regroupe les lignes de texte en entrées de légende (une entrée peut tenir sur deux lignes)."""
    entries, buffer = [], None
    for line in lines:
        line = clean(line)
        if buffer is None:
            if ENTRY_START_RE.match(line):
                buffer = line
        else:
            buffer = f"{buffer} {line}"
        if buffer is not None and "Nb. of sources" in buffer:
            entries.append(buffer)
            buffer = None
    return entries


def _legend_row(entry):
    m = ENTRY_RE.match(entry)
    if not m:
        return None
    channel = m["channel"].strip()
    c = CHANNEL_RE.match(channel)
    if c:
        duplex, bandwidth, band = c["duplex"], c["bandwidth"], c["band"]
    else:
        duplex = None
        bw = re.search(r"[\d.,]+ MHz", channel)
        bandwidth = bw.group(0) if bw else None
        band = channel.split(" ")[0]
    return {
        "operator": normalize_operator(m["operator"]),
        "operator_raw": m["operator"].strip(),
        "technology": m["technology"],
        "generation": GENERATION.get(m["technology"]),
        "band_label": m["band_label"].strip(),
        "channel": channel,
        "duplex": duplex,
        "bandwidth": bandwidth,
        "band": band,
        "sectors": m["sectors"].strip(),
        "n_sources": int(m["sources"]),
    }


def _pdf_report(path):
    """Lignes d'antennes et lignes de texte (pour la légende) d'un rapport PDF."""
    rows, lines = [], []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for raw in table:
                    row = _antenna_row([clean(c) for c in raw])
                    if row:
                        rows.append(row)
            text = page.extract_text() or ""
            if " / " in text and "Nb. of sources" in text:
                lines.extend(text.splitlines())
    return rows, lines


def _excel_report(path):
    """Lignes d'antennes et lignes de texte (pour la légende) d'un export Excel.

    L'export a des cellules fusionnées : on ne garde que les cellules non vides, dans
    l'ordre, ce qui redonne les colonnes du PDF. Chaque entrée de légende tient dans
    une seule cellule.
    """
    rows, lines = [], []
    wb = openpyxl.load_workbook(path, data_only=True)
    for ws in wb.worksheets:
        for raw in ws.iter_rows(values_only=True):
            cells = [clean(v) for v in raw if v not in (None, "")]
            if not cells:
                continue
            row = _antenna_row(cells)
            if row:
                rows.append(row)
            elif len(cells) == 1:
                lines.append(cells[0])
    return rows, lines


def parse_antenna_report(path):
    """Lit le rapport (PDF ou export Excel) en une passe. Renvoie (tableau des antennes, légende)."""
    path = Path(path)
    rows, lines = _excel_report(path) if path.suffix.lower() == ".xlsx" else _pdf_report(path)

    legend_rows, seen = [], set()
    for entry in _legend_entries(lines):
        row = _legend_row(entry)
        if row is None:
            continue
        key = (row["operator"], row["technology"], row["band_label"], row["channel"])
        if key in seen:
            continue
        seen.add(key)
        legend_rows.append(row)

    return pd.DataFrame(rows, columns=COLUMNS), pd.DataFrame(legend_rows, columns=LEGEND_COLUMNS)


def parse_antennas(path):
    """Tableau des antennes : une ligne par élément rayonnant et par système."""
    return parse_antenna_report(path)[0]


def parse_legend(path):
    """Légende : une ligne par (opérateur, techno, bande, canal). Vide si la légende est absente."""
    return parse_antenna_report(path)[1]


def antennas_units(df):
    """Une ligne par élément rayonnant : modèle et systèmes servis.

    Les lignes de total (« All systems », « Selected systems ») ne sont pas des systèmes.
    Un élément listé plusieurs fois (répétitions entre pages) n'est compté qu'une fois.
    """
    rows = []
    for antenna_id, group in df.groupby("antenna_id", sort=True):
        systems = sorted({s for s in group["system"] if s and s not in SUMMARY_SYSTEMS})
        rows.append(
            {
                "antenna_id": antenna_id,
                "model": group["model"].iloc[0],
                "n_systems": len(systems),
                "systems": systems,
            }
        )
    return pd.DataFrame(rows, columns=["antenna_id", "model", "n_systems", "systems"])


def antenna_systems(df):
    """Systèmes distincts servis par les antennes (libellés du tableau, sans les lignes de total)."""
    return sorted({s for s in df["system"] if s and s not in SUMMARY_SYSTEMS})


def antennas_summary(df):
    """Nombre d'éléments rayonnants distincts par modèle."""
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
        .agg(
            systems=("band_label", "count"),
            generations=("generation", lambda g: "/".join(sorted({x for x in g if x}))),
        )
        .reset_index()
    )