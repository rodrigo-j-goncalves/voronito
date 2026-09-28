"""Colorblind-safe default color assignment.

Top-level branches (depth 1, i.e. direct children of the root) get a color
from the Okabe-Ito palette -- the standard colorblind-safe qualitative
palette (Okabe & Ito, 2008). Descendants of a branch inherit that branch's
hue/saturation and vary only in lightness ("shades of" the parent color),
so a subtree reads as visually related at a glance. An explicit `color`
value from the CSV always wins and becomes the new base for its own subtree.
"""

from __future__ import annotations

import colorsys
from itertools import cycle

# Okabe & Ito (2008), black excluded (reserved for text/strokes, not data fill).
OKABE_ITO = [
    "#E69F00",  # orange
    "#56B4E9",  # sky blue
    "#009E73",  # bluish green
    "#F0E442",  # yellow
    "#0072B2",  # blue
    "#D55E00",  # vermillion
    "#CC79A7",  # reddish purple
]

_ROOT_HSL = (0.0, 0.0, 0.95)  # neutral near-white; root polygon is not filled by default
_MIN_LIGHTNESS = 0.20
_MAX_LIGHTNESS = 0.82


def hex_to_hsl(hex_color: str) -> tuple[float, float, float]:
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return (h, s, l)


def hsl_to_hex(h: float, s: float, l: float) -> str:
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return "#{:02X}{:02X}{:02X}".format(round(r * 255), round(g * 255), round(b * 255))


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def assign_colors(root: dict) -> None:
    """Mutates the tree in place, adding a resolved `color` (hex) to every node."""
    palette_iter = cycle(OKABE_ITO)
    _assign(root, depth=0, parent_hsl=None, sibling_index=0, sibling_count=1, palette_iter=palette_iter)


def _assign(node, depth, parent_hsl, sibling_index, sibling_count, palette_iter):
    explicit = node.get("color")
    if explicit:
        base_hsl = hex_to_hsl(explicit)
    elif depth == 0:
        base_hsl = _ROOT_HSL
    elif depth == 1:
        base_hsl = hex_to_hsl(next(palette_iter))
    else:
        h, s, l = parent_hsl
        spread = max(0.28 - 0.06 * depth, 0.08)
        frac = (sibling_index / (sibling_count - 1) - 0.5) if sibling_count > 1 else 0.0
        new_l = _clamp(l + frac * 2 * spread, _MIN_LIGHTNESS, _MAX_LIGHTNESS)
        base_hsl = (h, s, new_l)

    node["color"] = hsl_to_hex(*base_hsl)

    children = node.get("children") or []
    n = len(children)
    for i, child in enumerate(children):
        _assign(child, depth + 1, base_hsl, i, n, palette_iter)
