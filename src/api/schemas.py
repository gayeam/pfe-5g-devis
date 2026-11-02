"""Formats des données échangées entre l'API et l'interface."""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .catalogue import FAMILIES


class EstimateRequest(BaseModel):
    """Entrées d'une estimation : ce qu'on connaît avant la conception."""

    bandes: list[str] = Field(min_length=1, description="Bandes, ex. « 1800 MHz (4G) », « 3.5 GHz (5G) »")
    operateurs: list[str] = Field(min_length=1, description="Opérateurs, ex. BOUYGUES, ORANGE")
    mimo: bool = False
    etages: int = Field(ge=1, le=200)
    locaux_techniques: int = Field(default=1, ge=1, le=50)
    niveau_local: int = Field(default=0, ge=-10, le=100, description="-1 sous-sol, 0 RDC, 2 R+2…")
    hauteur_antennes: float = Field(default=2.5, gt=0, le=50)
    methode: Literal["VPLE", "FRT"] = "VPLE"
    surface: Optional[float] = Field(default=None, ge=0, description="Surface prédite en m² (si le modèle l'utilise)")


class EstimateLine(BaseModel):
    cle: str
    libelle: str
    unite: Literal["u", "m"]
    valeurs: dict[str, float]


class EstimateResponse(BaseModel):
    modele: str
    etudes_train: int
    surface_utilisee: bool
    etudes_par_das: dict[str, int]
    lignes: list[EstimateLine]
    alertes: list[str]


class ModelInfo(BaseModel):
    version: str
    etudes_train: int
    surface_utilisee: bool
    etudes_par_das: dict[str, int]


class OptionsResponse(BaseModel):
    bandes: list[str]
    operateurs: list[str]
    familles: list[str]
    types_das: list[str]
    modele: Optional[ModelInfo]


class EquipmentIn(BaseModel):
    famille: str = ""
    fabricant: str = ""
    reference: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=500)
    unite: Literal["u", "m"] = "u"
    source: Literal["saisie", "ELR"] = "saisie"

    @field_validator("famille", "fabricant", "reference", "description", mode="before")
    @classmethod
    def strip(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("famille")
    @classmethod
    def known_family(cls, value):
        if value and value not in FAMILIES:
            raise ValueError(f"famille inconnue : {value}")
        return value


class EquipmentOut(EquipmentIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class ImportResult(BaseModel):
    trouvees: int
    ajoutees: int
    erreurs: list[str]