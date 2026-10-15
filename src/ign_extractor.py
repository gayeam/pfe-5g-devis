"""
Extracteur de données IGN - BD TOPO & LiDAR
==========================================
Module pour extraire : surface, forme, type, hauteur, nombre d'étages
à partir des données publiques IGN (BD TOPO, LiDAR HD)

Utilisation :
    python ign_extractor.py --address "123 rue de Paris, Lyon"
    ou
    python ign_extractor.py --lat 45.75 --lon 4.84 --radius 100
"""

import json
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import requests
from shapely.geometry import shape, Point, box
from shapely.ops import transform
import pyproj

# Configuration logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# Constants
# IGN_WFS_URL = "https://wxs.ign.fr/essentiels/geom/wfs"  # API IGN (open data)
# OVERPASS_URL = "https://overpass.kumi.systems/api/interpreter"  # Miroir Overpass
OVERPASS_URL = "https://overpass-api.de/api/interpreter"  # Fallback OSM


@dataclass
class BuildingInfo:
    """Résultat extraction d'un bâtiment"""
    address: Optional[str] = None
    surface_m2: Optional[float] = None  # Surface en m²
    shape: Optional[str] = None  # "rectangle", "L-shape", "irregular"
    building_type: Optional[str] = None  # "residential", "commercial", "industrial", etc.
    height_m: Optional[float] = None  # Hauteur en mètres
    estimated_floors: Optional[int] = None  # Nombre d'étages estimé
    roof_shape: Optional[str] = None  # "flat", "pitched", "complex"
    materials: Optional[List[str]] = None  # Matériaux si disponibles
    confidence: float = 0.0  # Score confiance 0-1
    source: str = "unknown"  # Source données (BD TOPO, OSM, etc.)
    metadata: Dict = None  # Métadonnées brutes

    def to_dict(self) -> Dict:
        """Convertir en dictionnaire"""
        return {
            'address': self.address,
            'surface_m2': self.surface_m2,
            'shape': self.shape,
            'building_type': self.building_type,
            'height_m': self.height_m,
            'estimated_floors': self.estimated_floors,
            'roof_shape': self.roof_shape,
            'materials': self.materials,
            'confidence': self.confidence,
            'source': self.source
        }

    def __str__(self) -> str:
        """Affichage lisible"""
        output = f"\n{'='*50}\n"
        output += f"RÉSULTAT EXTRACTION BÂTIMENT\n"
        output += f"{'='*50}\n"
        if self.address:
            output += f"Adresse: {self.address}\n"
        output += f"Surface: {self.surface_m2:.0f} m²\n" if self.surface_m2 else "Surface: ?\n"
        output += f"Type: {self.building_type}\n" if self.building_type else "Type: ?\n"
        output += f"Forme: {self.shape}\n" if self.shape else "Forme: ?\n"
        output += f"Hauteur: {self.height_m:.1f} m\n" if self.height_m else "Hauteur: ?\n"
        output += f"Étages estimés: {self.estimated_floors}\n" if self.estimated_floors else "Étages: ?\n"
        output += f"Confiance: {self.confidence:.0%}\n"
        output += f"Source: {self.source}\n"
        output += f"{'='*50}\n"
        return output


