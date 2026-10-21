"""Suivi des liaisons depuis chaque BTS : quelles antennes, quels ports, quel mode.

Principe :
- un BTS est un système (bande + techno + secteur) ;
- on suit les câbles et bretelles depuis chaque BTS jusqu'aux antennes ;
- si un même BTS atteint deux ports différents d'une même antenne, le système
  est en MIMO sur cette antenne. S'il n'atteint qu'un port, il est en SISO.

Le même raisonnement se lit dans l'autre sens : deux câbles rattachés au même
BTS et à la même antenne indiquent un MIMO activé.

Le mode indiqué sur le port (« (MIMO) », « (SISO) ») est gardé à part, comme
information de conception : les deux peuvent diverger.

Statut :
- « suivi » : au moins une antenne atteinte, le mode est déduit du suivi ;
- « chaine_non_suivie » : aucune antenne atteinte. Le mode est alors présumé
  d'après le nombre de câbles de sortie de la tête : deux câbles -> MIMO,
  un seul -> SISO.
"""

from collections import defaultdict

import pandas as pd

MAX_HOPS = 30

TRACE_COLUMNS = ["bts", "antenna", "port", "mode_label", "last_cable", "hops"]

SUMMARY_COLUMNS = [
    "bts",
    "system",
    "generation",
    "freq_mhz",
    "sector",
    "floor",
    "cables_out",
    "antennas",
    "max_ports_per_antenna",
    "status",
    "mode",
    "port_labels",
    "mode_labels",
]


def trace_bts(routing):
    """Une ligne par (BTS, antenne, port atteint). Parcours en profondeur depuis chaque BTS."""
    children = defaultdict(list)
    for row in routing.itertuples(index=False):
        children[row.source_node].append(row)

    bts_nodes = sorted(set(routing.loc[routing["source_node"].str.startswith("BTS"), "source_node"]))
    out = []
    for bts in bts_nodes:
        stack = [(bts, (bts,), 0)]
        while stack:
            node, visited, hops = stack.pop()
            for row in children.get(node, []):
                if row.dest_node in visited or hops >= MAX_HOPS:
                    continue
                if row.dest_node.startswith("ANT"):
                    out.append(
                        {
                            "bts": bts,
                            "antenna": row.dest_node,
                            "port": row.dest_port,
                            "mode_label": row.dest_mode,
                            "last_cable": row.record_id,
                            "hops": hops + 1,
                        }
                    )
                else:
                    stack.append((row.dest_node, visited + (row.dest_node,), hops + 1))
    return pd.DataFrame(out, columns=TRACE_COLUMNS)


def bts_summary(routing, trace):
    """Une ligne par BTS (= système) : bande, techno, secteur, étage, statut et mode."""
    heads = routing[routing["source_node"].str.startswith("BTS")].drop_duplicates("source_node")
    rows = []
    for head in heads.itertuples(index=False):
        bts = head.source_node
        cables_out = int((routing["source_node"] == bts).sum())
        t = trace[trace["bts"] == bts]
        per_antenna = t.groupby("antenna")["last_cable"].nunique() if len(t) else pd.Series(dtype=int)
        max_ports = int(per_antenna.max()) if len(per_antenna) else 0
        ports = sorted(set(t["port"].dropna())) if len(t) else []
        modes = sorted(set(t["mode_label"].dropna())) if len(t) else []
        traced = len(per_antenna) > 0
        if traced:
            mode = "MIMO" if max_ports >= 2 else "SISO"
        else:
            mode = "MIMO" if cables_out >= 2 else "SISO"
        rows.append(
            {
                "bts": bts,
                "system": head.source_system,
                "generation": head.source_generation,
                "freq_mhz": head.source_freq_mhz,
                "sector": head.source_sector,
                "floor": head.source_floor,
                "cables_out": cables_out,
                "antennas": int(len(per_antenna)),
                "max_ports_per_antenna": max_ports,
                "status": "suivi" if traced else "chaine_non_suivie",
                "mode": mode,
                "port_labels": ", ".join(ports) if ports else None,
                "mode_labels": ", ".join(modes) if modes else None,
            }
        )
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)