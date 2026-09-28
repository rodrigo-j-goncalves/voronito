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


def ancestors_of(lookup: dict[str, dict], node_id: str) -> list[str]:
    """Root-first list of ancestor ids, including node_id itself."""
    chain = []
    cur = node_id
    while cur is not None:
        chain.append(cur)
        cur = lookup[cur]["parent_id"]
    return list(reversed(chain))
