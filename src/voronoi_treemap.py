#!/usr/bin/env python3
"""CLI entry point for the voronoi-treemap pipeline.

Example:
  python voronoi_treemap.py \\
    --input data/biomass.csv \\
    --output-svg output/biomass.svg \\
    --output-html output/biomass.html \\
    --shape pentagon

  # or an arbitrary clip polygon extracted from a closed SVG silhouette:
  python voronoi_treemap.py --input data/biomass.csv --output-svg output/biomass.svg \\
    --shape masks/leaf.svg#outline

  # or generate every built-in shape in one go (output/biomass_circle.svg, _rectangle.svg, ...):
  python voronoi_treemap.py --input data/biomass.csv --output-svg output/biomass.svg --all-shapes
"""

from __future__ import annotations

import argparse
from pathlib import Path

from hierarchy import read_csv, build_tree
from colors import assign_colors
from engine import run_engine
from svg_export import render_svg
from html_export import render_html
from clip_svg import extract_polygon
from geometry import bounding_box

_NAMED_REGULAR_POLYGONS = {"triangle": 3, "pentagon": 5, "hexagon": 6}
_ALL_SHAPES = ("circle", "rectangle", "square", "ellipse", *_NAMED_REGULAR_POLYGONS)


def _is_svg_shape(value: str) -> bool:
    return value.split("#", 1)[0].lower().endswith(".svg")


def _build_shape(shape_value: str, width: float, height: float) -> dict:
    if _is_svg_shape(shape_value):
        points = extract_polygon(shape_value, width, height)
        return {"type": "polygon", "points": points}

    if shape_value in _NAMED_REGULAR_POLYGONS:
        return {"type": "polygon", "sides": _NAMED_REGULAR_POLYGONS[shape_value]}

    if shape_value.startswith("polygon:"):
        raw_sides = shape_value.split(":", 1)[1]
        try:
            sides = int(raw_sides)
        except ValueError:
            raise SystemExit(f"--shape 'polygon:N' requires an integer N (got: {shape_value!r})")
        if sides < 3:
            raise SystemExit(f"--shape 'polygon:N' requires N >= 3 (got: {sides})")
        return {"type": "polygon", "sides": sides}

    if shape_value in ("circle", "rectangle", "ellipse"):
        return {"type": shape_value}

    if shape_value == "square":
        side = min(width, height)
        return {"type": "rectangle", "width": side, "height": side}

    raise SystemExit(
        f"--shape must be one of {', '.join(_ALL_SHAPES)}, 'polygon:N', or a path to an "
        f".svg file (got: {shape_value!r})"
    )


def _suffixed_path(path_str: str, suffix: str) -> str:
    p = Path(path_str)
    return str(p.with_name(f"{p.stem}_{suffix}{p.suffix}"))


def _generate(root, shape_value, width, height, seed, output_svg, output_html, title, unit):
    shape = _build_shape(shape_value, width, height)
    result = run_engine(root, shape=shape, options={"width": width, "height": height, "seed": seed})

    root_node = next(n for n in result["nodes"] if n["id"] == root["id"])
    viewbox = bounding_box(root_node["polygon"])

    if output_svg:
        svg = render_svg(root, result["nodes"], viewbox, unit=unit)
        out_path = Path(output_svg)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(svg, encoding="utf-8")
        print(f"Wrote {out_path} ({len(result['nodes'])} nodes)")

    if output_html:
        html = render_html(root, result["nodes"], viewbox, title=title, unit=unit)
        out_path = Path(output_html)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html, encoding="utf-8")
        print(f"Wrote {out_path} ({len(result['nodes'])} nodes)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a voronoi treemap from a hierarchical CSV.")
    parser.add_argument("--input", required=True, help="Path to input CSV")
    parser.add_argument("--output-svg", help="Path to write the SVG output")
    parser.add_argument("--output-html", help="Path to write the interactive HTML output")

    parser.add_argument(
        "--shape",
        default="circle",
        help=(
            "Bounding shape: 'circle', 'rectangle', 'square', 'ellipse', 'triangle', "
            "'pentagon', 'hexagon', 'polygon:N' (regular N-gon), or a path to an .svg "
            "file (optionally 'path.svg#elementId') to clip to an arbitrary closed polygon"
        ),
    )
    parser.add_argument(
        "--all-shapes",
        action="store_true",
        help=(
            f"Generate one output per built-in shape ({', '.join(_ALL_SHAPES)}), each "
            "suffixed '_<shape>' before the extension, instead of a single --shape"
        ),
    )

    parser.add_argument("--width", type=float, default=800)
    parser.add_argument("--height", type=float, default=800)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--title", default="Voronoi Treemap", help="Title for the HTML output")
    parser.add_argument("--unit", default="", help="Unit label appended to values in tooltips (e.g. 'Gt C', 'USD')")
    args = parser.parse_args()

    if not args.output_svg and not args.output_html:
        parser.error("at least one of --output-svg or --output-html is required")

    df = read_csv(args.input)
    root = build_tree(df)
    assign_colors(root)

    if args.all_shapes:
        for shape_name in _ALL_SHAPES:
            svg_out = _suffixed_path(args.output_svg, shape_name) if args.output_svg else None
            html_out = _suffixed_path(args.output_html, shape_name) if args.output_html else None
            _generate(root, shape_name, args.width, args.height, args.seed, svg_out, html_out, args.title, args.unit)
    else:
        _generate(root, args.shape, args.width, args.height, args.seed, args.output_svg, args.output_html, args.title, args.unit)


if __name__ == "__main__":
    main()
