"""Lecture d'un libellé de système iBwave.

Exemples de libellés (2023 et 2026) :
- « 1800 MHz - DCS - LTE-A PCC - Sector 1 »
- « 3.5 GHz - 5G NR - Sector 1 »
- « 900 MHz - GSM - HSPA - Sector 2 »
- « 2.6 GHz - LTE - Sector 1 »

Un libellé donne la fréquence, la génération (2G, 3G, 4G, 5G) et le secteur.
"""

import re

FREQ_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(MHz|GHz)")
SECTOR_RE = re.compile(r"Sector\s*(\d+)")
NR_RE = re.compile(r"\bNR\b")


def generation(text):
    """Génération déduite du libellé. LTE et LTE-A = 4G, NR = 5G.

    « DCS » seul (sans LTE) est une bande GSM, donc 2G.
    """
    if NR_RE.search(text):
        return "5G"
    if "LTE" in text:
        return "4G"
    if "UMTS" in text or "HSPA" in text:
        return "3G"
    if "GSM" in text or "DCS" in text:
        return "2G"
    return None


def parse_system(label):
    """Renvoie un dictionnaire : libellé nettoyé, fréquence en MHz, génération, secteur."""
    text = " ".join(str(label).split())
    freq = FREQ_RE.search(text)
    freq_mhz = None
    if freq:
        value = float(freq.group(1).replace(",", "."))
        freq_mhz = value * 1000 if freq.group(2) == "GHz" else value
    sector = SECTOR_RE.search(text)
    return {
        "system": text,
        "freq_mhz": freq_mhz,
        "generation": generation(text),
        "sector": int(sector.group(1)) if sector else None,
    }