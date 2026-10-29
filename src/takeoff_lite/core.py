"""Takeoff core: surface area per material, opening deductions, quantities and cost.

Everything here is pure geometry/arithmetic so it can be checked against
hand-computed answers. No bpy UI in this module beyond what is needed to read
mesh data.

Design note on opening deduction
--------------------------------
A wall face and a door/window face are both polygons. Splitting a polygon by
another polygon is messy for concave outlines, so both are fan-triangulated
first. A fan triangle of a *convex* face is inside the face, and the
intersection of two triangles is convex, so each wall-triangle / opening-triangle
pair can be clipped exactly with Sutherland-Hodgman in the shared plane. Sum the
clipped areas, clamp at the wall area. Result is exact, not sampled.
"""

import math

EPS = 1.0e-9


# ---------------------------------------------------------------------------
# unit handling
# ---------------------------------------------------------------------------

UNIT_FACTORS = {
    # Display-only unit sizes, used to pick the area label and the sq ft factor.
    "METERS": 1.0,
    "CENTIMETERS": 0.01,
    "MILLIMETERS": 0.001,
    "MICROMETERS": 1.0e-6,
    "KILOMETERS": 1000.0,
    "FEET": 0.3048,
    "INCHES": 0.0254,
    "YARDS": 0.9144,
    "MILES": 1609.344,
}

IMPERIAL_UNITS = {"FEET", "INCHES", "YARDS", "MILES"}

M2_PER_SQFT = 0.09290304


def scene_metres_per_unit(scene):
    """Metres represented by one Blender unit.

    Only `scale_length` changes physical size — its tooltip is literally "Scale of
    the unit (in meters)". `length_unit` is a display preference: switching a
    metric scene to Centimeters makes a 2 m cube read as 200 cm, it does not make
    it 2 cm. Treating length_unit as a size factor double-counts (that bug made a
    cm-authored scene report 1/10000 of its real area).
    """
    us = scene.unit_settings
    scale = us.scale_length or 1.0
    if scale <= 0:
        scale = 1.0
    return scale


def to_display_area(area_m2, length_unit):
    """Convert m^2 to the display unit: m2 for metric, sq ft for imperial."""
    unit = (length_unit or "METERS").upper()
    if unit in IMPERIAL_UNITS:
        return area_m2 / M2_PER_SQFT
    return area_m2


def area_unit_name(length_unit):
    unit = (length_unit or "METERS").upper()
    return "sq ft" if unit in IMPERIAL_UNITS else "m2"


# ---------------------------------------------------------------------------
# small vector helpers (tuples, so this module stays importable without bpy)
# ---------------------------------------------------------------------------

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _len(a):
    return math.sqrt(_dot(a, a))


def _norm(a):
    n = _len(a)
    if n < EPS:
        return (0.0, 0.0, 0.0)
    return (a[0] / n, a[1] / n, a[2] / n)


def triangle_area(p0, p1, p2):
    """Area of a triangle from three points (any winding)."""
    return 0.5 * _len(_cross(_sub(p1, p0), _sub(p2, p0)))


def polygon_area(pts):
    """Area of a planar polygon given in order. Fan triangulation, absolute."""
    if len(pts) < 3:
        return 0.0
    total = 0.0
    a = pts[0]
    for i in range(1, len(pts) - 1):
        total += triangle_area(a, pts[i], pts[i + 1])
    return total


# ---------------------------------------------------------------------------
# 2D clipping (Sutherland-Hodgman, convex clip window)
# ---------------------------------------------------------------------------

def _tri_2d(tri, origin, axis_u, axis_v):
    out = []
    for p in tri:
        d = _sub(p, origin)
        out.append((_dot(d, axis_u), _dot(d, axis_v)))
    return out


