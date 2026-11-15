#!/usr/bin/env python3
"""Bootstrap a new campus profile from OpenStreetMap.

Creates ``workshop/Includes/campuses/<slug>/`` with campus.json + geojson in the exact
shape the workshop expects. Stdlib only (no pip installs needed).

Example (Baylor University, Waco TX)::

    python3 tools/new_campus.py \\
        --slug baylor --name "Baylor University" --short-name Baylor \\
        --city "Waco, TX" --event-name "Baylor Datathon" \\
        --boundary way/163627351 --primary-color "#154734"

Find the boundary id by searching the campus on https://www.openstreetmap.org and
clicking the campus outline (usually an ``amenity=university`` way or relation), or:
    curl -A you@example.com "https://nominatim.openstreetmap.org/search?q=<campus>&format=json&limit=3"

What it does
  1. Downloads the campus boundary and every *named* OSM building in/near it.
  2. Keeps buildings whose centroid is inside the boundary (plus named buildings in the
     padded bbox whose name/operator mentions the campus, e.g. an off-boundary stadium).
  3. Maps OSM tags -> the workshop's BLDG_USAGE vocabulary (Academic, StudentHousing, ...).
  4. Generates approximate neighbourhood zones (k-means + convex hull), 10 synthetic
     cell sites, and 16 landmark zones from the largest buildings.
  5. Writes buildings / complexes / neighbourhoods / landuse / legal_boundary geojson and
     a draft campus.json, then prints a summary + things to review by hand.

Everything generated is a *draft*: review zone names, landmarks and cell-site names
before an event. Data © OpenStreetMap contributors, ODbL.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[1]
CAMPUSES = REPO / "workshop" / "Includes" / "campuses"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "smart-campus-template/0.1 (Databricks Smart Community workshop)"

Point = Tuple[float, float]  # (lon, lat), GeoJSON order


# ----------------------------------------------------------------------------- OSM I/O
def overpass(query: str, retries: int = 3) -> Dict:
    data = urllib.parse.urlencode({"data": query}).encode()
    for attempt in range(retries):
        req = urllib.request.Request(OVERPASS_URL, data=data, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001 - surface any network error after retries
            if attempt == retries - 1:
                raise SystemExit(f"Overpass request failed: {e}")
            time.sleep(5 * (attempt + 1))
    return {}


def parse_osm_ref(ref: str) -> Tuple[str, int]:
    m = re.fullmatch(r"(way|relation|rel)/(\d+)", ref.strip())
    if not m:
        raise SystemExit(f"--boundary must look like way/123 or relation/123, got {ref!r}")
    return ("relation" if m.group(1) in ("relation", "rel") else "way"), int(m.group(2))


def element_rings(el: Dict) -> List[List[Point]]:
    """Closed outer rings for an Overpass way/relation returned with `out geom`."""
    if el["type"] == "way":
        ring = [(p["lon"], p["lat"]) for p in el.get("geometry", [])]
        return [ring] if len(ring) >= 4 and ring[0] == ring[-1] else []
    rings = []
    for m in el.get("members", []):
        if m.get("role") == "outer" and m.get("geometry"):
            ring = [(p["lon"], p["lat"]) for p in m["geometry"]]
            if len(ring) >= 4 and ring[0] == ring[-1]:
                rings.append(ring)
    return rings


# ----------------------------------------------------------------------------- geometry
def m_per_deg(lat: float) -> Tuple[float, float]:
    return 111_132.954, 111_320.0 * math.cos(math.radians(lat))


def ring_area_m2(ring: List[Point]) -> float:
    lat0 = sum(p[1] for p in ring) / len(ring)
    my, mx = m_per_deg(lat0)
    pts = [(p[0] * mx, p[1] * my) for p in ring]
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:]))) / 2


def ring_centroid(ring: List[Point]) -> Point:
    pts = ring[:-1] if ring[0] == ring[-1] else ring
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def point_in_ring(pt: Point, ring: List[Point]) -> bool:
    x, y = pt
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def convex_hull(points: List[Point]) -> List[Point]:
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    return hull + [hull[0]]


def kmeans(points: List[Point], k: int, seed: int = 42, iters: int = 50) -> List[int]:
    """Tiny deterministic k-means (k-means++ init) on (lon, lat) scaled to metres."""
    if not points:
        return []
    k = max(1, min(k, len(points)))
    lat0 = sum(p[1] for p in points) / len(points)
    my, mx = m_per_deg(lat0)
    xy = [(p[0] * mx, p[1] * my) for p in points]
    rnd = random.Random(seed)
    cents = [xy[rnd.randrange(len(xy))]]
    while len(cents) < k:
        d2 = [min((x - cx) ** 2 + (y - cy) ** 2 for cx, cy in cents) for x, y in xy]
        r, acc = rnd.random() * sum(d2), 0.0
        for i, d in enumerate(d2):
            acc += d
            if acc >= r:
                cents.append(xy[i])
                break
    labels = [0] * len(xy)
    for _ in range(iters):
        labels = [min(range(k), key=lambda c: (x - cents[c][0]) ** 2 + (y - cents[c][1]) ** 2) for x, y in xy]
        new = []
        for c in range(k):
            members = [xy[i] for i, l in enumerate(labels) if l == c]
            new.append((sum(m[0] for m in members) / len(members), sum(m[1] for m in members) / len(members))
                       if members else cents[c])
        if new == cents:
            break
        cents = new
    return labels


def compass(from_pt: Point, to_pt: Point) -> str:
    lat0 = from_pt[1]
    my, mx = m_per_deg(lat0)
    dx, dy = (to_pt[0] - from_pt[0]) * mx, (to_pt[1] - from_pt[1]) * my
    ang = (math.degrees(math.atan2(dx, dy)) + 360) % 360
    return ["North", "Northeast", "East", "Southeast", "South", "Southwest", "West", "Northwest"][int((ang + 22.5) // 45) % 8]


# ----------------------------------------------------------------------------- tag mapping
_RX = lambda s: re.compile(s, re.I)  # noqa: E731
NAME_RULES = [
    ("Commercial", _RX(r"\b(hotel|inn|suites|motel)\b")),
    ("Parking", _RX(r"\b(parking|garage)\b")),
    ("Commons", _RX(r"\b(student (center|union|life)|union|dining|commons|community center|food hall|bookstore)\b")),
    ("Athletics", _RX(r"\b(stadium|arena|field ?house|natatorium|ballpark|athletics?|sports|fitness|recreation|"
                      r"tennis|softball|baseball|soccer|track|golf|basketball|football|gym(nasium)?|aquatic)\b")),
    ("StudentHousing", _RX(r"\b(residence|residential|dorm(itory)?|village|apartments?|living|house|towers?)\b")),
    ("Research", _RX(r"\b(research|laborator(y|ies)|institute|observatory|sciences? building|lab)\b")),
    ("Administrative", _RX(r"\b(administration|admissions|president|alumni|chancellor|bursar|registrar|"
                           r"one bear place|welcome)\b")),
    ("Operations", _RX(r"\b(power ?plant|physical plant|chiller|utility|utilities|facilities|maintenance|warehouse|central plant|"
                       r"police|steam|energy plant)\b")),
    ("Services", _RX(r"\b(chapel|church|library|museum|health|clinic|counsel|career|hospital|theat(er|re)|"
                     r"auditorium|concert|hall of fame|art)\b")),
]
TAG_RULES = {
    "dormitory": "StudentHousing", "residential": "StudentHousing", "apartments": "StudentHousing",
    "house": "Housing", "stadium": "Athletics", "sports_hall": "Athletics", "sports_centre": "Athletics",
    "grandstand": "Athletics", "parking": "Parking", "garage": "Parking", "garages": "Parking",
    "carport": "Parking", "church": "Services", "chapel": "Services", "cathedral": "Services",
    "hospital": "Services", "office": "Administrative", "government": "Administrative",
    "commercial": "Commercial", "retail": "Commercial", "supermarket": "Commercial",
    "industrial": "Operations", "service": "Operations", "warehouse": "Operations", "hangar": "Operations",
    "university": "Academic", "college": "Academic", "school": "Academic",
}


def classify(tags: Dict[str, str]) -> str:
    name = tags.get("name", "")
    if tags.get("tourism") in ("hotel", "motel", "hostel", "guest_house"):
        return "Commercial"
    for usage, rx in NAME_RULES:
        if rx.search(name):
            return usage
    if tags.get("amenity") in ("parking",):
        return "Parking"
    if tags.get("leisure") in ("stadium", "sports_centre", "sports_hall", "fitness_centre"):
        return "Athletics"
    if tags.get("amenity") in ("library", "place_of_worship", "theatre", "arts_centre", "clinic"):
        return "Services"
    if tags.get("shop") or tags.get("amenity") in ("restaurant", "cafe", "fast_food", "bank"):
        return "Commercial"
    usage = TAG_RULES.get(tags.get("building", ""), None)
    if usage:
        return usage
    if tags.get("amenity") in ("university", "college", "school") or tags.get("building") == "yes":
        return "Academic"
    return "Other"


def levels(tags: Dict[str, str], usage: str) -> int:
    for k in ("building:levels", "levels"):
        try:
            return max(1, int(float(tags[k].split(";")[0])))
        except (KeyError, ValueError):
            pass
    return {"StudentHousing": 4, "Academic": 3, "Research": 3, "Parking": 4, "Athletics": 2}.get(usage, 2)


def short_code(name: str) -> str:
    words = [w for w in re.findall(r"[A-Za-z]+", name) if w.lower() not in ("of", "the", "and", "for", "at", "hall")]
    return ("".join(w[0] for w in words[:4]) or name[:3]).upper()


# ----------------------------------------------------------------------------- build
def feature(props: Dict, rings: List[List[Point]], multi: bool = True) -> Dict:
    coords = [[[list(p) for p in r]] for r in rings]
    geom = {"type": "MultiPolygon", "coordinates": coords} if multi else \
        {"type": "Polygon", "coordinates": coords[0]}
    return {"type": "Feature", "properties": props, "geometry": geom}


def fc(features: List[Dict]) -> Dict:
    return {"type": "FeatureCollection", "features": features}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--slug", required=True, help="folder name, lowercase, e.g. baylor")
    ap.add_argument("--name", required=True, help='full name, e.g. "Baylor University"')
    ap.add_argument("--short-name", required=True, help="short label for the app, e.g. Baylor")
    ap.add_argument("--city", required=True, help='e.g. "Waco, TX"')
    ap.add_argument("--boundary", required=True, help="OSM campus outline: way/<id> or relation/<id>")
    ap.add_argument("--event-name", default=None, help='e.g. "Baylor Datathon" (default: "<short> Workshop")')
    ap.add_argument("--primary-color", default="#1B3139", help="brand hex color (default Databricks navy)")
    ap.add_argument("--zones", type=int, default=7, help="number of neighbourhood zones (default 7)")
    ap.add_argument("--pad-m", type=float, default=150.0, help="bbox padding in metres (default 150)")
    ap.add_argument("--template", default="tamu", help="profile to copy data_window from (default tamu)")
    ap.add_argument("--force", action="store_true", help="overwrite an existing campus folder")
    a = ap.parse_args(argv)

    slug = a.slug.strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_]*", slug):
        raise SystemExit("--slug must be lowercase letters/digits/underscore, starting with a letter")
    out_dir = CAMPUSES / slug
    if out_dir.exists() and not a.force:
        raise SystemExit(f"{out_dir} already exists (use --force to overwrite)")

    # 1) boundary --------------------------------------------------------------------
    btype, bid = parse_osm_ref(a.boundary)
    print(f"Fetching boundary {btype}/{bid} ...")
    b = overpass(f"[out:json][timeout:60];{btype}({bid});out geom tags;")
    if not b.get("elements"):
        raise SystemExit(f"OSM {btype}/{bid} not found")
    bel = b["elements"][0]
    boundary = element_rings(bel)
    if not boundary:
        raise SystemExit(f"OSM {btype}/{bid} has no closed outer ring; pick the campus outline way/relation")
    all_b = [p for r in boundary for p in r]
    s, n = min(p[1] for p in all_b), max(p[1] for p in all_b)
    w, e = min(p[0] for p in all_b), max(p[0] for p in all_b)
    lat_c = (s + n) / 2
    my, mx = m_per_deg(lat_c)
    pad_lat, pad_lon = a.pad_m / my, a.pad_m / mx
    qs, qw, qn, qe = s - 4 * pad_lat, w - 4 * pad_lon, n + 4 * pad_lat, e + 4 * pad_lon

    # 2) buildings -------------------------------------------------------------------
    print("Fetching named buildings ...")
    q = (f"[out:json][timeout:120];(way[\"building\"][\"name\"]({qs},{qw},{qn},{qe});"
         f"relation[\"building\"][\"name\"]({qs},{qw},{qn},{qe}););out geom tags;")
    els = overpass(q).get("elements", [])
    name_rx = re.compile(re.escape(a.short_name) + "|" + re.escape(a.name), re.I)
    kept, seen_names = [], Counter()
    for el in sorted(els, key=lambda x: (x["type"], x["id"])):
        rings = element_rings(el)
        if not rings:
            continue
        tags = el.get("tags", {})
        c = ring_centroid(rings[0])
        inside = any(point_in_ring(c, r) for r in boundary)
        affiliated = bool(name_rx.search(tags.get("name", "") + " " + tags.get("operator", "")))
        if not (inside or affiliated):
            continue
        kept.append((el, rings, tags, c))
    if len(kept) < 10:
        raise SystemExit(f"Only {len(kept)} named buildings found; check the boundary id")

    # names must be unique (the app looks footprints up by NAME)
    for _, _, tags, _ in kept:
        seen_names[tags["name"]] += 1
    dup_idx: Dict[str, int] = defaultdict(int)

    prefix = slug[0].upper()
    buildings = []
    for i, (el, rings, tags, c) in enumerate(kept, start=1):
        name = tags["name"].strip()
        if seen_names[name] > 1:
            dup_idx[name] += 1
            name = f"{name} ({dup_idx[name]})"
        usage = classify(tags)
        addr = " ".join(x for x in (tags.get("addr:housenumber"), tags.get("addr:street")) if x) or None
        buildings.append({
            "props": {
                "BLDG_UID": f"{prefix}BL{10000 + i}",
                "NAME": name,
                "BLDG_CODE": tags.get("ref") or short_code(name),
                "SHORTNAME": tags.get("short_name") or name,
                "PRIMARY_ADDRESS": addr,
                "CONSTR_STATUS": "Complete",
                "BLDG_USAGE": usage,
                "BLDG_SEC_USAGE": None,
                "JURISDICTION": a.short_name,
                "NEIGHBOURHOOD": None,  # filled after zoning
                "MAX_FLOORS": levels(tags, usage),
                "OSM_ID": f"{el['type']}/{el['id']}",
            },
            "rings": rings, "centroid": c, "area": sum(ring_area_m2(r) for r in rings),
        })

    # bbox = boundary + kept buildings, padded
    pts = all_b + [p for bl in buildings for r in bl["rings"] for p in r]
    bb = {"lat_min": round(min(p[1] for p in pts) - pad_lat, 4), "lat_max": round(max(p[1] for p in pts) + pad_lat, 4),
          "lon_min": round(min(p[0] for p in pts) - pad_lon, 4), "lon_max": round(max(p[0] for p in pts) + pad_lon, 4)}
    cents = [bl["centroid"] for bl in buildings]
    center = (sum(p[0] for p in cents) / len(cents), sum(p[1] for p in cents) / len(cents))

    # 3) zones -----------------------------------------------------------------------
    k = max(2, min(a.zones, len(buildings) // 12))
    labels = kmeans(cents, k)
    groups: Dict[int, List[dict]] = defaultdict(list)
    for bl, lab in zip(buildings, labels):
        groups[lab].append(bl)
    gcent = {g: (sum(b_["centroid"][0] for b_ in m) / len(m), sum(b_["centroid"][1] for b_ in m) / len(m))
             for g, m in groups.items()}
    central = min(gcent, key=lambda g: (gcent[g][0] - center[0]) ** 2 + (gcent[g][1] - center[1]) ** 2)
    zone_names: Dict[int, str] = {}
    used = Counter()
    for g in sorted(groups, key=lambda g: -len(groups[g])):
        nm = "Central Campus" if g == central else f"{compass(center, gcent[g])} Campus"
        if used[nm]:
            biggest = max(groups[g], key=lambda b_: b_["area"])["props"]["NAME"]
            nm = f"{biggest} Area"
        used[nm] += 1
        zone_names[g] = nm
    zone_feats, landuse_feats = [], []
    for zid, g in enumerate(sorted(groups, key=lambda g: zone_names[g]), start=1):
        for bl in groups[g]:
            bl["props"]["NEIGHBOURHOOD"] = zone_names[g]
        hull = convex_hull([p for bl in groups[g] for r in bl["rings"] for p in r])
        if len(hull) < 4:
            continue
        zone_feats.append(feature({"ID": zid, "NAME": zone_names[g], "OTHER": "Demo zone"}, [hull], multi=False))
        landuse_feats.append(feature({"ID": zid, "NAME": zone_names[g], "OTHER": "Demo zone", "LANDUSE": "Campus"},
                                     [hull], multi=False))

    # 4) complexes (residence halls + commons) --------------------------------------
    complexes = []
    for j, bl in enumerate([b_ for b_ in buildings if b_["props"]["BLDG_USAGE"] in ("StudentHousing", "Commons")], 1):
        gba = int(round(bl["area"] * bl["props"]["MAX_FLOORS"]))
        u = bl["props"]["BLDG_USAGE"]
        complexes.append(feature({
            "OBJECTID": j, "BCOM_UID": f"{prefix}BC{10000 + j}", "NAME": bl["props"]["NAME"], "STATUS": "Complete",
            "BCOM_USAGE": u, "USAGE_TYPE": u, "BCOM_CLASS": None, "GBA": gba,
            "UNITS": max(20, gba // 40) if u == "StudentHousing" else 0, "NOTES": "Source: OpenStreetMap",
            "OSM_ID": bl["props"]["OSM_ID"]}, bl["rings"]))

    # 5) landmarks + cell sites -------------------------------------------------------
    by_area = [b_ for b_ in sorted(buildings, key=lambda b_: -b_["area"])
               if b_["props"]["BLDG_USAGE"] not in ("Commercial", "Other")]
    picks: List[dict] = []
    for usage in ("Athletics", "Commons", "Services", "Academic", "StudentHousing", "Research", "Parking",
                  "Administrative"):
        cand = next((b_ for b_ in by_area if b_["props"]["BLDG_USAGE"] == usage and b_ not in picks), None)
        if cand:
            picks.append(cand)
    for b_ in by_area:
        if len(picks) >= 16:
            break
        if b_ not in picks and b_["props"]["BLDG_USAGE"] != "Parking":
            picks.append(b_)
    ztype = {"Athletics": "recreational", "StudentHousing": "residential", "Housing": "residential",
             "Commons": "transit", "Parking": "transit"}
    landmarks = [{
        "zone_id": f"ZONE_{i:02d}", "name": b_["props"]["NAME"], "type": ztype.get(b_["props"]["BLDG_USAGE"], "academic"),
        "lat": round(b_["centroid"][1], 4), "lon": round(b_["centroid"][0], 4),
        "footprint": {"source": "buildings", "name": b_["props"]["NAME"]}} for i, b_ in enumerate(picks[:16], 1)]

    site_labels = kmeans(cents, 10, seed=7)
    sites = []
    for sidx in sorted(set(site_labels)):
        members = [bl for bl, l in zip(buildings, site_labels) if l == sidx]
        lon = sum(m["centroid"][0] for m in members) / len(members)
        lat = sum(m["centroid"][1] for m in members) / len(members)
        campus_bldgs = [m for m in buildings if m["props"]["BLDG_USAGE"] not in ("Commercial", "Parking", "Other")]
        named = [m for m in members if m in campus_bldgs]
        if named:
            anchor = max(named, key=lambda m: m["area"])["props"]["NAME"]
        else:  # cluster of off-campus/parking only: name it after the nearest campus building
            anchor = min(campus_bldgs, key=lambda m: (m["centroid"][0] - lon) ** 2 + (m["centroid"][1] - lat) ** 2
                         )["props"]["NAME"]
        sites.append((lat, lon, anchor))
    sites.sort(key=lambda t: (-t[0], t[1]))  # north to south
    cell_sites = [{"site_id": f"SITE_{i:02d}", "name": f"Near {anchor}", "lat": round(lat, 4), "lon": round(lon, 4)}
                  for i, (lat, lon, anchor) in enumerate(sites, 1)]

    # 6) campus.json ------------------------------------------------------------------
    tmpl = CAMPUSES / a.template / "campus.json"
    data_window = json.loads(tmpl.read_text())["data_window"] if tmpl.exists() else {
        "end": "2026-11-06T00:00:00", "days": 30,
        "study_crunch_start": "2026-10-26T00:00:00", "study_crunch_end": "2026-11-01T23:59:59"}
    campus = {
        "slug": slug, "name": a.name, "short_name": a.short_name, "city": a.city,
        "event_name": a.event_name or f"{a.short_name} Workshop",
        "branding": {"primary_color": a.primary_color},
        "map": {
            "center": {"lat": round(center[1], 4), "lon": round(center[0], 4)},
            "bbox": bb,
            "bbox_description": f"{a.name} campus (OSM {btype}/{bid}) plus {int(a.pad_m)} m",
            "meters_per_degree_lon": round(m_per_deg(center[1])[1], 1),
        },
        "data_window": data_window,
        "landmark_zones": landmarks,
        "cell_sites": cell_sites,
        "attribution": (f"Map data © OpenStreetMap contributors (ODbL). Neighbourhood zones, landmarks and cell "
                        f"sites were generated automatically for this demo and are not official {a.name} data."),
        "generated_by": {"tool": "tools/new_campus.py", "boundary": f"{btype}/{bid}",
                         "osm_timestamp": b.get("osm3s", {}).get("timestamp_osm_base")},
    }

    # 7) write ----------------------------------------------------------------------
    gdir = out_dir / "geojson"
    gdir.mkdir(parents=True, exist_ok=True)

    def dump(path: Path, obj) -> None:
        path.write_text(json.dumps(obj, indent=1 if path.suffix == ".json" and path.name == "campus.json" else None,
                                   ensure_ascii=False) + "\n", encoding="utf-8")

    dump(gdir / "buildings.geojson", fc([feature(bl["props"], bl["rings"]) for bl in buildings]))
    dump(gdir / "complexes.geojson", fc(complexes))
    dump(gdir / "neighbourhoods.geojson", fc(zone_feats))
    dump(gdir / "landuse.geojson", fc(landuse_feats))
    dump(gdir / "legal_boundary.geojson", fc([feature({"NAME": bel.get("tags", {}).get("name", a.name),
                                                       "SOURCE": "OpenStreetMap"}, boundary)]))
    (out_dir / "campus.json").write_text(json.dumps(campus, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # 8) summary --------------------------------------------------------------------
    usage_counts = Counter(bl["props"]["BLDG_USAGE"] for bl in buildings)
    print(f"\nWrote {out_dir}")
    print(f"  buildings      {len(buildings)}  {dict(usage_counts.most_common())}")
    print(f"  complexes      {len(complexes)} (residence halls + commons)")
    print(f"  zones          {len(zone_feats)}: {', '.join(sorted(zone_names.values()))}")
    print(f"  landmarks      {len(landmarks)}, cell sites {len(cell_sites)}")
    print(f"  center         {campus['map']['center']}   bbox {bb}")
    print("\nReview by hand before an event:")
    print("  - zone NAMEs in geojson/neighbourhoods.geojson (and NEIGHBOURHOOD in buildings.geojson)")
    print("  - BLDG_USAGE for buildings classified 'Other' or 'Academic' by default")
    print("  - landmark_zones / cell_sites names in campus.json, branding.primary_color, event_name")
    print(f"\nThen validate:  python3 tools/validate_campus.py {slug}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
