# Campus profiles

Each folder here is one campus. The active one is picked by `CAMPUS` in
`Includes/Classroom-Setup-Common.py`.

```
campuses/<slug>/
├── campus.json
└── geojson/
    ├── buildings.geojson        required
    ├── complexes.geojson        required (residence complexes)
    ├── neighbourhoods.geojson   required (become dim_zones in Lab 02)
    ├── landuse.geojson          optional, not read by the labs/app today
    └── legal_boundary.geojson   optional, not read by the labs/app today
```

## What follows `CAMPUS`

| Piece | Reads |
|---|---|
| Synthetic telemetry (Classroom-Setup → `smart_campus_generators.py`) | `campus.json` (`map`, `data_window`, `cell_sites`) + `buildings.geojson`, `complexes.geojson` |
| Geodata Volume (Lab 01/02 ingest) | `buildings.geojson`, `neighbourhoods.geojson` |
| Lab 02 bounding-box check | `campus.json` `map.bbox` |
| App backend (Lab 06 bundles the profile into `server/campus/`) | geojson, `landmark_zones[].footprint`, `short_name`; `/api/campus` exposes name, branding, center and bbox |

Bronze telemetry is tagged with the campus it was generated for
(`workshop.campus` table property on `sc_access_events`), so changing `CAMPUS` regenerates it on
the next lab setup run.

## Adding a new school

1. `cp -R campuses/tamu campuses/<slug>`
2. **Geodata.** Export the campus from OpenStreetMap (e.g. Overpass or OSMnx) and convert it to the
   property names below. Keep the ODbL attribution.

   | File | Properties used |
   |---|---|
   | `buildings.geojson` | `BLDG_UID` (unique, used as `bldg_uid` everywhere), `NAME`, `CONSTR_STATUS` (only `"Complete"` rows are used), `BLDG_USAGE`, `MAX_FLOORS`, `BLDG_CODE`, `PRIMARY_ADDRESS`, `NEIGHBOURHOOD` |
   | `complexes.geojson` | `BCOM_UID`, `NAME`, `GBA`, `UNITS`, `USAGE_TYPE` |
   | `neighbourhoods.geojson` | `ID`, `NAME` (Polygon) |

   `BLDG_USAGE` values map to categories via: `Housing`, `StudentHousing`, `Academic`, `Research`,
   `Services`, `Operations`, `Administrative`, `Athletics`, `Commons`, `Parking`, `Commercial`
   (anything else becomes `Other`).
3. **`campus.json`.** Update:
   - `slug` (must match the folder name), `name`, `short_name`, `city`, `event_name`, `branding.primary_color`
   - `map.center`, `map.bbox` (must contain every building you want kept; the center must sit inside the bbox)
   - `map.meters_per_degree_lon`: about `111320 * cos(center latitude)`. You can delete it to have that computed.
   - `data_window`: the 30-day window end date and the "study crunch" week (exam period) inside it
   - `cell_sites`: about 10 synthetic tower locations spread across the campus
   - `landmark_zones`: named landmarks; `footprint` points at a building `NAME` in the geojson, or `null` for a circle
   - `attribution`
4. Set `CAMPUS = "<slug>"` in `Classroom-Setup-Common.py` and run Lab 01. `load_campus()` validates
   the profile and fails early with a clear message if keys or files are missing.

## Not yet driven by the profile

- **App frontend** (`reference_code/app/frontend/dist/`): only the compiled bundle is in the repo.
  The map center, maroon color, "TAMU" badge/title and dataset descriptions are baked into
  `assets/index-*.js`. Once the React source is available, it should read `/api/campus` instead.
- **Notebook prose** (lab markdown, header color, the course README): still TAMU-specific text.