class IGNExtractor:
    """Extraction données IGN"""

    def __init__(self):
        self.transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:2154", always_xy=True)
        self.headers = {
            'User-Agent': 'PFE-5G-Extractor/1.0'
        }

    def extract_from_address(self, address: str) -> Optional[BuildingInfo]:
        """Extraire infos bâtiment depuis adresse

        Args:
            address: adresse (ex: "123 rue de Paris, Lyon")

        Returns:
            BuildingInfo ou None si pas trouvé
        """
        logger.info(f"Recherche bâtiment: {address}")

        # 1. Géocoder l'adresse (utiliser nominatim OSM)
        coords = self._geocode_address(address)
        if not coords:
            logger.warning(f"Adresse non trouvée: {address}")
            return None

        lat, lon = coords
        logger.info(f"Coordonnées: {lat}, {lon}")

        # 2. Extraire bâtiment à partir coordonnées
        return self.extract_from_coords(lat, lon, address)

    def extract_from_coords(self, lat: float, lon: float, address: Optional[str] = None,
                           radius: int = 50) -> Optional[BuildingInfo]:
        """Extraire infos bâtiment depuis coordonnées GPS

        Args:
            lat, lon: latitude/longitude
            address: adresse (optionnel)
            radius: rayon recherche en mètres

        Returns:
            BuildingInfo ou None
        """
        logger.info(f"Extraction depuis coords ({lat}, {lon})")

        # 1. Requête Overpass API (OSM) - plus rapide que WFS IGN
        building = self._query_osm_building(lat, lon, radius)

        if not building:
            logger.warning("Aucun bâtiment trouvé")
            return None

        logger.info(f"Bâtiment trouvé: {building}")

        # 2. Extraire infos
        info = self._extract_building_info(building, address)

        return info

    def _geocode_address(self, address: str) -> Optional[Tuple[float, float]]:
        """Géocoder adresse avec Nominatim (OSM)"""
        try:
            url = "https://nominatim.openstreetmap.org/search"
            params = {
                'q': address,
                'format': 'json',
                'limit': 1
            }
            resp = requests.get(url, params=params, headers=self.headers, timeout=5)
            resp.raise_for_status()
            results = resp.json()

            if results:
                result = results[0]
                return float(result['lat']), float(result['lon'])
        except Exception as e:
            logger.error(f"Erreur géocodage: {e}")

        return None

    def _query_osm_building(self, lat: float, lon: float, radius: int) -> Optional[Dict]:
        """Requête Overpass API pour récupérer bâtiment

        Returns:
        GeoJSON feature ou None
        """
        try:
            # Bbox autour du point (lat/lon +/- radius)
            lat_delta = radius / 111000  # 1 degré ≈ 111 km
            lon_delta = radius / (111000 * __import__('math').cos(__import__('math').radians(lat)))

            bbox = f"{lat - lat_delta},{lon - lon_delta},{lat + lat_delta},{lon + lon_delta}"

            # Overpass QL pour bâtiments (format amélioré)
            query = f"""[out:json];
    (
        way["building"]({bbox});
        relation["building"]({bbox});
    );
    out geom;"""

            logger.info(f"Requête Overpass: {query}")
        
            resp = requests.post(OVERPASS_URL, data=query, headers=self.headers, timeout=60)
        
            # Debug : afficher la réponse brute
            logger.info(f"Réponse Overpass (status {resp.status_code}): {resp.text[:200]}")
        
            resp.raise_for_status()

            data = resp.json()
            elements = data.get('elements', [])

            if elements:
                # Retourner le premier bâtiment (généralement le plus proche)
                logger.info(f"Bâtiment trouvé: {elements[0]}")
                return elements[0]
            else:
                logger.warning("Pas d'éléments dans la réponse Overpass")
        except Exception as e:
            logger.error(f"Erreur Overpass: {e}")

        return None

    def _extract_building_info(self, osm_element: Dict, address: Optional[str]) -> BuildingInfo:
        """Extraire infos du feature OSM

        Args:
            osm_element: feature Overpass API
            address: adresse optionnelle

        Returns:
            BuildingInfo rempli au maximum
        """
        info = BuildingInfo(address=address, source="OpenStreetMap")

        tags = osm_element.get('tags', {})
        geometry = osm_element.get('geometry', [])

        # Type de bâtiment
        building_type = tags.get('building', 'unknown')
        info.building_type = self._normalize_building_type(building_type)

        # Calculer surface depuis géométrie
        if geometry:
            coords = [(point['lon'], point['lat']) for point in geometry]
            if len(coords) > 2:
                from shapely.geometry import Polygon
                polygon = Polygon(coords)
                info.surface_m2 = self._polygon_area_m2(polygon)
                info.shape = self._detect_shape(polygon)

        # Hauteur (OSM a parfois)
        if 'height' in tags:
            try:
                # Parser "20", "20 m", etc.
                height_str = tags['height'].split()[0]
                info.height_m = float(height_str)
                info.confidence += 0.3
            except:
                pass

        # Nombre d'étages
        if 'building:levels' in tags:
            try:
                info.estimated_floors = int(tags['building:levels'])
                info.confidence += 0.2
            except:
                pass
        elif info.height_m:
            # Estimer étages depuis hauteur (3m par étage en moyenne)
            info.estimated_floors = max(1, int(info.height_m / 3.0))
            info.confidence += 0.1

        # Toit
        if 'roof:shape' in tags:
            info.roof_shape = tags['roof:shape']

        # Confiance globale
        info.confidence = min(1.0, info.confidence + 0.4)  # Baseline 0.4 pour OSM

        info.metadata = tags

        return info

    def _normalize_building_type(self, osm_type: str) -> str:
        """Normaliser type bâtiment OSM vers catégories métier"""
        mapping = {
            'commercial': 'commercial',
            'retail': 'commercial',
            'mall': 'commercial',
            'supermarket': 'commercial',
            'office': 'office',
            'hotel': 'hotel',
            'hospital': 'hospital',
            'residential': 'residential',
            'apartment': 'residential',
            'house': 'residential',
            'industrial': 'industrial',
            'warehouse': 'industrial',
            'factory': 'industrial',
            'public': 'public',
            'school': 'public',
            'museum': 'public',
            'airport': 'airport',
            'train_station': 'transport',
        }

        osm_type_lower = osm_type.lower()
        return mapping.get(osm_type_lower, osm_type_lower)

    def _polygon_area_m2(self, polygon) -> float:
        """Calculer surface polygone en m² (Lambert-93)"""
        from shapely.ops import transform
        polygon_m = transform(self.transformer.transform, polygon)
        return polygon_m.area

    def _detect_shape(self, polygon) -> str:
        """Détecter forme du bâtiment (rectangle, L-shape, irregular)"""
        # Simplification : regarder nombre coins et ratio dimensions
        exterior = polygon.exterior.coords[:-1]  # Sans dernier point (doublon)

        num_corners = len(exterior)

        if num_corners <= 4:
            return "rectangle"
        elif num_corners <= 8:
            return "complex"  # L-shape, T-shape, etc.
        else:
            return "irregular"


def main():
    """Exemple d'utilisation"""
    import argparse

    parser = argparse.ArgumentParser(description="Extracteur données IGN")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--address', help='Adresse à rechercher')
    group.add_argument('--coords', nargs=2, type=float, metavar=('LAT', 'LON'),
                      help='Coordonnées GPS')

    args = parser.parse_args()

    extractor = IGNExtractor()

    if args.address:
        result = extractor.extract_from_address(args.address)
    else:
        result = extractor.extract_from_coords(args.coords[0], args.coords[1])

    if result:
        print(result)
        #print(f"Résultat JSON: {json.dumps(result.to_dict(), indent=2, ensure_ascii=False)}")
    else:
        print("Aucun résultat")


if __name__ == "__main__":
    main()