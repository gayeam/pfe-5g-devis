"""Contrôle croisé d'une étude : ELR, routage, antennes et suivi des BTS doivent se répondre.

Usage :
    python -m src.parsing.check --dir data/HOTEL_CELESTE
    python -m src.parsing.check --dir data/HOTEL_CELESTE --site "HOTEL CELESTE"

Le dossier doit contenir :
    Equipment List Report.xlsx
    Antennas Report.pdf
    Cable Routing Report.pdf

Le script affiche les totaux, les systèmes (BTS), les modes déduits du suivi,
les libellés de port, la ligne de synthèse du site et les écarts. Il ne corrige rien.
"""

import argparse
from pathlib import Path

from .antennas import antennas_summary, antennas_units, legend_summary, parse_antennas, parse_legend
from .elr import parse_elr
from .routing import parse_routing, ports_summary, routing_summary
from .synthese import site_summary
from .topology import bts_summary, trace_bts

ELR_FILE = "Equipment List Report.xlsx"
ANT_FILE = "Antennas Report.pdf"
ROUTING_FILE = "Cable Routing Report.pdf"


def controls(study_dir, site_name=None):
    """Lit les trois rapports et renvoie un dictionnaire de résultats, de contrôles et de synthèse."""
    study_dir = Path(study_dir)
    elr = parse_elr(study_dir / ELR_FILE)
    antennas = parse_antennas(study_dir / ANT_FILE)
    legend = parse_legend(study_dir / ANT_FILE)
    routing = parse_routing(study_dir / ROUTING_FILE)

    coax = routing[routing["kind"] == "coax"]
    jumpers = routing[routing["kind"] == "jumper"]

    n_coax = len(coax)
    coax_length = round(coax["length_est_m"].sum(), 2)
    n_connectors_elr = elr.loc[elr["model"].str.contains("43M-SCF12|Connector", case=False, na=False), "qty"].sum()
    units = antennas_units(antennas)
    n_antennas = len(units)
    n_antennas_elr = elr.loc[elr["type"].str.lower().eq("antenna"), "qty"].sum()
    n_jumpers_elr = elr.loc[elr["description"].str.contains("Jumper|Bretelle", case=False, na=False), "qty"].sum()
    operators = sorted(legend["operator"].unique()) if len(legend) else None
    n_operators = len(operators) if operators else 0

    trace = trace_bts(routing)
    bts = bts_summary(routing, trace)
    n_mimo = int((bts["mode"] == "MIMO").sum())
    n_not_traced = int((bts["status"] != "suivi").sum())
    site = site_summary(site_name or study_dir.name, routing, bts, operators)

    return {
        "elr": elr,
        "antennas": antennas,
        "units": units,
        "legend": legend,
        "routing": routing,
        "ports": ports_summary(routing),
        "trace": trace,
        "bts": bts,
        "site": site,
        "checks": [
            ("Antennes distinctes (design)", n_antennas, n_antennas_elr, "antennes ELR"),
            ("Opérateurs (légende antennes)", n_operators, None, "pas de valeur ELR"),
            ("Câbles coax (design)", n_coax, None, "pas de valeur ELR"),
            ("Linéaire coax m (design)", coax_length, elr.loc[elr["unit"].str.lower().eq("m"), "qty"].sum(), "ELR"),
            ("Bretelles (design)", len(jumpers), n_jumpers_elr, "ELR"),
            ("Connecteurs = 2 × coax ?", 2 * n_coax, n_connectors_elr, "ELR"),
            ("Systèmes BTS (design)", len(bts), None, "suivi BTS"),
            ("Systèmes en MIMO (suivi)", n_mimo, None, "suivi BTS"),
            ("Systèmes non suivis", n_not_traced, None, "suivi BTS"),
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="Contrôle croisé ELR / routage / antennes / BTS")
    parser.add_argument("--dir", required=True, help="dossier de l'étude (ex. data/HOTEL_CELESTE)")
    parser.add_argument("--site", default=None, help="nom du site pour la ligne de synthèse")
    args = parser.parse_args()

    result = controls(args.dir, args.site)

    print("== Synthèse du site")
    print(result["site"]["line"])
    print("\n== Antennes par modèle")
    print(antennas_summary(result["antennas"]).to_string(index=False))
    print("\n== Opérateurs (légende du rapport antennes)")
    print(legend_summary(result["legend"]).to_string(index=False))
    print("\n== Systèmes (BTS) : bande, techno, secteur, étage, mode déduit du suivi")
    print(result["bts"].to_string(index=False))
    print("\n== Ports antenne : libellés du routage (mode, port, diamètre)")
    print(result["ports"].to_string(index=False))
    print("\n== Coax par étage source")
    print(routing_summary(result["routing"]).to_string(index=False))
    print("\n== Contrôles croisés (design / ELR)")
    print(f"{'contrôle':<32}{'design':>12}{'référence':>12}   source")
    for label, design, reference, source in result["checks"]:
        ref = "-" if reference is None else f"{reference:g}"
        print(f"{label:<32}{design:>12g}{ref:>12}   {source}")


if __name__ == "__main__":
    main()