# Running this workshop for a new campus

The workshop is driven by a **campus profile**: a folder under
`workshop/Includes/campuses/<slug>/` with a `campus.json` and five geojson files. Pick the
active campus with one line, `CAMPUS = "<slug>"`, in `workshop/Includes/Classroom-Setup-Common.py`.
`tamu` (Texas A&M) and `baylor` (Baylor University) are included as examples.

You need Python 3.9+ on your laptop (stdlib only for the tools) and a Databricks workspace
with Serverless, Genie and Databricks Apps.

## 1. Fork and branch

Fork this repo, then clone it and create a branch for your campus:

```bash
git clone https://github.com/<you>/data-intelligence-for-smarter-community && cd data-intelligence-for-smarter-community
git checkout -b campus/<slug>
```

## 2. Find the campus outline in OpenStreetMap

Search the campus on https://www.openstreetmap.org, click its outline and note the id
(e.g. `way/163627351` for Baylor). Or look it up from the command line:

```bash
curl -s -A "you@example.com" "https://nominatim.openstreetmap.org/search?q=Baylor+University+Waco&format=json&limit=3" \
  | python3 -c "import json,sys; [print(r['osm_type'], r['osm_id'], r['display_name']) for r in json.load(sys.stdin)]"
```

Pick the `amenity=university` way/relation that covers the main campus.

## 3. Generate the profile

```bash
python3 tools/new_campus.py \
  --slug baylor --name "Baylor University" --short-name Baylor --city "Waco, TX" \
  --event-name "Baylor Datathon" --boundary way/163627351 --primary-color "#154734"
```

This downloads named buildings from OpenStreetMap, maps them to the workshop's building
categories, and generates approximate zones, landmarks and synthetic cell sites. It takes
under a minute and prints a summary.

## 4. Review (about 30 minutes, by hand)

Open `workshop/Includes/campuses/<slug>/` and check:

- **`campus.json`**: `event_name`, `branding.primary_color`, and the `landmark_zones` /
  `cell_sites` names. They're auto-picked from the largest buildings, so rename or swap
  any that a local audience wouldn't recognise.
- **`geojson/buildings.geojson`**: spot-check `BLDG_USAGE`. The categories are guessed from
  OSM tags and names. Hotels and other off-campus buildings that mention the campus name get
  `Commercial`; delete them if you don't want them on the map.
- **`geojson/neighbourhoods.geojson`**: zones are auto-drawn clusters named by direction
  ("North Campus", ...). If you rename one, rename the matching `NEIGHBOURHOOD` values in
  `buildings.geojson` too. https://geojson.io is handy for redrawing a polygon.

## 5. Validate locally

```bash
python3 tools/validate_campus.py <slug>          # profile checks (stdlib only)

python3 -m venv .venv && .venv/bin/pip install -r tests/requirements.txt
.venv/bin/python -m pytest tests -q              # generator + app + branding, all campuses
```

Both must pass. Warnings from `validate_campus.py` are worth reading but don't block.

## 6. Switch the workshop to your campus and push

In `workshop/Includes/Classroom-Setup-Common.py` set:

```python
CAMPUS = "<slug>"
```

Then commit and push your branch.

## 7. Run it in a workspace

1. **Workspace → Create → Git folder**, using your fork's URL and your campus branch.
2. Open `workshop/00 - Course Overview` and connect to **Serverless**.
3. Run labs 01 → 06 in order. Check:
   - **Lab 01:** the setup output shows a **"Today's campus: <your campus>"** banner in your
     color, and the config table shows **Campus: <your campus>**.
   - **Lab 05:** the instructions cell prints Genie instructions naming your campus; paste those.
   - **Lab 02:** prints your campus bounding box.
   - **Lab 06:** prints *"Frontend re-branded for <campus>"*. The app map opens on your campus,
     in your color, and `<app-url>/api/campus` returns your profile.

**No permission to create a catalog?** (FE Vending Machine workspaces, for example, only allow
Default Storage catalogs from the UI.) Set `EXISTING_CATALOG` in `Classroom-Setup-Common.py`
to a catalog you can write to. The workshop then creates per-user schemas
(`<user>_bronze` / `_silver` / `_gold`) inside it.

**Re-using a workspace that already ran another campus?** Changing `CAMPUS` regenerates Bronze
automatically (the telemetry table is tagged `workshop.campus`). Labs 02–06 overwrite their own
tables, and Lab 06 redeploys the same app with the new campus.

## Still campus-specific (known gaps)

- **Lab notebook text** is campus-neutral ("your campus"). The campus name shows up at runtime:
  the setup banner in every lab, the Genie instructions printed in Lab 05, and the "you should
  see" line in Lab 06. The "Modified … for the TAMU Datathon" lines are attribution notices; keep
  them. `tests/test_notebook_text.py` fails if campus-specific text creeps back into a notebook.
- **The app's frontend** source isn't in the repo. Lab 06 patches the compiled bundle (center,
  color, names), which covers what attendees see, but layout or text changes beyond that need
  the React source.
- **Attribution**: keep the OpenStreetMap / ODbL credit and the "modified by" notices.
