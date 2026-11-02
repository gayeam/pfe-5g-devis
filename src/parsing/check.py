"""Contrôle croisé d'une étude : ELR, routage, antennes et suivi des BTS doivent se répondre.

Usage :
    python -m src.parsing.check --dir data/ETUDE_A
    python -m src.parsing.check --dir data/ETUDE_A --site "SITE A"

Le dossier doit contenir (noms exacts, majuscules indifférentes) :
    Equipment List Report.xlsx  (ou .pdf)
    Antennas Report.pdf         (ou .xlsx)
    Cable Routing Report.pdf    (ou .xlsx)
et peut contenir :
    Electromagnetic Field Report.pdf  (hauteurs d'antennes si absentes du rapport antennes)

Le script affiche les totaux, les systèmes (BTS), les modes déduits du suivi,
la ligne de synthèse du site et les écarts avec l'ELR. Il ne corrige rien.
"""

import argparse
from pathlib import Path

from .antennas import antennas_summary, antennas_units, legend_summary, parse_antenna_report
from .elr import parse_elr
from .elr_targets import elr_targets
from .routing import parse_routing, ports_summary, routing_summary
from .synthese import site_summary
from .topology import bts_summary, trace_bts

STUDY_FILES = {
    "elr": ["Equipment List Report.xlsx", "Equipment List Report.pdf"],
    "antennas": ["Antennas Report.pdf", "Antennas Report.xlsx"],
    "routing": ["Cable Routing Report.pdf", "Cable Routing Report.xlsx"],
    "em": ["Electromagnetic Field Report.pdf"],
}
REQUIRED_FILES = ("elr", "antennas", "routing")


def find_files(study_dir):
    """Chemins des fichiers de l'étude ({clé: Path ou None}), sans vérifier qu'ils sont complets."""
    names = {p.name.lower(): p for p in Path(study_dir).iterdir() if p.is_file()}
    return {key: next((names[o.lower()] for o in options if o.lower() in names), None) for key, options in STUDY_FILES.items()}


def is_study(study_dir):
    """Vrai si le dossier contient un ELR (Excel ou PDF)."""
    return find_files(study_dir)["elr"] is not None


def study_files(study_dir):
    """Comme find_files, mais lève une erreur claire si un fichier obligatoire manque."""
    files = find_files(study_dir)
    missing = [STUDY_FILES[k][0] for k in REQUIRED_FILES if files[k] is None]
    if missing:
        present = sorted(p.name for p in Path(study_dir).iterdir() if p.is_file() and p.suffix.lower() in {".pdf", ".xlsx"})
        raise FileNotFoundError(
            f"fichier(s) manquant(s) : {', '.join(missing)} (présents : {', '.join(present) or 'aucun PDF ni Excel'})"
        )
    return files


def controls(study_dir, site_name=None):
    """Lit les rapports et renvoie un dictionnaire de résultats, de contrôles et de synthèse."""
    study_dir = Path(study_dir)
    files = study_files(study_dir)
    elr = parse_elr(files["elr"])
    antennas, legend = parse_antenna_report(files["antennas"])
    routing = parse_routing(files["routing"])
    targets = elr_targets(elr)

    coax = routing[(routing["kind"] == "coax") & (routing["medium"] == "coax")]
    jumpers = routing[routing["kind"].isin(["jumper", "cable_jumper"])]
    n_coax = len(coax)
    coax_length = round(coax["length_est_m"].sum(), 2)

    units = antennas_units(antennas)
    routing_antennas = set(routing.loc[routing["dest_node"].str.startswith("ANT"), "dest_node"])
    elements = set(units["antenna_id"]) | routing_antennas
    elements_ref = targets["elr_antennes"] or targets["elr_unites_radio"]

    operators = sorted(set(legend["operator"])) if len(legend) else None

    trace = trace_bts(routing)
    bts = bts_summary(routing, trace)
    n_mimo = int((bts["mode"] == "MIMO").sum())
    n_not_traced = int((bts["status"] != "suivi").sum())
    site = site_summary(site_name or study_dir.name, routing, bts, operators)

    return {
        "files": files,
        "elr": elr,
        "targets": targets,
        "antennas": antennas,
        "units": units,
        "elements": sorted(elements),
        "legend": legend,
        "routing": routing,
        "ports": ports_summary(routing),
        "trace": trace,
        "bts": bts,
        "site": site,
        "checks": [
            ("Éléments rayonnants (design)", len(elements), elements_ref, "ELR antennes (ou unités radio)"),
            ("Opérateurs (légende antennes)", len(operators) if operators else 0, None, "légende"),
            ("Câbles coax (design)", n_coax, None, "pas de valeur ELR"),
            ("Linéaire coax m (design)", coax_length, targets["elr_coax_m_total"], "ELR"),
            ("Bretelles (design)", len(jumpers), targets["elr_bretelles"], "ELR"),
            ("Connecteurs coax = 2 × coax ?", 2 * n_coax, targets["elr_connecteurs_coax"], "ELR"),
            ("Systèmes BTS (design)", len(bts), None, "suivi BTS"),
            ("Systèmes en MIMO", n_mimo, None, "suivi ou présomption"),
            ("Systèmes non suivis", n_not_traced, None, "suivi BTS"),
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="Contrôle croisé ELR / routage / antennes / BTS")
    parser.add_argument("--dir", required=True, help="dossier de l'étude (ex. data/ETUDE_A)")
    parser.add_argument("--site", default=None, help="nom du site pour la ligne de synthèse")
    args = parser.parse_args()

    result = controls(args.dir, args.site)

    print("== Synthèse du site")
    print(result["site"]["line"])
    print("\n== Antennes par modèle (rapport antennes)")
    print(antennas_summary(result["antennas"]).to_string(index=False))
    print("\n== Opérateurs (légende du rapport antennes)")
    print(legend_summary(result["legend"]).to_string(index=False))
    print("\n== Systèmes (BTS) : bande, techno, secteur, étage, mode déduit du suivi")
    print(result["bts"].to_string(index=False))
    print("\n== Ports antenne : libellés du routage (mode, port, diamètre)")
    print(result["ports"].to_string(index=False))
    print("\n== Coax par étage source")
    print(routing_summary(result["routing"]).to_string(index=False))
    print("\n== Quantités ELR (cibles)")
    for key, value in result["targets"].items():
        if value:
            print(f"  {key:28s}{value:>12g}")
    print("\n== Contrôles croisés (design / ELR)")
    print(f"{'contrôle':<34}{'design':>12}{'référence':>12}   source")
    for label, design, reference, source in result["checks"]:
        ref = "-" if reference is None else f"{reference:g}"
        print(f"{label:<34}{design:>12g}{ref:>12}   {source}")


if __name__ == "__main__":
    main()