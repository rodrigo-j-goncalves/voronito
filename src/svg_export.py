"""Renders a clean, Inkscape/progresSVG-friendly SVG from computed treemap geometry.

Structure:
  <svg>
    <g id="voronoi-treemap">
      <g id="group-<id>">           (one per internal/branch node, nested)
        <path id="cell-<id>" .../>  (one per leaf node)
        <text>...</text>            (leaf label, omitted if the cell is too small)
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from geometry import merge_tree_and_geometry

_MIN_LABEL_AREA = 200.0
_FONT_SIZE_K = 0.35
_FONT_SIZE_MIN = 7.0
_FONT_SIZE_MAX = 20.0


def _text_color_for(hex_color: str) -> str:
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0
    return "#111111" if luminance > 0.6 else "#FAFAFA"


def _polygon_path_d(polygon: list[list[float]]) -> str:
    points = " L".join(f"{x:.2f},{y:.2f}" for x, y in polygon)
    return f"M{points} Z"


def _font_size_for(area: float) -> float:
    size = _FONT_SIZE_K * (area**0.5)
    return max(_FONT_SIZE_MIN, min(_FONT_SIZE_MAX, size))


def _render_node(node_id: str, lookup: dict[str, dict], indent: str) -> str:
    n = lookup[node_id]
    if not n["children_ids"]:
        return _render_leaf(n, indent)

    parts = [f'{indent}<g id="group-{n["id"]}">']
    for child_id in n["children_ids"]:
        parts.append(_render_node(child_id, lookup, indent + "  "))
    parts.append(f"{indent}</g>")
    return "\n".join(parts)


def _render_leaf(n: dict, indent: str) -> str:
    d = _polygon_path_d(n["polygon"])
    parts = [f'{indent}<path id="cell-{n["id"]}" class="cell" d="{d}" fill="{n["color"]}">']
    title = escape(f'{n["name"]}: {n["value"]:g} Gt C')
    parts.append(f"{indent}  <title>{title}</title>")
    parts.append(f"{indent}</path>")

    if n["area"] >= _MIN_LABEL_AREA:
        cx, cy = n["centroid"]
        font_size = _font_size_for(n["area"])
        text_color = _text_color_for(n["color"])
        label = escape(n["name"])
        parts.append(
            f'{indent}<text class="cell-label" x="{cx:.2f}" y="{cy:.2f}" '
            f'font-size="{font_size:.1f}" fill="{text_color}">{label}</text>'
        )

    return "\n".join(parts)


def render_svg(tree_root: dict, engine_nodes: list[dict], width: float, height: float) -> str:
    lookup = merge_tree_and_geometry(tree_root, engine_nodes)
    root_id = tree_root["id"]

    body = _render_node(root_id, lookup, indent="      ")

    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:g} {height:g}" width="{width:g}" height="{height:g}">
  <defs>
    <style>
      .cell {{ stroke: #FFFFFF; stroke-width: 1.5; stroke-linejoin: round; }}
      .cell-label {{ font-family: "Helvetica Neue", Arial, sans-serif; text-anchor: middle; dominant-baseline: middle; }}
    </style>
  </defs>
  <g id="voronoi-treemap">
{body}
  </g>
</svg>
"""
    return svg
