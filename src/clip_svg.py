"""Extracts a clip polygon from an SVG file's <path>/<polygon>/<polyline>
element, for use as an arbitrary bounding shape (`--shape path/to/mask.svg`).

Path parsing supports M/L/H/V/C/S/Q/T/A/Z (both absolute and relative);
curves and arcs are flattened into line segments. Element + ancestor
`transform` attributes (translate/scale/rotate/matrix) are applied. If a
path has multiple subpaths, the one with the largest area is used as the
silhouette -- and it must be closed (explicit Z), or extract_polygon raises
ValueError; a <polyline> is always rejected as open by definition. The
resulting polygon is rescaled (aspect-preserving) to fit the target canvas
with a small margin.

The underlying voronoi-treemap engine only supports convex clip polygons;
a concave shape is not rejected, but prints a warning to stderr, since its
concave regions (notches, waists) will be ignored/distorted by the engine.
"""

from __future__ import annotations

import math
import re
import sys
import xml.etree.ElementTree as ET

_SVG_NS = "{http://www.w3.org/2000/svg}"
_CURVE_STEPS = 20
_ARC_STEPS = 24

_TOKEN_RE = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?")


# ---------- affine transform helpers: (a, b, c, d, e, f) applied as
# x' = a*x + c*y + e ; y' = b*x + d*y + f ----------
IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _mat_mult(m1, m2):
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    )


def _apply(m, x, y):
    a, b, c, d, e, f = m
    return (a * x + c * y + e, b * x + d * y + f)


