"""Outils communs de lecture : nettoyage des cellules et conversion des nombres.

Les rapports iBwave utilisent la virgule comme séparateur décimal (« 30,41 »)
et mettent parfois une unité dans la cellule (« 1245,22 m »).
"""

import re

_NUM_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


def clean(value):
    """Nettoie une cellule : None -> '', retours à la ligne et espaces multiples supprimés."""
    if value is None:
        return ""
    text = str(value).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def to_float(value):
    """Convertit « 30,41 » ou « 1245,22 m » en float. Renvoie None si pas de nombre."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = _NUM_RE.search(str(value))
    if not match:
        return None
    return float(match.group(0).replace(",", "."))


def split_unit(value):
    """« 1245,22 m » -> (1245.22, 'm'). Sans unité, renvoie (nombre, '')."""
    number = to_float(value)
    if number is None:
        return None, ""
    rest = _NUM_RE.sub("", str(value), count=1).strip()
    return number, rest