"""API de pré-dimensionnement DAS (FastAPI).

Lancement, depuis la racine du dépôt :
    uvicorn src.api.main:app --reload

Puis, pour le développement de l'interface : dans frontend/, « npm run dev » (http://localhost:5173).
Si l'interface a été construite (« npm run build »), elle est aussi servie directement par
l'API sur http://localhost:8000.

Variables d'environnement (facultatives) :
    PFE_DATA    dossier des données (défaut : data/ à la racine du dépôt)
    PFE_DB_URL  base de données (défaut : sqlite:///data/app.db)

Routes :
    GET    /api/options                  listes pour le formulaire, état du modèle
    POST   /api/estimate                 estimation par type de DAS
    GET    /api/catalogue                références (filtres : famille, q)
    POST   /api/catalogue                ajouter une référence
    PUT    /api/catalogue/{id}           modifier une référence
    DELETE /api/catalogue/{id}           supprimer une référence
    POST   /api/catalogue/import-elr     ajouter les références trouvées dans les ELR des études
"""

import os
from pathlib import Path

import joblib
from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..model.features import DAS_TYPES, load_corpus
from ..parsing.antennas import OPERATORS, PRIVATE
from ..model.predict import LABELS, MIN_STUDIES_PER_DAS, predict_all
from ..model.train import MODEL_DIR, VERSION
from .catalogue import FAMILIES, references_from_elr
from .db import Equipment, make_session_factory
from .schemas import (
    EquipmentIn,
    EquipmentOut,
    EstimateLine,
    EstimateRequest,
    EstimateResponse,
    ImportResult,
    ModelInfo,
    OptionsResponse,
)

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_ROOT = Path(os.environ.get("PFE_DATA", ROOT_DIR / "data"))
DATA_ROOT.mkdir(parents=True, exist_ok=True)
DB_URL = os.environ.get("PFE_DB_URL", f"sqlite:///{(DATA_ROOT / 'app.db').as_posix()}")
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"

DEFAULT_BANDS = [
    "700 MHz (4G)", "800 MHz (4G)", "900 MHz (2G)", "900 MHz (3G)",
    "1800 MHz (4G)", "2100 MHz (4G)", "2600 MHz (4G)", "3.5 GHz (5G)",
]
# Liste fixe : les 4 opérateurs mobiles et « PRIVÉ » (réseau privé, sans opérateur).
# Les noms lus dans les études (variantes, « OPERATEUR 1 »…) ne sont pas proposés.
OPERATOR_CHOICES = OPERATORS + [PRIVATE]

SessionLocal = make_session_factory(DB_URL)

