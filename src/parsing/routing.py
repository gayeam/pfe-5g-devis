"""Lecture du rapport « Cable Routing Report » (PDF iBwave).

Chaque ligne est un câble coaxial (CBLn) ou une bretelle (JMPn), avec :
- la source : soit une tête radio (BTSn, qui porte la bande, la techno et le
  secteur dans son libellé), soit un splitter, un filtre ou une matrice ;
- la destination : une antenne (ANTn) ou un autre équipement ;
- l'étage de chaque extrémité : c'est aussi la localisation des BTS (ex. SS-1
  pour un local technique au sous-sol) ;
- sur le port côté antenne : le mode (SISO / MIMO), le numéro de port
  (« Ant 1 », « Ant 2 » en 2023) ou la polarisation (« H » / « V »), et la
  plage de fréquences du port (fiche technique, pas la bande utilisée) ;
- le type, le modèle, le diamètre et la longueur estimée.

Un rapport peut couvrir plusieurs pages : les en-têtes répétés sont ignorés.
"""

import re

import pandas as pd
import pdfplumber

from .systems import parse_system
from .utils import clean, to_float

RECORD_ID_RE = re.compile(r"^(CBL|JMP)\d+$")
MODE_RE = re.compile(r"\((SISO|MIMO)\)")
POL_RE = re.compile(r"\((H|V)\)")
PORT_RE = re.compile(r"^(Ant \d+)\b")
BTS_RE = re.compile(r"^(BTS\d+)\s*\((.*)\)$")
DIAMETER_RE = re.compile(r'(\d+/\d+)"')

COLUMNS = [
    "record_id",
    "kind",
    "source_part",
    "source_conn",
    "source_floor",
    "source_node",
    "dest_part",
    "dest_conn",
    "dest_floor",
    "dest_node",
    "cable_type",
    "model",
    "manufacturer",
    "length_est_m",
    "length_measured_m",
    "dest_mode",
    "dest_port",
    "dest_band",
    "cable_diameter",
    "source_system",
    "source_freq_mhz",
    "source_generation",
    "source_sector",
]


def _node(text):
    """Identifiant court d'un équipement : « BTS12 (…) » -> BTS12, « jumper on SPT1 » -> SPT1."""
    text = " ".join(str(text).split())
    text = re.sub(r"^jumper on\s+", "", text)
    match = BTS_RE.match(text)
    return match.group(1) if match else text.split(" ")[0]


def _diameter(text):
    """« Coaxial-1/2" 4.3-10-M » -> '1/2'. None si absent."""
    match = DIAMETER_RE.search(text)
    return match.group(1) if match else None


def _dest_fields(conn):
    """Décompose le port côté antenne : (mode, port, bande de fonctionnement du port)."""
    text = " ".join(str(conn).split())
    mode = MODE_RE.search(text)
    port = PORT_RE.match(text) or POL_RE.search(text)
    band = PORT_RE.sub("", MODE_RE.sub("", POL_RE.sub("", text))).strip()
    return (
        mode.group(1) if mode else None,
        port.group(1) if port else None,
        band or None,
    )


def _source_fields(source_part):
    """Pour une tête BTS : (libellé du système, fréquence MHz, génération, secteur). Sinon None."""
    match = BTS_RE.match(" ".join(str(source_part).split()))
    if not match:
        return None, None, None, None
    info = parse_system(match.group(2))
    return info["system"], info["freq_mhz"], info["generation"], info["sector"]


def parse_routing(path):
    """Renvoie un DataFrame : une ligne par câble ou bretelle, sans doublon d'identifiant."""
    rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for raw in table:
                    cells = [clean(c) for c in raw]
                    if not cells or not cells[0]:
                        continue
                    record_id = cells[0].split(" ")[0]
                    if not RECORD_ID_RE.match(record_id) or len(cells) < 12:
                        continue
                    dest_mode, dest_port, dest_band = _dest_fields(cells[5])
                    sys_label, sys_freq, sys_gen, sys_sector = _source_fields(cells[1])
                    rows.append(
                        {
                            "record_id": record_id,
                            "kind": "coax" if record_id.startswith("CBL") else "jumper",
                            "source_part": cells[1],
                            "source_conn": cells[2],
                            "source_floor": cells[3],
                            "source_node": _node(cells[1]),
                            "dest_part": cells[4],
                            "dest_conn": cells[5],
                            "dest_floor": cells[6],
                            "dest_node": _node(cells[4]),
                            "cable_type": cells[7],
                            "model": cells[8],
                            "manufacturer": cells[9],
                            "length_est_m": to_float(cells[10]),
                            "length_measured_m": to_float(cells[11]),
                            "dest_mode": dest_mode,
                            "dest_port": dest_port,
                            "dest_band": dest_band,
                            "cable_diameter": _diameter(cells[8]),
                            "source_system": sys_label,
                            "source_freq_mhz": sys_freq,
                            "source_generation": sys_gen,
                            "source_sector": sys_sector,
                        }
                    )
    df = pd.DataFrame(rows, columns=COLUMNS)
    before = len(df)
    df = df.drop_duplicates("record_id").reset_index(drop=True)
    if len(df) != before:
        print(f"[routing] {before - len(df)} doublon(s) d'identifiant supprimé(s)")
    return df


def routing_summary(df):
    """Totaux utiles pour le contrôle : nombre et linéaire coax par étage source."""
    coax = df[df["kind"] == "coax"]
    per_floor = (
        coax.groupby("source_floor")
        .agg(coax_count=("record_id", "count"), coax_length_m=("length_est_m", "sum"))
        .reset_index()
    )
    return per_floor


def ports_summary(df):
    """Câbles arrivant sur une antenne, par mode, port et diamètre (libellés du routage)."""
    to_antenna = df[(df["kind"] == "coax") & df["dest_node"].str.startswith("ANT")]
    return (
        to_antenna.groupby(["dest_mode", "dest_port", "cable_diameter"], dropna=False)
        .size()
        .rename("cables")
        .reset_index()
    )