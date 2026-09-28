#!/usr/bin/env python3
"""CLI entry point for the voronoi-treemap pipeline.

Example:
  python voronoi_treemap.py \\
    --input data/biomass.csv \\
    --output-svg output/biomass.svg \\
    --output-html output/biomass.html \\
    --shape circle

  # or an arbitrary clip polygon extracted from an SVG silhouette:
  python voronoi_treemap.py --input data/biomass.csv --output-svg output/biomass.svg \\
    --clip-svg masks/leaf.svg#outline
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


def _build_shape(args) -> dict:
    if args.clip_svg:
        points = extract_polygon(args.clip_svg, args.width, args.height)
        return {"type": "polygon", "points": points}
    return {"type": args.shape}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a voronoi treemap from a hierarchical CSV.")
    parser.add_argument("--input", required=True, help="Path to input CSV")
    parser.add_argument("--output-svg", help="Path to write the SVG output")
    parser.add_argument("--output-html", help="Path to write the interactive HTML output")

    shape_group = parser.add_mutually_exclusive_group()
    shape_group.add_argument("--shape", choices=["circle", "rectangle"], default="circle")
    shape_group.add_argument(
        "--clip-svg",
        metavar="PATH[#elementId]",
        help="Use an arbitrary polygon clip extracted from an SVG path/polygon/polyline element",
    )

    parser.add_argument("--width", type=float, default=800)
    parser.add_argument("--height", type=float, default=800)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--title", default="Voronoi Treemap", help="Title for the HTML output")
    args = parser.parse_args()

    if not args.output_svg and not args.output_html:
        parser.error("at least one of --output-svg or --output-html is required")

    df = read_csv(args.input)
    root = build_tree(df)
    assign_colors(root)

    shape = _build_shape(args)
    result = run_engine(
        root,
        shape=shape,
        options={"width": args.width, "height": args.height, "seed": args.seed},
    )

    if args.output_svg:
        svg = render_svg(root, result["nodes"], args.width, args.height)
        out_path = Path(args.output_svg)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(svg, encoding="utf-8")
        print(f"Wrote {out_path} ({len(result['nodes'])} nodes)")

    if args.output_html:
        html = render_html(root, result["nodes"], args.width, args.height, title=args.title)
        out_path = Path(args.output_html)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html, encoding="utf-8")
        print(f"Wrote {out_path} ({len(result['nodes'])} nodes)")


if __name__ == "__main__":
    main()