def _orient(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _clip_edge(subject, a, b):
    """Keep the part of `subject` left of (or on) the directed line a->b."""
    if not subject:
        return []
    out = []
    n = len(subject)
    for i in range(n):
        cur = subject[i]
        prv = subject[i - 1]
        cur_in = _orient(a, b, cur) >= -EPS
        prv_in = _orient(a, b, prv) >= -EPS
        if cur_in:
            if not prv_in:
                out.append(_intersect(prv, cur, a, b))
            out.append(cur)
        elif prv_in:
            out.append(_intersect(prv, cur, a, b))
    return out


def _intersect(p, q, a, b):
    """Intersection of segment p->q with the infinite line a->b."""
    d1 = _orient(a, b, p)
    d2 = _orient(a, b, q)
    den = d1 - d2
    if abs(den) < EPS:
        return q
    t = d1 / den
    return (p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1]))


def clip_convex(subject, clip):
    """Intersect two convex 2D polygons. `clip` must be in consistent winding."""
    if len(clip) < 3:
        return []
    # normalise winding to counter-clockwise so "left of edge" is inside
    signed = 0.0
    for i in range(len(clip)):
        x1, y1 = clip[i]
        x2, y2 = clip[(i + 1) % len(clip)]
        signed += x1 * y2 - x2 * y1
    ccw = list(clip) if signed > 0 else list(reversed(clip))
    out = list(subject)
    for i in range(len(ccw)):
        a = ccw[i]
        b = ccw[(i + 1) % len(ccw)]
        out = _clip_edge(out, a, b)
        if not out:
            return []
    return out


def poly_2d_area(poly):
    if len(poly) < 3:
        return 0.0
    s = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        s += x1 * y2 - x2 * y1
    return abs(s) * 0.5


def overlap_area_3d(tri_a, tri_b):
    """Area shared by two coplanar triangles. Returns 0.0 when not coplanar."""
    na = _norm(_cross(_sub(tri_a[1], tri_a[0]), _sub(tri_a[2], tri_a[0])))
    if _len(na) < 0.5:
        return 0.0
    nb = _norm(_cross(_sub(tri_b[1], tri_b[0]), _sub(tri_b[2], tri_b[0])))
    if _len(nb) < 0.5:
        return 0.0
    if abs(abs(_dot(na, nb)) - 1.0) > 1e-4:
        return 0.0  # not parallel
    # plane distance of tri_b points from tri_a's plane
    for p in tri_b:
        if abs(_dot(_sub(p, tri_a[0]), na)) > 1e-4:
            return 0.0  # parallel but offset
    # build a basis in the plane
    ref = (1.0, 0.0, 0.0)
    if abs(_dot(na, ref)) > 0.9:
        ref = (0.0, 0.0, 1.0)
    axis_u = _norm(_cross(na, ref))
    axis_v = _norm(_cross(na, axis_u))
    origin = tri_a[0]
    a2 = _tri_2d(tri_a, origin, axis_u, axis_v)
    b2 = _tri_2d(tri_b, origin, axis_u, axis_v)
    clipped = clip_convex(a2, b2)
    return poly_2d_area(clipped)


def fan_triangles(pts):
    """Fan-triangulate a polygon (assumes it is well-formed and convex-ish)."""
    tris = []
    for i in range(1, len(pts) - 1):
        tris.append((pts[0], pts[i], pts[i + 1]))
    return tris


# ---------------------------------------------------------------------------
# measurement
# ---------------------------------------------------------------------------

def opening_faces(obj):
    """Triangles of an object treated as an opening (door/window/void)."""
    mw = obj.matrix_world
    mesh = obj.data
    tris = []
    if not hasattr(mesh, "polygons"):
        return tris
    verts = [mw @ v.co for v in mesh.vertices]
    for poly in mesh.polygons:
        pts = [verts[i] for i in poly.vertices]
        if len(pts) < 3:
            continue
        tris.extend(fan_triangles(pts))
    return tris


