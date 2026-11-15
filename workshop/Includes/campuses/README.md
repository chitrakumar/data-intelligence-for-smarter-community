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
| App frontend (Lab 06 re-brands the compiled bundle copy) | `name`, `short_name`, `city`, `map.center`, `branding.primary_color` |

Bronze telemetry is tagged with the campus it was generated for
(`workshop.campus` table property on `sc_access_events`), so changing `CAMPUS` regenerates it on
the next lab setup run.

## Adding a new school

See [`NEW_CAMPUS.md`](../../../NEW_CAMPUS.md) at the repo root. In short:

```bash
python3 tools/new_campus.py --slug <slug> --name "<Full Name>" --short-name <Short> \
    --city "<City, ST>" --boundary way/<osm-id> --primary-color "#RRGGBB"
python3 tools/validate_campus.py <slug>
```

Then review the generated names, set `CAMPUS = "<slug>"` and run the labs.

### Building a profile by hand

If you don't use `tools/new_campus.py`, the files must use these properties:

| File | Properties used |
|---|---|
| `buildings.geojson` | `BLDG_UID` (unique, used as `bldg_uid` everywhere), `NAME` (unique), `CONSTR_STATUS` (only `"Complete"` rows are used), `BLDG_USAGE`, `MAX_FLOORS`, `BLDG_CODE`, `PRIMARY_ADDRESS`, `NEIGHBOURHOOD` |
| `complexes.geojson` | `BCOM_UID`, `NAME`, `GBA`, `UNITS`, `USAGE_TYPE` |
| `neighbourhoods.geojson` | `ID`, `NAME` (Polygon) |

`BLDG_USAGE` vocabulary: `Housing`, `StudentHousing`, `Academic`, `Research`, `Services`,
`Operations`, `Administrative`, `Athletics`, `Commons`, `Parking`, `Commercial`, `Other`.

In `campus.json`: `map.center` must be inside `map.bbox`, and every building, landmark and
cell site you care about must be inside the bbox too (Lab 02 drops anything outside).

## Not yet driven by the profile

- **App frontend** (`reference_code/app/frontend/dist/`): only the compiled bundle is in the repo.
  Lab 06 patches the student's copy (`frontend_branding.py`: map center, brand color, campus
  names, building count). Once the React source is available, it should read `/api/campus` instead.
- **Repo READMEs** (root `README.md` intro and "About this edition") still describe the Texas A&M edition. The lab notebooks themselves are campus-neutral and render the campus name at runtime.