app = FastAPI(title="Pré-dimensionnement DAS", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --------------------------------------------------------------------- modèle et corpus

_cache = {}


def _cached(key, path, loader):
    """Recharge le fichier seulement s'il a changé (modèle réentraîné, corpus reconstruit)."""
    mtime = path.stat().st_mtime if path.exists() else None
    if key not in _cache or _cache[key][0] != mtime:
        _cache[key] = (mtime, loader() if mtime is not None else None)
    return _cache[key][1]


def get_bundle():
    path = DATA_ROOT / MODEL_DIR / f"modele_{VERSION}.joblib"
    return _cached("model", path, lambda: joblib.load(path))


def _band_order(label):
    try:
        value = float(label.split(" ")[0].replace(",", "."))
    except ValueError:
        return (1e9, label)
    return (value * 1000 if "GHz" in label else value, label)


def get_corpus_options():
    path = DATA_ROOT / "corpus" / "train" / "dataset.csv"

    def load():
        corpus = load_corpus(DATA_ROOT)

        def values(column):
            found = set()
            for cell in corpus[column].dropna().astype(str):
                found |= {v.strip() for v in cell.split(";") if v.strip()}
            return found

        return values("bands")

    bands = _cached("corpus", path, load) or set()
    return sorted(bands | set(DEFAULT_BANDS), key=_band_order), OPERATOR_CHOICES


def _model_info(bundle):
    if bundle is None:
        return None
    return ModelInfo(
        version=bundle["version"],
        etudes_train=bundle["train_size"],
        surface_utilisee=bundle["use_surface"],
        etudes_par_das={d: int(bundle["das_counts"].get(d, 0)) for d in DAS_TYPES},
    )


# --------------------------------------------------------------------- routes : estimation


@app.get("/api/options", response_model=OptionsResponse)
def options():
    bands, operators = get_corpus_options()
    return OptionsResponse(
        bandes=bands,
        operateurs=operators,
        familles=FAMILIES,
        types_das=DAS_TYPES,
        modele=_model_info(get_bundle()),
    )


@app.post("/api/estimate", response_model=EstimateResponse)
def estimate(req: EstimateRequest):
    bundle = get_bundle()
    if bundle is None:
        raise HTTPException(503, "Aucun modèle entraîné : lancer « python -m src.model.train --root data ».")
    if bundle["use_surface"] and req.surface is None:
        raise HTTPException(422, "Ce modèle utilise la surface : renseigner la surface prédite.")

    inputs = {
        "bandes": len(set(req.bandes)),
        "bande_5g": any("(5G)" in b for b in req.bandes),
        "operateurs": len(set(req.operateurs)),
        "mimo": req.mimo,
        "etages": req.etages,
        "locaux_techniques": req.locaux_techniques,
        "niveau_local": req.niveau_local,
        "hauteur_antennes": req.hauteur_antennes,
        "methode": req.methode,
        "surface": req.surface if bundle["use_surface"] else None,
    }
    result = predict_all(bundle, **inputs)

    alerts = []
    ranges = bundle["feature_ranges"]
    checks = [
        ("Bandes", "bandes", "bandes"),
        ("Opérateurs", "operateurs", "operateurs"),
        ("Étages", "etages", "etages"),
        ("Locaux techniques", "locaux_techniques", "locaux_techniques"),
        ("Hauteur des antennes", "hauteur_antennes", "hauteur_antennes"),
    ]
    if bundle["use_surface"]:
        checks.append(("Surface", "surface", "surface_predite_m2"))
    for label, key, column in checks:
        low, high = ranges[column]
        if not low <= inputs[key] <= high:
            alerts.append(f"{label} = {inputs[key]:g} : hors de ce qui a été vu à l'entraînement ({low:g} à {high:g}).")
    counts = {d: int(bundle["das_counts"].get(d, 0)) for d in DAS_TYPES}
    few = [d for d in DAS_TYPES if counts[d] < MIN_STUDIES_PER_DAS]
    if few:
        alerts.append(f"Peu d'études en train pour : DAS {', '.join(few)} (moins de {MIN_STUDIES_PER_DAS}).")

    lines = [
        EstimateLine(
            cle=target,
            libelle=LABELS.get(target, target),
            unite=unit,
            valeurs={das: round(result[das][target], 2) for das in DAS_TYPES},
        )
        for target, unit in bundle["units"].items()
    ]
    return EstimateResponse(
        modele=bundle["version"],
        etudes_train=bundle["train_size"],
        surface_utilisee=bundle["use_surface"],
        etudes_par_das=counts,
        lignes=lines,
        alertes=alerts,
    )


# --------------------------------------------------------------------- routes : catalogue


def _duplicate(db, fabricant, reference, exclude_id=None):
    query = select(Equipment).where(
        func.lower(Equipment.fabricant) == fabricant.lower(),
        func.lower(Equipment.reference) == reference.lower(),
    )
    if exclude_id is not None:
        query = query.where(Equipment.id != exclude_id)
    return db.scalars(query).first() is not None


@app.get("/api/catalogue", response_model=list[EquipmentOut])
def list_equipment(
    famille: str | None = Query(default=None),
    q: str | None = Query(default=None, description="recherche dans fabricant, référence, description"),
    db: Session = Depends(get_db),
):
    query = select(Equipment)
    if famille:
        query = query.where(Equipment.famille == famille)
    if q:
        pattern = f"%{q.lower()}%"
        query = query.where(
            or_(
                func.lower(Equipment.fabricant).like(pattern),
                func.lower(Equipment.reference).like(pattern),
                func.lower(Equipment.description).like(pattern),
            )
        )
    return db.scalars(query.order_by(Equipment.famille, Equipment.fabricant, Equipment.reference)).all()


@app.post("/api/catalogue", response_model=EquipmentOut, status_code=201)
def create_equipment(item: EquipmentIn, db: Session = Depends(get_db)):
    if _duplicate(db, item.fabricant, item.reference):
        raise HTTPException(409, f"La référence {item.fabricant} {item.reference} existe déjà.")
    equipment = Equipment(**item.model_dump())
    db.add(equipment)
    db.commit()
    db.refresh(equipment)
    return equipment


@app.put("/api/catalogue/{equipment_id}", response_model=EquipmentOut)
def update_equipment(equipment_id: int, item: EquipmentIn, db: Session = Depends(get_db)):
    equipment = db.get(Equipment, equipment_id)
    if equipment is None:
        raise HTTPException(404, "Référence introuvable.")
    if _duplicate(db, item.fabricant, item.reference, exclude_id=equipment_id):
        raise HTTPException(409, f"La référence {item.fabricant} {item.reference} existe déjà.")
    for key, value in item.model_dump().items():
        setattr(equipment, key, value)
    db.commit()
    db.refresh(equipment)
    return equipment


@app.delete("/api/catalogue/{equipment_id}", status_code=204)
def delete_equipment(equipment_id: int, db: Session = Depends(get_db)):
    equipment = db.get(Equipment, equipment_id)
    if equipment is None:
        raise HTTPException(404, "Référence introuvable.")
    db.delete(equipment)
    db.commit()
    return Response(status_code=204)


@app.post("/api/catalogue/import-elr", response_model=ImportResult)
def import_from_elr(db: Session = Depends(get_db)):
    found, errors = references_from_elr(DATA_ROOT)
    existing = {
        (f.lower(), r.lower()) for f, r in db.execute(select(Equipment.fabricant, Equipment.reference)).all()
    }
    added = 0
    for row in found:
        key = (row["fabricant"].lower(), row["reference"].lower())
        if key in existing:
            continue
        db.add(Equipment(**row))
        existing.add(key)
        added += 1
    db.commit()
    return ImportResult(trouvees=len(found), ajoutees=added, erreurs=errors)


# --------------------------------------------------------------------- interface construite

if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")