"""
Hauteur d'un bâtiment à partir du MNH LiDAR HD (service WMS de l'IGN).

Étapes :
1. On trouve le bâtiment BD TOPO qui contient le point (ou le plus proche).
2. On convertit son contour en Lambert 93 (EPSG:2154).
3. On demande au WMS un GeoTIFF de l'emprise du bâtiment (pas de 0,5 m).
4. On ne garde que les pixels à l'intérieur du contour, sans les -9999.
5. On affiche min, médiane, 90e percentile et max.

Usage :
    python src/lidar_height.py --coords 2.3522 48.8566
"""

import argparse
import math

import numpy as np
import pyproj
import requests
from rasterio.features import geometry_mask
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds
from shapely.geometry import Point, shape
import shapely

WFS_URL = "https://data.geopf.fr/wfs/ows"
WMS_URL = "https://data.geopf.fr/wms-r/ows"
BDTOPO_TYPE = "BDTOPO_V3:batiment"
MNH_LAYER = "IGNF_LIDAR-HD_MNH_ELEVATION.ELEVATIONGRIDCOVERAGE.LAMB93"
RESOLUTION = 0.5          # m, pas du MNH LiDAR HD
NODATA = -9999            # valeur conventionnelle des nœuds vides
MARGIN = 5.0              # m de marge autour du bâtiment
HEADERS = {"User-Agent": "pfe-5g-devis/0.1"}

# always_xy=True : ordre longitude, latitude (puis x, y en Lambert 93)
to_l93 = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:2154", always_xy=True).transform


def fetch_building(lon: float, lat: float, delta: float = 0.0005):
    """Renvoie (géométrie en Lambert 93, propriétés BD TOPO, contient_le_point)."""
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": BDTOPO_TYPE,
        "bbox": f"{lon - delta},{lat - delta},{lon + delta},{lat + delta},EPSG:4326",
        "srsName": "EPSG:4326",
        "outputFormat": "application/json",
        "count": 50,
    }
    r = requests.get(WFS_URL, params=params, headers=HEADERS, timeout=60)
    r.raise_for_status()
    features = r.json().get("features", [])
    if not features:
        raise SystemExit("Aucun bâtiment BD TOPO trouvé autour de ce point.")

    point = Point(lon, lat)
    best = None
    for f in features:
        geom = shape(f["geometry"])
        inside = geom.contains(point)
        dist = geom.distance(point)
        # on préfère un bâtiment qui contient le point, sinon le plus proche
        key = (0 if inside else 1, dist)
        if best is None or key < best[0]:
            best = (key, geom, f["properties"], inside)

    _, geom_wgs84, props, inside = best
    geom_l93 = shapely.transform(
    geom_wgs84,
    lambda c: np.column_stack(to_l93(c[:, 0], c[:, 1])),
   )
    return geom_l93, props, inside


def fetch_mnh(geom_l93):
    """Télécharge un GeoTIFF du MNH autour du bâtiment. Renvoie (tableau, transform, nodata)."""
    minx, miny, maxx, maxy = geom_l93.bounds
    # on cale l'emprise sur la grille de 0,5 m
    minx = math.floor((minx - MARGIN) / RESOLUTION) * RESOLUTION
    miny = math.floor((miny - MARGIN) / RESOLUTION) * RESOLUTION
    maxx = math.ceil((maxx + MARGIN) / RESOLUTION) * RESOLUTION
    maxy = math.ceil((maxy + MARGIN) / RESOLUTION) * RESOLUTION
    width = int(round((maxx - minx) / RESOLUTION))
    height = int(round((maxy - miny) / RESOLUTION))

    params = {
        "SERVICE": "WMS",
        "VERSION": "1.3.0",
        "REQUEST": "GetMap",
        "LAYERS": MNH_LAYER,
        "STYLES": "normal",
        "CRS": "EPSG:2154",
        "BBOX": f"{minx},{miny},{maxx},{maxy}",
        "WIDTH": width,
        "HEIGHT": height,
        "FORMAT": "image/geotiff",
    }
    r = requests.get(WMS_URL, params=params, headers=HEADERS, timeout=120)
    r.raise_for_status()
    if "xml" in r.headers.get("Content-Type", ""):
        raise RuntimeError(f"Le WMS a renvoyé une erreur : {r.text[:500]}")

    with MemoryFile(r.content) as mem, mem.open() as src:
        if src.count != 1:
            raise RuntimeError(f"Attendu 1 bande, reçu {src.count} : vérifier le format renvoyé.")
        data = src.read(1).astype("float64")
        nodata = src.nodata

    transform = from_bounds(minx, miny, maxx, maxy, width, height)
    return data, transform, nodata