def _parse_transform(transform_str: str):
    m = IDENTITY
    if not transform_str:
        return m
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", transform_str):
        nums = [float(v) for v in re.findall(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?", args)]
        if name == "translate":
            tx = nums[0]
            ty = nums[1] if len(nums) > 1 else 0.0
            m = _mat_mult(m, (1, 0, 0, 1, tx, ty))
        elif name == "scale":
            sx = nums[0]
            sy = nums[1] if len(nums) > 1 else sx
            m = _mat_mult(m, (sx, 0, 0, sy, 0, 0))
        elif name == "rotate":
            deg = nums[0]
            rad = math.radians(deg)
            cos_r, sin_r = math.cos(rad), math.sin(rad)
            rot = (cos_r, sin_r, -sin_r, cos_r, 0, 0)
            if len(nums) >= 3:
                cx, cy = nums[1], nums[2]
                m = _mat_mult(m, (1, 0, 0, 1, cx, cy))
                m = _mat_mult(m, rot)
                m = _mat_mult(m, (1, 0, 0, 1, -cx, -cy))
            else:
                m = _mat_mult(m, rot)
        elif name == "matrix":
            m = _mat_mult(m, tuple(nums[:6]))
    return m


# ---------- curve flattening ----------
def _cubic_bezier_points(p0, p1, p2, p3, steps=_CURVE_STEPS):
    pts = []
    for i in range(1, steps + 1):
        t = i / steps
        mt = 1 - t
        x = mt**3 * p0[0] + 3 * mt**2 * t * p1[0] + 3 * mt * t**2 * p2[0] + t**3 * p3[0]
        y = mt**3 * p0[1] + 3 * mt**2 * t * p1[1] + 3 * mt * t**2 * p2[1] + t**3 * p3[1]
        pts.append((x, y))
    return pts


def _quadratic_bezier_points(p0, p1, p2, steps=_CURVE_STEPS):
    pts = []
    for i in range(1, steps + 1):
        t = i / steps
        mt = 1 - t
        x = mt**2 * p0[0] + 2 * mt * t * p1[0] + t**2 * p2[0]
        y = mt**2 * p0[1] + 2 * mt * t * p1[1] + t**2 * p2[1]
        pts.append((x, y))
    return pts


def _arc_points(p0, rx, ry, x_axis_rot_deg, large_arc, sweep, p1, steps=_ARC_STEPS):
    if rx == 0 or ry == 0:
        return [p1]
    phi = math.radians(x_axis_rot_deg)
    cos_phi, sin_phi = math.cos(phi), math.sin(phi)

    dx2 = (p0[0] - p1[0]) / 2
    dy2 = (p0[1] - p1[1]) / 2
    x1p = cos_phi * dx2 + sin_phi * dy2
    y1p = -sin_phi * dx2 + cos_phi * dy2

    rx, ry = abs(rx), abs(ry)
    lam = (x1p**2) / (rx**2) + (y1p**2) / (ry**2)
    if lam > 1:
        scale = math.sqrt(lam)
        rx *= scale
        ry *= scale

    sign = -1 if large_arc == sweep else 1
    num = rx**2 * ry**2 - rx**2 * y1p**2 - ry**2 * x1p**2
    den = rx**2 * y1p**2 + ry**2 * x1p**2
    co = sign * math.sqrt(max(num / den, 0)) if den != 0 else 0
    cxp = co * (rx * y1p / ry)
    cyp = co * -(ry * x1p / rx)

    cx = cos_phi * cxp - sin_phi * cyp + (p0[0] + p1[0]) / 2
    cy = sin_phi * cxp + cos_phi * cyp + (p0[1] + p1[1]) / 2

    def angle(ux, uy, vx, vy):
        dot = ux * vx + uy * vy
        length = math.sqrt((ux**2 + uy**2) * (vx**2 + vy**2))
        ang = math.acos(max(-1, min(1, dot / length))) if length else 0
        return ang if (ux * vy - uy * vx) >= 0 else -ang

    theta1 = angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dtheta = angle((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and dtheta > 0:
        dtheta -= 2 * math.pi
    elif sweep and dtheta < 0:
        dtheta += 2 * math.pi

    pts = []
    for i in range(1, steps + 1):
        t = theta1 + dtheta * i / steps
        x = cx + rx * math.cos(t) * cos_phi - ry * math.sin(t) * sin_phi
        y = cy + rx * math.cos(t) * sin_phi + ry * math.sin(t) * cos_phi
        pts.append((x, y))
    return pts


# ---------- path `d` parsing ----------
def parse_path_d(d: str) -> list[tuple[list[tuple[float, float]], bool]]:
    """Returns a list of (subpath points, is_closed) pairs.

    A subpath counts as closed only if it ends with an explicit Z/z
    command -- matching SVG semantics, where an omitted Z leaves the
    path open even if it geometrically ends back at its start point.
    """
    tokens = _TOKEN_RE.findall(d)
    i = 0
    cmd = None
    cur = (0.0, 0.0)
    start = (0.0, 0.0)
    prev_ctrl = None  # for S/T reflection
    subpaths: list[tuple[list[tuple[float, float]], bool]] = []
    cur_sub: list[tuple[float, float]] = []
    cur_closed = False

    def next_num():
        nonlocal i
        v = float(tokens[i])
        i += 1
        return v

    while i < len(tokens):
        tok = tokens[i]
        if re.match(r"[A-Za-z]", tok):
            cmd = tok
            i += 1
        # else: reuse previous cmd (implicit repetition)

        is_rel = cmd.islower()
        c = cmd.upper()

        if c == "M":
            x, y = next_num(), next_num()
            if is_rel:
                x, y = cur[0] + x, cur[1] + y
            if cur_sub:
                subpaths.append((cur_sub, cur_closed))
            cur_sub = [(x, y)]
            cur_closed = False
            cur = start = (x, y)
            cmd = "l" if is_rel else "L"  # subsequent coord pairs are implicit lineto
        elif c == "L":
            x, y = next_num(), next_num()
            if is_rel:
                x, y = cur[0] + x, cur[1] + y
            cur_sub.append((x, y))
            cur = (x, y)
        elif c == "H":
            x = next_num()
            if is_rel:
                x = cur[0] + x
            cur = (x, cur[1])
            cur_sub.append(cur)
        elif c == "V":
            y = next_num()
            if is_rel:
                y = cur[1] + y
            cur = (cur[0], y)
            cur_sub.append(cur)
        elif c == "C":
            x1, y1, x2, y2, x, y = (next_num() for _ in range(6))
            if is_rel:
                x1, y1 = cur[0] + x1, cur[1] + y1
                x2, y2 = cur[0] + x2, cur[1] + y2
                x, y = cur[0] + x, cur[1] + y
            cur_sub.extend(_cubic_bezier_points(cur, (x1, y1), (x2, y2), (x, y)))
            prev_ctrl = (x2, y2)
            cur = (x, y)
        elif c == "S":
            x2, y2, x, y = (next_num() for _ in range(4))
            if is_rel:
                x2, y2 = cur[0] + x2, cur[1] + y2
                x, y = cur[0] + x, cur[1] + y
            if prev_ctrl:
                x1, y1 = 2 * cur[0] - prev_ctrl[0], 2 * cur[1] - prev_ctrl[1]
            else:
                x1, y1 = cur
            cur_sub.extend(_cubic_bezier_points(cur, (x1, y1), (x2, y2), (x, y)))
            prev_ctrl = (x2, y2)
            cur = (x, y)
        elif c == "Q":
            x1, y1, x, y = (next_num() for _ in range(4))
            if is_rel:
                x1, y1 = cur[0] + x1, cur[1] + y1
                x, y = cur[0] + x, cur[1] + y
            cur_sub.extend(_quadratic_bezier_points(cur, (x1, y1), (x, y)))
            prev_ctrl = (x1, y1)
            cur = (x, y)
        elif c == "T":
            x, y = next_num(), next_num()
            if is_rel:
                x, y = cur[0] + x, cur[1] + y
            if prev_ctrl:
                x1, y1 = 2 * cur[0] - prev_ctrl[0], 2 * cur[1] - prev_ctrl[1]
            else:
                x1, y1 = cur
            cur_sub.extend(_quadratic_bezier_points(cur, (x1, y1), (x, y)))
            prev_ctrl = (x1, y1)
            cur = (x, y)
        elif c == "A":
            rx, ry, rot, large_arc, sweep, x, y = (next_num() for _ in range(7))
            if is_rel:
                x, y = cur[0] + x, cur[1] + y
            cur_sub.extend(_arc_points(cur, rx, ry, rot, bool(large_arc), bool(sweep), (x, y)))
            cur = (x, y)
        elif c == "Z":
            cur_sub.append(start)
            cur = start
            cur_closed = True
        else:
            raise ValueError(f"Unsupported SVG path command: {cmd}")

        if c not in ("S", "Q", "T", "C"):
            prev_ctrl = None

    if cur_sub:
        subpaths.append((cur_sub, cur_closed))
    return subpaths


def _polygon_area(points):
    area = 0.0
    n = len(points)
    for i in range(n):
        x0, y0 = points[i]
        x1, y1 = points[(i + 1) % n]
        area += x0 * y1 - x1 * y0
    return abs(area) / 2


def _find_element(root, fragment_id: str | None):
    candidates = []
    for tag in ("path", "polygon", "polyline"):
        candidates.extend(root.iter(f"{_SVG_NS}{tag}"))
        candidates.extend(root.iter(tag))  # tolerate files without namespace
    if fragment_id:
        for el in candidates:
            if el.get("id") == fragment_id:
                return el
        raise ValueError(f"No <path>/<polygon>/<polyline> with id='{fragment_id}' found")
    if not candidates:
        raise ValueError("No <path>/<polygon>/<polyline> element found in SVG")
    return candidates[0]


def _accumulated_transform(root, target):
    parent_map = {c: p for p in root.iter() for c in p}
    chain = []
    el = target
    while el is not None:
        chain.append(el.get("transform", ""))
        el = parent_map.get(el)
    m = IDENTITY
    for t in reversed(chain):  # root-to-leaf order
        m = _mat_mult(m, _parse_transform(t))
    return m


def _points_attr(points_str: str) -> list[tuple[float, float]]:
    nums = [float(v) for v in re.findall(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?", points_str)]
    return [(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]


def _is_convex(points: list[tuple[float, float]]) -> bool:
    n = len(points)
    if n < 4:
        return True
    signs = set()
    for i in range(n):
        ox, oy = points[i]
        ax, ay = points[(i + 1) % n]
        bx, by = points[(i + 2) % n]
        cross = (ax - ox) * (by - ay) - (ay - oy) * (bx - ax)
        if cross > 0:
            signs.add(1)
        elif cross < 0:
            signs.add(-1)
    return len(signs) <= 1


def _rescale_to_canvas(points, width, height, padding_ratio=0.05):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    src_w = max(max_x - min_x, 1e-9)
    src_h = max(max_y - min_y, 1e-9)

    avail_w = width * (1 - 2 * padding_ratio)
    avail_h = height * (1 - 2 * padding_ratio)
    scale = min(avail_w / src_w, avail_h / src_h)

    scaled_w = src_w * scale
    scaled_h = src_h * scale
    offset_x = (width - scaled_w) / 2
    offset_y = (height - scaled_h) / 2

    return [
        [offset_x + (x - min_x) * scale, offset_y + (y - min_y) * scale]
        for x, y in points
    ]


def extract_polygon(svg_path: str, width: float, height: float) -> list[list[float]]:
    """Parses `path[#fragment_id]`, extracts the target shape, and returns a
    polygon (list of [x, y]) rescaled to fit the given canvas.

    Raises ValueError if the selected shape is not closed: a <path> whose
    largest subpath lacks an explicit Z, or a <polyline> (which is open by
    definition). <polygon> elements are always closed.
    """
    path_part, _, fragment_id = svg_path.partition("#")
    tree = ET.parse(path_part)
    root = tree.getroot()

    el = _find_element(root, fragment_id or None)
    transform = _accumulated_transform(root, el)

    tag = el.tag.split("}")[-1]
    if tag == "path":
        subpaths = parse_path_d(el.get("d", ""))
        if not subpaths:
            raise ValueError(f"Path element has no drawable geometry: {svg_path}")
        points, closed = max(subpaths, key=lambda sp: _polygon_area(sp[0]))
        if not closed:
            raise ValueError(
                f"Shape in {svg_path!r} is not closed (missing 'Z' in its <path> d attribute) "
                "-- a clip shape must be a closed outline."
            )
        polygon = points
    elif tag == "polygon":
        polygon = _points_attr(el.get("points", ""))
        if len(polygon) < 3:
            raise ValueError(f"polygon element has fewer than 3 points: {svg_path}")
    elif tag == "polyline":
        raise ValueError(
            f"Shape in {svg_path!r} is a <polyline>, which is open by definition "
            "-- use a <polygon> or a closed <path> (ending in 'Z') instead."
        )
    else:
        raise ValueError(f"Unsupported SVG element <{tag}>: {svg_path}")

    transformed = [_apply(transform, x, y) for x, y in polygon]

    if not _is_convex(transformed):
        print(
            f"warning: shape in {svg_path!r} is concave -- the underlying voronoi-treemap "
            "engine only supports convex clip polygons, so concave regions (notches, waists) "
            "will be ignored/distorted in the output.",
            file=sys.stderr,
        )

    return _rescale_to_canvas(transformed, width, height)
