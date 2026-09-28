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

from geometry import merge_tree_and_geometry, label_layout


def _text_color_for(hex_color: str) -> str:
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0
    return "#111111" if luminance > 0.6 else "#FAFAFA"


def _polygon_path_d(polygon: list[list[float]]) -> str:
    points = " L".join(f"{x:.2f},{y:.2f}" for x, y in polygon)
    return f"M{points} Z"


def _render_node(node_id: str, lookup: dict[str, dict], indent: str, unit: str, clip_defs: list[str]) -> str:
    n = lookup[node_id]
    if not n["children_ids"]:
        return _render_leaf(n, indent, unit, clip_defs)

    parts = [f'{indent}<g id="group-{n["id"]}">']
    for child_id in n["children_ids"]:
        parts.append(_render_node(child_id, lookup, indent + "  ", unit, clip_defs))
    parts.append(f"{indent}</g>")
    return "\n".join(parts)


def _render_leaf(n: dict, indent: str, unit: str, clip_defs: list[str]) -> str:
    d = _polygon_path_d(n["polygon"])
    parts = [f'{indent}<path id="cell-{n["id"]}" class="cell" d="{d}" fill="{n["color"]}">']
    value_str = f'{n["value"]:g}' + (f" {unit}" if unit else "")
    title = escape(f'{n["name"]}: {value_str}')
    parts.append(f"{indent}  <title>{title}</title>")
    parts.append(f"{indent}</path>")

    layout = label_layout(n["polygon"], n["centroid"], n["area"], n["name"])
    if layout:
        cx, cy = n["centroid"]
        text_color = _text_color_for(n["color"])
        label = escape(n["name"])
        clip_id = f'clip-{n["id"]}'
        clip_defs.append(f'    <clipPath id="{clip_id}"><path d="{d}"/></clipPath>')
        parts.append(
            f'{indent}<text class="cell-label" x="{cx:.2f}" y="{cy:.2f}" '
            f'font-size="{layout["font_size"]:.1f}" fill="{text_color}" clip-path="url(#{clip_id})">{label}</text>'
        )

    return "\n".join(parts)


def render_svg(tree_root: dict, engine_nodes: list[dict], width: float, height: float, unit: str = "") -> str:
    lookup = merge_tree_and_geometry(tree_root, engine_nodes)
    root_id = tree_root["id"]

    clip_defs: list[str] = []
    body = _render_node(root_id, lookup, indent="      ", unit=unit, clip_defs=clip_defs)
    clip_defs_str = "\n".join(clip_defs)

    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:g} {height:g}" width="{width:g}" height="{height:g}">
  <defs>
    <style>
      .cell {{ stroke: #FFFFFF; stroke-width: 1.5; stroke-linejoin: round; }}
      .cell-label {{ font-family: "Helvetica Neue", Arial, sans-serif; text-anchor: middle; dominant-baseline: middle; }}
    </style>
{clip_defs_str}
  </defs>
  <g id="voronoi-treemap">
{body}
  </g>
</svg>
"""
    return svg
