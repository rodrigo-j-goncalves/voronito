# voronito

Command-line pipeline that turns a hierarchical CSV into a voronoi treemap:
a Python orchestrator drives a headless Node.js computation engine
(`d3-voronoi-treemap`), then exports either a clean, Inkscape/`progresSVG`-ready
**SVG** or a self-contained, D3-driven interactive **HTML** (embeddable in
Quarto via `<iframe>`).

## Setup

Requires Node.js/npm and Python 3.

```bash
npm install
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Usage

```bash
.venv/bin/python src/voronoi_treemap.py \
  --input data/biomass.csv \
  --output-svg output/biomass.svg \
  --output-html output/biomass.html \
  --shape circle \
  --unit "Gt C"
```

### CLI flags

| Flag | Default | Description |
|---|---|---|
| `--input` | *(required)* | Path to the input CSV |
| `--output-svg` | | Path to write the static SVG (at least one of `--output-svg`/`--output-html` is required) |
| `--output-html` | | Path to write the interactive HTML |
| `--shape` | `circle` | `circle`, `rectangle` (golden-ratio proportions, φ≈1.618:1 — independent of the canvas's own aspect ratio), `square` (equal sides), `ellipse`, `triangle`, `pentagon`, `hexagon`, `polygon:N` (any regular N-sided convex polygon, N≥3), or a path to an `.svg` file (optionally `path.svg#elementId`) to clip to an arbitrary polygon extracted from its `<path>`/`<polygon>`/`<polyline>` — the shape must be closed (a `<path>` needs an explicit `Z`; `<polyline>` is rejected as open by definition). The engine only supports **convex** clip polygons; a concave mask prints a warning and proceeds, but its concave regions (notches, waists) will be ignored/distorted in the output. |
| `--all-shapes` | off | Generate one output per built-in shape (`circle`, `rectangle`, `square`, `ellipse`, `triangle`, `pentagon`, `hexagon`) instead of a single `--shape`, each suffixed `_<shape>` before the extension (e.g. `--output-svg out.svg --all-shapes` → `out_circle.svg`, `out_rectangle.svg`, ...). Applies to both `--output-svg` and `--output-html` if both are given. |
| `--width`, `--height` | `800`, `800` | Canvas size in px used to *lay out* the shape (its own aspect ratio, e.g. rectangle's golden ratio, is independent of this). The exported SVG/HTML viewBox is then tightly cropped to the shape's own bounding box (+5% margin), not this nominal canvas — so a shape that doesn't fill a square canvas (e.g. rectangle) isn't left with a visibly empty margin. |
| `--seed` | `42` | PRNG seed for the layout (deterministic output) |
| `--title` | `Voronoi Treemap` | `<title>` for the HTML output |
| `--unit` | *(none)* | Unit label appended to values in tooltips, e.g. `"Gt C"`, `"USD"` |

## CSV data format

Explicit parent-child rows:

```
id,parent_id,name,value,color,description
Root,,Root Category,,,
,Root,Branch A,,#009E73,
,Branch A,Leaf 1,10,,optional description
```

- **`id`** — if given, used verbatim as the node's slug (and as the SVG element id: `cell-<id>` / `group-<id>`). If empty, derived from `name`: accented/special characters transliterated to ASCII, spaces and remaining non-alphanumeric characters stripped, and a numeric suffix appended starting at `2` on collision (e.g. `Mammals`, `Mammals2`).
- **`parent_id`** — the parent's `id`. Exactly one row must have an empty `parent_id` (the root).
- **`value`** — required and `> 0` on every leaf (node with no children). Internal/branch node values are left blank and computed by summing their descendants.
- **`color`** — optional hex color. If blank: top-level branches (direct children of the root) get a color from the [Okabe-Ito](https://jfly.uni-koeln.de/color/) colorblind-safe palette; deeper descendants inherit their branch's hue/saturation and vary only in lightness ("shades of" the parent color). An explicit `color` at any level overrides this and becomes the new base for its own subtree.
- **`description`** — optional free text, shown in the HTML tooltip.

## Demo datasets

- `data/biomass.csv` — global biomass by domain/phylum (Bar-On, Phillips & Milo, *PNAS* 2018), order-of-magnitude figures.
- `data/companies.csv` — reproduction of Visual Capitalist's ["World's 30 Largest Companies: Profit per $100 in Revenue"](https://www.visualcapitalist.com/ranked-how-profitable-are-the-worlds-largest-companies/) (Fortune Global 500, 2026 fiscal data); wedge size = the profit-per-$100 rate shown on each cell.
- `data/companies_summary.csv` — sector-level rollup of `companies.csv` (2-level hierarchy: root → 8 sectors, no individual companies); a simpler, less cluttered example.

`examples/` holds pre-generated outputs for all three, in every built-in shape
(`--all-shapes`) as both SVG and HTML — e.g. `examples/companies_hexagon.svg`.
Unlike `output/` (a gitignored scratch area for your own runs), `examples/`
is committed, so these are viewable without regenerating them. Regenerate
with, e.g.:

```bash
.venv/bin/python src/voronoi_treemap.py --input data/companies.csv \
  --output-svg examples/companies.svg --output-html examples/companies.html \
  --all-shapes --unit "per \$100 revenue" --title "World's 30 Largest Companies"
```

## Architecture

```
src/
  voronoi_treemap.py   CLI entry point
  hierarchy.py          CSV -> nested tree, id resolution
  colors.py              Okabe-Ito palette + shade assignment
  clip_svg.py            arbitrary polygon extraction from an SVG mask (--shape mask.svg)
  engine.py               subprocess bridge to compute_treemap.js
  compute_treemap.js     headless Node engine (d3-voronoi-treemap)
  geometry.py             shared tree+geometry merge, label fit/sizing
  svg_export.py           static SVG renderer
  html_export.py          interactive D3/HTML renderer
```

Each leaf's polygon/centroid/area is computed once by the Node engine and
consumed by both exporters, so the SVG and HTML outputs are always
geometrically identical.

## Notes

- Labels are omitted (not truncated) when a cell is too narrow to fit them — checked against the cell's actual width at the label's row, not just its bounding box, since voronoi cells are frequently wedge-shaped.
- Datasets with an extreme value range (many orders of magnitude between largest and smallest leaf, e.g. `biomass.csv`) will make the smallest leaves visually negligible regardless of layout settings — this is an inherent limitation of area-proportional treemaps, not a bug.
