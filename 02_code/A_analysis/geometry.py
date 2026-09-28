"""Shared helper: merges the CSV-derived hierarchy tree with the Node engine's
computed geometry (polygon, centroid, area) into a single id-keyed lookup,
used by both the SVG and HTML exporters.
"""

from __future__ import annotations


def merge_tree_and_geometry(tree_root: dict, engine_nodes: list[dict]) -> dict[str, dict]:
    lookup: dict[str, dict] = {}

    def walk(node, parent_id, depth):
        lookup[node["id"]] = {
            "id": node["id"],
            "name": node["name"],
            "value": node["value"],
            "color": node["color"],
            "description": node["description"],
            "parent_id": parent_id,
            "depth": depth,
            "children_ids": [c["id"] for c in node.get("children") or []],
        }
        for child in node.get("children") or []:
            walk(child, node["id"], depth + 1)

    walk(tree_root, None, 0)

    for n in engine_nodes:
        lookup[n["id"]].update(
            {
                "polygon": n["polygon"],
                "centroid": n["centroid"],
                "area": n["area"],
            }
        )
    return lookup


def bounding_box(polygon: list[list[float]], padding_ratio: float = 0.05) -> tuple[float, float, float, float]:
    """Returns (min_x, min_y, width, height) for a polygon, expanded by
    `padding_ratio` of its own size on each side. Used to size the exported
    SVG/HTML viewBox to the actual shape instead of the nominal canvas, so a
    shape that doesn't fill the full canvas (e.g. a golden-ratio rectangle
    on a square canvas) doesn't leave a visibly empty margin.
    """
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    w = max_x - min_x
    h = max_y - min_y
    pad_x = w * padding_ratio
    pad_y = h * padding_ratio
    return (min_x - pad_x, min_y - pad_y, w + 2 * pad_x, h + 2 * pad_y)


def ancestors_of(lookup: dict[str, dict], node_id: str) -> list[str]:
    """Root-first list of ancestor ids, including node_id itself."""
    chain = []
    cur = node_id
    while cur is not None:
        chain.append(cur)
        cur = lookup[cur]["parent_id"]
    return list(reversed(chain))


def _width_at_y(polygon: list[list[float]], y: float) -> float:
    """Horizontal extent of a convex polygon at a given y (scanline).
    Voronoi/power-diagram cells are always convex, so a horizontal line
    crosses the boundary at exactly two points (generically), giving a
    well-defined interior width -- a much tighter fit estimate than the
    polygon's overall bounding box for wedge/elongated cells.
    """
    xs = []
    n = len(polygon)
    for i in range(n):
        x0, y0 = polygon[i]
        x1, y1 = polygon[(i + 1) % n]
        if (y0 <= y < y1) or (y1 <= y < y0):
            t = (y - y0) / (y1 - y0)
            xs.append(x0 + t * (x1 - x0))
    if len(xs) < 2:
        return 0.0
    return max(xs) - min(xs)


def label_layout(
    polygon: list[list[float]],
    centroid: list[float],
    area: float,
    name: str,
    min_area: float = 200.0,
    font_k: float = 0.35,
    font_min: float = 7.0,
    font_max: float = 20.0,
    char_width_ratio: float = 0.58,
) -> dict | None:
    """Decides whether a leaf's label fits its cell, and at what size.

    Area alone is a poor proxy for elongated/wedge-shaped cells (e.g. thin
    circle sectors): a cell can be large enough by area yet too narrow for
    its label. This checks the estimated label width against the cell's
    actual width at the label's row (not just its bounding box) and
    returns None (don't render) if it won't fit.
    """
    if area < min_area or not name:
        return None
    font_size = max(font_min, min(font_max, font_k * (area**0.5)))
    ys = [p[1] for p in polygon]
    bbox_h = max(ys) - min(ys)
    local_w = _width_at_y(polygon, centroid[1])
    est_text_w = char_width_ratio * font_size * len(name)
    if local_w <= 0 or est_text_w > local_w * 0.92 or font_size > bbox_h:
        return None
    return {"font_size": font_size}
