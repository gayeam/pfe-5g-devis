"""Modèles maison, dans un module à part pour que le modèle enregistré (joblib) se relise de partout.

Une classe définie dans le script lancé en commande (python -m src.model.train) serait enregistrée
sous le nom provisoire « __main__ », et ne pourrait plus être relue par l'application.
"""

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin

from .features import DAS_TYPES, SURFACE_FEATURE


class MedianByDas(BaseEstimator, RegressorMixin):
    """Prédit la médiane des études de train du même type de DAS (médiane générale à défaut)."""

    def fit(self, X, y):
        X = pd.DataFrame(X)
        y = np.asarray(y, dtype=float)
        self.global_ = float(np.median(y)) if len(y) else 0.0
        self.by_das_ = {}
        for das in DAS_TYPES:
            column = f"das_{das}"
            if column in X:
                mask = X[column].to_numpy() == 1
                if mask.any():
                    self.by_das_[das] = float(np.median(y[mask]))
        return self

    def predict(self, X):
        X = pd.DataFrame(X)
        result = np.full(len(X), self.global_)
        for das, value in self.by_das_.items():
            result[X[f"das_{das}"].to_numpy() == 1] = value
        return result


class RatioSurfaceByDas(BaseEstimator, RegressorMixin):
    """Quantité = densité au m² (médiane des études de train du même DAS) × surface prédite.

    Référence simple quand la surface est connue : « tant d'antennes, de mètres de coax… par m² ».
    Sans colonne surface, se comporte comme MedianByDas.
    """

    def fit(self, X, y):
        X = pd.DataFrame(X)
        y = np.asarray(y, dtype=float)
        self.fallback_ = MedianByDas().fit(X, y)
        self.has_surface_ = SURFACE_FEATURE in X
        if not self.has_surface_:
            return self
        surface = X[SURFACE_FEATURE].to_numpy(dtype=float)
        ok = surface > 0
        ratio = np.where(ok, y / np.where(ok, surface, 1), np.nan)
        self.global_ = float(np.nanmedian(ratio)) if ok.any() else 0.0
        self.by_das_ = {}
        for das in DAS_TYPES:
            column = f"das_{das}"
            if column in X:
                mask = (X[column].to_numpy() == 1) & ok
                if mask.any():
                    self.by_das_[das] = float(np.median(ratio[mask]))
        return self

    def predict(self, X):
        X = pd.DataFrame(X)
        if not self.has_surface_:
            return self.fallback_.predict(X)
        ratio = np.full(len(X), self.global_)
        for das, value in self.by_das_.items():
            ratio[X[f"das_{das}"].to_numpy() == 1] = value
        surface = pd.to_numeric(X[SURFACE_FEATURE], errors="coerce").to_numpy(dtype=float)
        result = ratio * surface
        missing = ~(surface > 0)
        result[missing] = self.fallback_.predict(X)[missing]
        return result