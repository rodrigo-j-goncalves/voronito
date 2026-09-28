"""CSV -> nested hierarchy tree, with ID slug generation.

ID rule:
  - if the CSV `id` column is non-empty for a row, use it verbatim.
  - otherwise, derive it from `name`: transliterate to ASCII (strip accents/
    diacritics), drop any remaining non-alphanumeric characters (including
    spaces), and on collision with an already-used id, append a numeric
    suffix starting at 2 (e.g. "Mammals", "Mammals2").
"""

from __future__ import annotations

import unicodedata
import re
from pathlib import Path

import pandas as pd

_NON_ALNUM_RE = re.compile(r"[^A-Za-z0-9]+")


def slugify(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return _NON_ALNUM_RE.sub("", ascii_name)


def make_unique_id(name: str, used_ids: set[str]) -> str:
    base = slugify(name) or "node"
    if base not in used_ids:
        used_ids.add(base)
        return base
    suffix = 2
    while f"{base}{suffix}" in used_ids:
        suffix += 1
    candidate = f"{base}{suffix}"
    used_ids.add(candidate)
    return candidate


def read_csv(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str).fillna("")
    required = {"id", "parent_id", "name", "value", "color", "description"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV is missing required columns: {sorted(missing)}")
    return df


def build_tree(df: pd.DataFrame) -> dict:
    """Resolve ids and assemble the nested hierarchy dict.

    Returns the root node dict: {id, name, value, color, description, children: [...]}.
    Only leaf nodes carry a numeric `value`; internal node values are left
    as None and are summed bottom-up later by the compute engine.
    """
    used_ids: set[str] = set()
    resolved_ids: list[str] = []

    # First pass: resolve ids in CSV row order (explicit id wins, else derive from name).
    for _, row in df.iterrows():
        explicit_id = row["id"].strip()
        if explicit_id:
            if explicit_id in used_ids:
                raise ValueError(f"Duplicate explicit id in CSV: '{explicit_id}'")
            used_ids.add(explicit_id)
            resolved_ids.append(explicit_id)
        else:
            resolved_ids.append(make_unique_id(row["name"].strip(), used_ids))

    nodes: dict[str, dict] = {}
    parent_of: dict[str, str | None] = {}
    order: list[str] = []

    for (_, row), node_id in zip(df.iterrows(), resolved_ids):
        value_str = row["value"].strip()
        value = float(value_str) if value_str else None
        color = row["color"].strip() or None
        description = row["description"].strip() or None
        parent_id = row["parent_id"].strip() or None

        nodes[node_id] = {
            "id": node_id,
            "name": row["name"].strip(),
            "value": value,
            "color": color,
            "description": description,
            "children": [],
        }
        parent_of[node_id] = parent_id
        order.append(node_id)

    roots = [nid for nid in order if parent_of[nid] is None]
    if len(roots) != 1:
        raise ValueError(f"Expected exactly one root row (empty parent_id), found {len(roots)}: {roots}")
    root_id = roots[0]

    for nid in order:
        parent_id = parent_of[nid]
        if parent_id is None:
            continue
        if parent_id not in nodes:
            raise ValueError(f"Row '{nid}' references unknown parent_id '{parent_id}'")
        nodes[parent_id]["children"].append(nodes[nid])

    _check_no_cycles(root_id, nodes, parent_of)

    root = nodes[root_id]
    _validate_leaf_values(root)
    return root


def _check_no_cycles(root_id: str, nodes: dict, parent_of: dict) -> None:
    for nid in nodes:
        seen = set()
        cur = nid
        while cur is not None:
            if cur in seen:
                raise ValueError(f"Cycle detected in hierarchy involving '{cur}'")
            seen.add(cur)
            cur = parent_of.get(cur)


def _validate_leaf_values(node: dict, path: str = "") -> None:
    label = f"{path}/{node['name']}" if path else node["name"]
    if not node["children"]:
        if node["value"] is None or node["value"] <= 0:
            raise ValueError(f"Leaf node '{label}' (id={node['id']}) must have a numeric value > 0")
    else:
        for child in node["children"]:
            _validate_leaf_values(child, label)