def _bbox(pts):
    minx = miny = minz = 1e30
    maxx = maxy = maxz = -1e30
    for p in pts:
        if p[0] < minx: minx = p[0]
        if p[0] > maxx: maxx = p[0]
        if p[1] < miny: miny = p[1]
        if p[1] > maxy: maxy = p[1]
        if p[2] < minz: minz = p[2]
        if p[2] > maxz: maxz = p[2]
    return (minx, miny, minz, maxx, maxy, maxz)


def _bbox_hit(a, b, pad=1e-4):
    return (a[0] <= b[3] + pad and a[3] >= b[0] - pad and
            a[1] <= b[4] + pad and a[4] >= b[1] - pad and
            a[2] <= b[5] + pad and a[5] >= b[2] - pad)


def surface_rows(objects, scene, openings=None, group_by="MATERIAL",
                 area_scale=1.0, dedupe=True):
    """Per-group surface area table.

    group_by: "MATERIAL" or "OBJECT".
    openings: list of objects whose faces carve voids out of coincident faces.
    area_scale: plain multiplier applied to every area (display units).
    """
    openings = openings or []
    open_tris = []
    for o in openings:
        open_tris.extend(opening_faces(o))
    # Bounding boxes of the openings let us skip clipping for faces that cannot
    # possibly touch one. Without this, a 40k-face wall spends 24 s on work that
    # only concerns the handful of faces around three windows.
    open_boxes = [_bbox(t) for t in open_tris]

    table = {}
    for obj in objects:
        if getattr(obj, "type", None) != "MESH":
            continue
        mesh = obj.data
        if len(mesh.polygons) == 0:
            continue
        mw = obj.matrix_world
        verts = [mw @ v.co for v in mesh.vertices]
        mats = [s.material for s in obj.material_slots]

        for poly in mesh.polygons:
            pts = [verts[i] for i in poly.vertices]
            if len(pts) < 3:
                continue
            area = polygon_area(pts)
            if area <= EPS:
                continue

            if open_tris:
                face_box = _bbox(pts)
                near = [ot for ot, ob in zip(open_tris, open_boxes) if _bbox_hit(face_box, ob)]
                if near:
                    tris = fan_triangles(pts)
                    cut = 0.0
                    for t in tris:
                        hit = 0.0
                        for ot in near:
                            hit += overlap_area_3d(t, ot)
                        # an opening cannot remove more than the triangle itself
                        cut += min(hit, triangle_area(*t))
                    area = max(0.0, area - cut)

            if area <= EPS:
                continue

            mi = poly.material_index
            mat_name = ""
            if 0 <= mi < len(mats) and mats[mi] is not None:
                mat_name = mats[mi].name
            if group_by == "OBJECT":
                key = (obj.name, mat_name)
            else:
                key = (mat_name or "(no material)", "")

            rec = table.get(key)
            if rec is None:
                rec = {"group": key[0], "object": obj.name if group_by == "MATERIAL" else "",
                       "area": 0.0, "faces": 0}
                table[key] = rec
            rec["area"] += area * area_scale
            rec["faces"] += 1

    rows = list(table.values())
    rows.sort(key=lambda r: -r["area"])
    return rows


def apply_waste_and_price(rows, waste_pct=0.0, price_per_area=None):
    """Add a waste allowance and cost. price_per_area maps group -> unit price."""
    price_per_area = price_per_area or {}
    out = []
    for r in rows:
        base = r["area"]
        with_waste = base * (1.0 + waste_pct / 100.0)
        price = price_per_area.get(r["group"], 0.0)
        out.append({
            "group": r["group"],
            "object": r.get("object", ""),
            "faces": r["faces"],
            "area": base,
            "area_with_waste": with_waste,
            "price_per_area": price,
            "cost": with_waste * price,
        })
    out.sort(key=lambda r: -r["area_with_waste"])
    return out


def totals(rows):
    return {
        "groups": len(rows),
        "area": sum(r["area"] for r in rows),
        "area_with_waste": sum(r["area_with_waste"] for r in rows),
        "cost": sum(r["cost"] for r in rows),
    }
