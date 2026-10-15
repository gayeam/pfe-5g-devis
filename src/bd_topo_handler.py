"""
BD TOPO Handler - bâtiment à une adresse ou à des coordonnées
=============================================================
Trouve le bâtiment BD TOPO (BDTOPO_V3:batiment) à une adresse ou des coordonnées.

Utilisation :
    python src/bd_topo_handler.py --address "Hotel de ville, Paris"
    python src/bd_topo_handler.py --coords 48.8564 2.3525
"""

import numpy as np
import shapely
import argparse
import logging
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pyproj
import requests
from shapely.geometry import Point, shape

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

WFS_URL = "https://data.geopf.fr/wfs/ows"
TYPE_NAME = "BDTOPO_V3:batiment"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "PFE-5G-Extractor/1.0"}
RADIUS_M = 100

# Lambert-93 : projection officielle de la France, pour mesurer en mètres
TO_LAMBERT93 = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:2154", always_xy=True)

def to_lambert93(geom):
    """Reprojette une géométrie shapely de WGS84 vers Lambert 93."""
    return shapely.transform(
        geom,
        lambda c: np.column_stack(TO_LAMBERT93.transform(c[:, 0], c[:, 1])),
    )


@dataclass
class BDTopoBuilding:
    cleabs: str
    nature: Optional[str]
    usage: Optional[str]
    nombre_d_etages: Optional[int]
    hauteur: Optional[float]
    methode_altimetrique: Optional[str]
    precision_altimetrique: Optional[float]
    surface_m2: float
    contient_point: bool
    distance_m: float


def geocode(address: str) -> Optional[Tuple[float, float]]:
    """Adresse -> (lat, lon) via Nominatim"""
    try:
        resp = requests.get(NOMINATIM_URL,
                            params={"q": address, "format": "json", "limit": 1},
                            headers=HEADERS, timeout=10)
        resp.raise_for_status()
        results = resp.json()
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception as e:
        logger.error(f"Erreur géocodage: {e}")
    return None


class BDTopoHandler:
    """Requêtes WFS pour la couche bâtiments de la BD TOPO"""

    def find_building(self, lat: float, lon: float) -> Optional[BDTopoBuilding]:
        """Bâtiment qui contient le point, sinon le plus proche"""
        buildings = self.query_buildings(lat, lon)
        if not buildings:
            return None
        return min(buildings, key=lambda b: (not b.contient_point, b.distance_m))

    def query_buildings(self, lat: float, lon: float, radius: int = RADIUS_M,
                        max_features: int = 100) -> List[BDTopoBuilding]:
        lat_delta = radius / 111000
        lon_delta = radius / (111000 * math.cos(math.radians(lat)))

        # Ce service attend longitude puis latitude (testé dans le navigateur)
        bbox = f"{lon - lon_delta},{lat - lat_delta},{lon + lon_delta},{lat + lat_delta},EPSG:4326"

        params = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": TYPE_NAME,
            "bbox": bbox,
            "srsName": "EPSG:4326",
            "outputFormat": "application/json",
            "count": max_features,
        }

        try:
            resp = requests.get(WFS_URL, params=params, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            features = resp.json().get("features", [])
        except Exception as e:
            logger.error(f"Erreur BD TOPO: {e}")
            return []

        point_m = to_lambert93(Point(lon, lat))
        buildings = []
        for feature in features:
            b = self._parse_feature(feature, point_m)
            if b:
                buildings.append(b)
        return buildings

    def _parse_feature(self, feature: Dict, point_m: Point) -> Optional[BDTopoBuilding]:
        try:
            props = feature.get("properties", {})
            geom = feature.get("geometry")
            if not geom:
                return None

            geom_m = to_lambert93(shape(geom))

            return BDTopoBuilding(
                cleabs=props.get("cleabs", "inconnu"),
                nature=props.get("nature"),
                usage=props.get("usage_1"),
                nombre_d_etages=props.get("nombre_d_etages"),
                hauteur=props.get("hauteur"),
                methode_altimetrique=props.get("methode_d_acquisition_altimetrique"),
                precision_altimetrique=props.get("precision_altimetrique"),
                surface_m2=geom_m.area,
                contient_point=geom_m.contains(point_m),
                distance_m=geom_m.distance(point_m),
            )
        except Exception as e:
            logger.error(f"Erreur parsing bâtiment: {e}")
            return None


def main():
    parser = argparse.ArgumentParser(description="Bâtiment BD TOPO à une adresse ou des coordonnées")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--address", help="Adresse, ex: 'Hotel de ville, Paris'")
    group.add_argument("--coords", nargs=2, type=float, metavar=("LAT", "LON"),
                       help="Coordonnées GPS, ex: 48.8564 2.3525")
    args = parser.parse_args()

    if args.address:
        coords = geocode(args.address)
        if not coords:
            print("Adresse non trouvée")
            return
        lat, lon = coords
        print(f"Adresse géocodée : {lat}, {lon}")
    else:
        lat, lon = args.coords

    building = BDTopoHandler().find_building(lat, lon)
    if not building:
        print("Aucun bâtiment BD TOPO trouvé")
        return

    if building.contient_point:
        statut = "oui"
    else:
        statut = f"non, à {building.distance_m:.0f} m"

    print("=" * 50)
    print(f"Identifiant (cleabs)   : {building.cleabs}")
    print(f"Contient le point      : {statut}")
    print(f"Nature                 : {building.nature}")
    print(f"Usage                  : {building.usage}")
    print(f"Surface (emprise sol)  : {building.surface_m2:.0f} m²")
    print(f"Hauteur                : {building.hauteur} m")
    print(f"Méthode altimétrique   : {building.methode_altimetrique}")
    print(f"Précision altimétrique : {building.precision_altimetrique} m")
    print(f"Nombre d'étages        : {building.nombre_d_etages}")
    print("=" * 50)


if __name__ == "__main__":
    main()