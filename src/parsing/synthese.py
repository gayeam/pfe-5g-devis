"""Synthèse d'une étude : une ligne par site.

La ligne résume :
- le type de DAS (actif, passif ou hybride), déduit des équipements du routage ;
- pour chaque bande, le mode (MIMO, SISO ou mixte selon le secteur) ;
- les bandes et technologies présentes ;
- le nombre d'opérateurs estimé, et leurs noms s'ils sont dans la légende ;
- les étages des têtes radio (le ou les locaux techniques).

Règle du type de DAS :
- passif : seulement des splitters, filtres, matrices, atténuateurs ;
- actif : des unités radio ou hubs actifs, sans passif ;
- hybride : les deux.
La famille « MC » n'est pas classée (rôle inconnu) : elle n'influence pas le type.
"""

import re

PASSIVE_FAMILIES = {"SPT", "FTR", "ATT"}
ACTIVE_FAMILIES = {
    "gHOU", "HOU", "gMU", "MU", "gRFU", "RFU", "DAU",
    "HRN", "gHRN", "MRN", "gMRN", "LRN", "gLRN", "IRU", "DOT",
    "BDAHUB", "FBDA",
}

FAMILY_RE = re.compile(r"^[A-Za-z]+")


def _family(node):
    match = FAMILY_RE.match(str(node))
    return match.group(0) if match else None


def equipment_families(routing):
    """Familles d'équipements présentes dans le routage (source ou destination)."""
    nodes = set(routing["source_node"]) | set(routing["dest_node"])
    families = {_family(n) for n in nodes}
    return sorted(f for f in families if f and f not in {"BTS", "ANT"})


def das_type(routing):
    """Renvoie (type, familles actives, familles passives). Type : actif, passif, hybride ou None."""
    families = equipment_families(routing)
    active = [f for f in families if f in ACTIVE_FAMILIES]
    passive = [f for f in families if f in PASSIVE_FAMILIES]
    if active and passive:
        kind = "hybride"
    elif active:
        kind = "actif"
    elif passive:
        kind = "passif"
    else:
        kind = None
    return kind, active, passive


def operators_estimate(bts):
    """Nombre d'opérateurs estimé : nombre maximal de BTS pour une même bande et un même secteur.

    Un secteur est desservi par un BTS par opérateur et par bande.
    """
    if bts.empty:
        return 0
    counts = bts.groupby(["freq_mhz", "sector"]).size()
    return int(counts.max()) if len(counts) else 0


def band_label(freq_mhz, generation):
    """« 1800 MHz (4G) », « 3.5 GHz (5G) »."""
    if freq_mhz is None or freq_mhz != freq_mhz:
        return f"? ({generation})"
    shown = f"{freq_mhz / 1000:g} GHz" if freq_mhz >= 3000 else f"{freq_mhz:g} MHz"
    return f"{shown} ({generation})" if generation else shown


def _sectors(values):
    """Liste de secteurs lisible : « s1, s2 »."""
    clean = sorted({int(v) for v in values if v == v and v is not None})
    return ", ".join(f"s{v}" for v in clean) if clean else "secteur ?"


def band_modes(bts):
    """Pour chaque bande : mode par secteur, du type « MIMO (s1, s2) » ou « mixte : MIMO (s1), SISO (s2) »."""
    result = []
    for (freq, gen), group in bts.groupby(["freq_mhz", "generation"], dropna=False):
        label = band_label(freq, gen)
        mimo = _sectors(group.loc[group["mode"] == "MIMO", "sector"])
        siso = _sectors(group.loc[group["mode"] == "SISO", "sector"])
        has_mimo = (group["mode"] == "MIMO").any()
        has_siso = (group["mode"] == "SISO").any()
        if has_mimo and has_siso:
            text = f"{label} mixte : MIMO ({mimo}), SISO ({siso})"
        elif has_mimo:
            text = f"{label} MIMO ({mimo})"
        elif has_siso:
            text = f"{label} SISO ({siso})"
        else:
            continue
        result.append(text)
    return result


def site_summary(name, routing, bts, operators=None):
    """Renvoie un dictionnaire de synthèse et la ligne de texte correspondante.

    « operators » : liste des noms d'opérateurs si la légende les donne (sinon None).
    """
    kind, active, passive = das_type(routing)
    n_ops = operators_estimate(bts)
    bands = sorted({band_label(r.freq_mhz, r.generation) for r in bts.itertuples(index=False)})
    modes = band_modes(bts)
    not_traced = int((bts["status"] != "suivi").sum())
    floors = sorted({f for f in bts["floor"].dropna()}) if len(bts) else []

    if n_ops <= 1:
        op_text = "mono-opérateur"
    else:
        names = f" ({', '.join(operators)})" if operators else ""
        op_text = f"multi-opérateurs : {n_ops}{names}"

    line = (
        f"Site {name} : DAS {kind or 'indéterminé'}"
        f" ({', '.join(active + passive) or 'équipements inconnus'}) ; "
        f"MIMO/SISO par bande : {' ; '.join(modes) or 'non déterminé'} ; "
        f"bandes présentes : {', '.join(bands) or 'aucune'} ; "
        f"{op_text} ; "
        f"local(aux) technique(s) : {', '.join(floors) or 'non identifié'} ; "
        f"systèmes non suivis : {not_traced}."
    )
    return {
        "site": name,
        "das_type": kind,
        "active_families": active,
        "passive_families": passive,
        "band_modes": modes,
        "bands": bands,
        "operators_estimate": n_ops,
        "floors": floors,
        "not_traced": not_traced,
        "line": line,
    }