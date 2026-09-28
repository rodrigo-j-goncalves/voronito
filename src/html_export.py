"""Renders a standalone, D3-driven interactive HTML view of computed treemap
geometry: responsive SVG, hover tooltips (hierarchy path, value, % of parent/
total), and hover highlighting of the hovered cell's branch. Self-contained
(D3 loaded via CDN) so it can be embedded directly via a Quarto <iframe>.
"""

from __future__ import annotations

import json

from geometry import merge_tree_and_geometry, ancestors_of, label_layout

_D3_CDN = "https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"


def _polygon_path_d(polygon: list[list[float]]) -> str:
    points = " L".join(f"{x:.2f},{y:.2f}" for x, y in polygon)
    return f"M{points} Z"


def _breadcrumb(lookup: dict[str, dict], node_id: str) -> str:
    ids = ancestors_of(lookup, node_id)
    return " › ".join(lookup[i]["name"] for i in ids)


def _leaf_records(tree_root: dict, lookup: dict[str, dict]) -> list[dict]:
    root_value = lookup[tree_root["id"]]["value"]
    records = []
    for node_id, n in lookup.items():
        if n["children_ids"]:
            continue
        parent_id = n["parent_id"]
        parent_value = lookup[parent_id]["value"] if parent_id else n["value"]
        layout = label_layout(n["polygon"], n["centroid"], n["area"], n["name"])
        records.append(
            {
                "id": n["id"],
                "name": n["name"],
                "color": n["color"],
                "value": n["value"],
                "description": n["description"],
                "d": _polygon_path_d(n["polygon"]),
                "centroid": n["centroid"],
                "area": n["area"],
                "parentId": parent_id,
                "breadcrumb": _breadcrumb(lookup, node_id),
                "pctParent": (n["value"] / parent_value * 100) if parent_value else 100.0,
                "pctTotal": (n["value"] / root_value * 100) if root_value else 100.0,
                "labelFontSize": layout["font_size"] if layout else None,
            }
        )
    return records


_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<script src="{d3_cdn}"></script>
<style>
  html, body {{ margin: 0; padding: 0; height: 100%; font-family: "Helvetica Neue", Arial, sans-serif; }}
  body {{ min-height: 100vh; display: flex; align-items: center; justify-content: center; }}
  #chart-container {{ width: 100%; max-width: {width}px; }}
  svg {{ width: 100%; height: auto; display: block; }}
  .cell {{
    stroke: #FFFFFF;
    stroke-width: 1.5;
    stroke-linejoin: round;
    cursor: pointer;
    transition: opacity 150ms ease, stroke-width 150ms ease;
  }}
  .cell.dimmed {{ opacity: 0.35; }}
  #hover-highlight {{
    fill: none;
    stroke: #222222;
    stroke-width: 3;
    stroke-linejoin: round;
    pointer-events: none;
    display: none;
  }}
  .cell-label {{
    font-family: "Helvetica Neue", Arial, sans-serif;
    text-anchor: middle;
    dominant-baseline: middle;
    pointer-events: none;
    transition: opacity 150ms ease;
  }}
  #tooltip {{
    position: fixed;
    pointer-events: none;
    background: rgba(20, 20, 20, 0.92);
    color: #FAFAFA;
    padding: 8px 11px;
    border-radius: 6px;
    font-size: 13px;
    line-height: 1.45;
    max-width: 260px;
    opacity: 0;
    transition: opacity 120ms ease;
    z-index: 10;
  }}
  #tooltip .tt-name {{ font-weight: 600; font-size: 14px; }}
  #tooltip .tt-path {{ opacity: 0.75; font-size: 11.5px; margin-bottom: 3px; }}
</style>
</head>
<body>
<div id="chart-container">
  <svg viewBox="{min_x:g} {min_y:g} {width:g} {height:g}">
    <defs></defs>
    <g id="voronoi-treemap"></g>
  </svg>
</div>
<div id="tooltip"></div>
<script>
const CELLS = {cells_json};

const svg = d3.select("svg g#voronoi-treemap");
const tooltip = d3.select("#tooltip");

const cellSel = svg.selectAll("path.cell")
  .data(CELLS, d => d.id)
  .enter()
  .append("path")
  .attr("class", "cell")
  .attr("id", d => "cell-" + d.id)
  .attr("d", d => d.d)
  .attr("fill", d => d.color);

const labeled = CELLS.filter(d => d.labelFontSize !== null);

d3.select("svg defs").selectAll("clipPath")
  .data(labeled, d => d.id)
  .enter()
  .append("clipPath")
  .attr("id", d => "clip-" + d.id)
  .append("path")
  .attr("d", d => d.d);

const labelSel = svg.selectAll("text.cell-label")
  .data(labeled)
  .enter()
  .append("text")
  .attr("class", "cell-label")
  .attr("x", d => d.centroid[0])
  .attr("y", d => d.centroid[1])
  .attr("font-size", d => d.labelFontSize)
  .attr("fill", d => textColorFor(d.color))
  .attr("clip-path", d => "url(#clip-" + d.id + ")")
  .text(d => d.name);

const hoverHighlight = svg.append("path").attr("id", "hover-highlight");

function textColorFor(hex) {{
  hex = hex.replace("#", "");
  const r = parseInt(hex.substring(0, 2), 16);
  const g = parseInt(hex.substring(2, 4), 16);
  const b = parseInt(hex.substring(4, 6), 16);
  const luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
  return luminance > 0.6 ? "#111111" : "#FAFAFA";
}}

function fmtValue(v) {{
  return (Math.round(v * 1000) / 1000).toString();
}}

cellSel
  .on("mouseenter", function (event, d) {{
    cellSel.classed("dimmed", o => o.parentId !== d.parentId);
    d3.select(this).classed("dimmed", false);
    hoverHighlight.attr("d", d.d).style("display", "inline");

    tooltip.html(
      '<div class="tt-path">' + d.breadcrumb + '</div>' +
      '<div class="tt-name">' + d.name + '</div>' +
      '<div>' + fmtValue(d.value) + ' {unit}</div>' +
      '<div>' + d.pctParent.toFixed(1) + '% of parent &middot; ' + d.pctTotal.toFixed(2) + '% of total</div>'
    ).style("opacity", 1);
  }})
  .on("mousemove", function (event) {{
    tooltip
      .style("left", (event.clientX + 16) + "px")
      .style("top", (event.clientY + 16) + "px");
  }})
  .on("mouseleave", function () {{
    cellSel.classed("dimmed", false);
    hoverHighlight.style("display", "none");
    tooltip.style("opacity", 0);
  }});
</script>
</body>
</html>
"""


def render_html(
    tree_root: dict,
    engine_nodes: list[dict],
    viewbox: tuple[float, float, float, float],
    title: str = "Voronoi Treemap",
    unit: str = "",
) -> str:
    """`viewbox` is (min_x, min_y, width, height); see render_svg's docstring
    in svg_export.py for why this isn't just the nominal canvas size."""
    lookup = merge_tree_and_geometry(tree_root, engine_nodes)
    cells = _leaf_records(tree_root, lookup)
    min_x, min_y, width, height = viewbox

    return _TEMPLATE.format(
        title=title,
        d3_cdn=_D3_CDN,
        min_x=min_x,
        min_y=min_y,
        width=width,
        height=height,
        cells_json=json.dumps(cells),
        unit=unit,
    )