def height_stats(data, transform, nodata, geom_l93):
    """Statistiques de hauteur sur les pixels situés dans le contour du bâtiment."""
    inside = geometry_mask([geom_l93], out_shape=data.shape, transform=transform, invert=True)
    valid = inside & np.isfinite(data) & (data != NODATA)
    if nodata is not None:
        valid &= data != nodata
    values = data[valid]
    if values.size == 0:
        return None
    return {
        "n_pixels": int(values.size),
        "min": float(values.min()),
        "median": float(np.median(values)),
        "p90": float(np.percentile(values, 90)),
        "max": float(values.max()),
    }

def geocode(address: str):
    """Adresse -> (lon, lat, adresse trouvée) via Nominatim."""
    r = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": address, "format": "json", "limit": 1, "countrycodes": "fr"},
        headers=HEADERS,
        timeout=30,
    )
    r.raise_for_status()
    results = r.json()
    if not results:
        raise SystemExit(f"Adresse introuvable : {address}")
    hit = results[0]
    return float(hit["lon"]), float(hit["lat"]), hit["display_name"]

def main():
    parser = argparse.ArgumentParser(description="Hauteur d'un bâtiment via le MNH LiDAR HD")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--address", help="Adresse, ex : 'Hôtel de ville, Paris'")
    group.add_argument("--coords", nargs=2, type=float, metavar=("LON", "LAT"))
    args = parser.parse_args()

    if args.address:
        lon, lat, found = geocode(args.address)
        print(f"Adresse trouvée : {found}")
    else:
        lon, lat = args.coords

    geom_l93, props, inside = fetch_building(lon, lat)
    print(f"Bâtiment BD TOPO : {props.get('cleabs')}")
    print(f"  contient le point : {'oui' if inside else 'non (le plus proche)'}")
    print(f"  surface au sol    : {geom_l93.area:.0f} m²")
    print(f"  hauteur BD TOPO   : {props.get('hauteur')} m")

    data, transform, nodata = fetch_mnh(geom_l93)
    stats = height_stats(data, transform, nodata, geom_l93)
    if stats is None:
        print("Aucune donnée LiDAR valide sur ce bâtiment.")
        return

    print("Hauteur LiDAR (MNH)")
    print(f"  pixels utilisés   : {stats['n_pixels']}")
    print(f"  min               : {stats['min']:.1f} m")
    print(f"  médiane           : {stats['median']:.1f} m")
    print(f"  90e percentile    : {stats['p90']:.1f} m")
    print(f"  max               : {stats['max']:.1f} m")


if __name__ == "__main__":
    main()

# ---------------------------------------------------------------------------
# Explication des valeurs affichées
#
# Bâtiment BD TOPO : identifiant unique du bâtiment dans la base IGN (cleabs).
# contient le point : "oui" si le point GPS tombe dans le contour du bâtiment,
#                     "non" si le script a pris le bâtiment le plus proche.
# surface au sol    : emprise du bâtiment vu du dessus, en m².
#                     Ce n'est pas la surface de tous les étages.
# hauteur BD TOPO   : hauteur annoncée par l'IGN (interpolée, non mesurée).
#
# pixels utilisés   : nombre de pixels LiDAR à l'intérieur du contour.
#                     Un pixel = 0,5 m x 0,5 m = 0,25 m².
#                     Pour vérifier : pixels x 0,25 doit donner la surface au sol.
# min               : hauteur la plus basse dans le contour. Souvent du sol
#                     (cour, bord) : à ignorer pour la hauteur du bâtiment.
# médiane           : valeur du milieu. La moitié des pixels est en dessous,
#                     l'autre moitié au-dessus. Hauteur "typique", robuste.
# 90e percentile    : 90 % des pixels sont en dessous. Hauteur des parties
#                     hautes (tour, beffroi), sans les pointes isolées.
# max               : pixel le plus haut. Sensible au bruit (antenne, arbre,
#                     erreur) : ne pas l'utiliser seul.
#
# Toutes les hauteurs sont en mètres au-dessus du sol (MNH).
# ---------------------------------------------------------------------------