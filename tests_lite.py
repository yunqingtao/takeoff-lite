"""Headless tests for Takeoff Lite. Run with:
    blender -b --factory-startup --python tests_lite.py
"""
import os
import sys
import re

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))

import bpy

FAILS = []
CHECKS = [0]


def check(name, got, want, tol=1e-5):
    CHECKS[0] += 1
    if isinstance(want, str):
        ok = got == want
        print("%-52s %s got=%r want=%r" % (name, "ok  " if ok else "FAIL", got, want))
    elif isinstance(want, (list, tuple, set)):
        ok = set(got) == set(want) if isinstance(want, set) else list(got) == list(want)
        print("%-52s %s got=%r want=%r" % (name, "ok  " if ok else "FAIL", got, want))
    else:
        ok = abs(float(got) - float(want)) <= tol
        print("%-52s %s got=%.6f want=%.6f" % (name, "ok  " if ok else "FAIL", float(got), float(want)))
    if not ok:
        FAILS.append("%s: got %r want %r" % (name, got, want))


def reset_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for me in list(bpy.data.meshes):
        if me.users == 0:
            bpy.data.meshes.remove(me)
    for mat in list(bpy.data.materials):
        if mat.users == 0:
            bpy.data.materials.remove(mat)
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'
    sc.unit_settings.length_unit = 'METERS'
    sc.unit_settings.scale_length = 1.0
    while len(sc.tkl.rows):
        sc.tkl.rows.remove(0)


def make_mesh_object(name, verts, faces, material=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    if material is not None:
        ob.data.materials.append(material)
    return ob


def make_material(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    return m


# ---------------------------------------------------------------------------
print("\n== 1. module import & registration ==")
import takeoff_lite

print("takeoff_lite at", os.path.dirname(takeoff_lite.__file__))
bpy.ops.preferences.addon_enable(module="takeoff_lite")
check("scene.tkl registered", hasattr(bpy.types.Scene, "tkl"), True)
check("measure operator present", hasattr(bpy.types, "TKL_OT_measure"), True)
check("scene.tko NOT registered (paid addon absent)", hasattr(bpy.types.Scene, "tko"), False)

# every icon string must exist in this Blender build
icons = set()
with open(os.path.join(os.path.dirname(takeoff_lite.__file__), "__init__.py"), encoding="utf-8") as fh:
    src = fh.read()
for m in re.finditer(r"icon='([A-Z0-9_]+)'", src):
    icons.add(m.group(1))
valid = {i.identifier for i in
         bpy.types.UILayout.bl_rna.functions["operator"].parameters["icon"].enum_items}
check("all %d ui icons valid" % len(icons), sorted(i for i in icons if i not in valid), [])
check("icons actually found", len(icons) > 0, True)

# ---------------------------------------------------------------------------
print("\n== 2. paid features really absent ==")
s = bpy.context.scene.tkl
row_props = set(takeoff_lite.TKL_Row.bl_rna.properties.keys())
set_props = set(takeoff_lite.TKL_Settings.bl_rna.properties.keys())
check("row props have no price/cost", sorted(row_props & {"price", "cost"}), [])
check("settings have no cost total", "last_total_cost" in set_props, False)
check("no CSV operator class", hasattr(takeoff_lite, "TKL_OT_export_csv"), False)
check("no set_price operator class", hasattr(takeoff_lite, "TKL_OT_set_price"), False)
ops = [o for o in dir(bpy.ops.tkl)]
check("only lite operators exposed", sorted(ops),
      sorted(["buy", "clear", "clear_openings", "copy_table", "measure", "toggle_opening"]))

# ---------------------------------------------------------------------------
print("\n== 3. four-wall room, one floor ==")
reset_scene()
paint = make_material("Paint")
tile = make_material("Tile")
H = 2.5
make_mesh_object("Wall_S", [(0, 0, 0), (4, 0, 0), (4, 0, H), (0, 0, H)], [(0, 1, 2, 3)], paint)
make_mesh_object("Wall_N", [(0, 3, 0), (4, 3, 0), (4, 3, H), (0, 3, H)], [(0, 1, 2, 3)], paint)
make_mesh_object("Wall_W", [(0, 0, 0), (0, 3, 0), (0, 3, H), (0, 0, H)], [(0, 1, 2, 3)], paint)
make_mesh_object("Wall_E", [(4, 0, 0), (4, 3, 0), (4, 3, H), (4, 0, H)], [(0, 1, 2, 3)], paint)
make_mesh_object("Floor", [(0, 0, 0), (4, 0, 0), (4, 3, 0), (0, 3, 0)], [(0, 1, 2, 3)], tile)

bpy.context.view_layer.update()
bpy.ops.object.select_all(action='DESELECT')

r = bpy.ops.tkl.measure()
check("measure returns FINISHED", r, {'FINISHED'})
area_by = {row.group: row.area for row in s.rows}
check("Paint area 35", area_by.get("Paint", 0.0), 35.0)
check("Tile area 12", area_by.get("Tile", 0.0), 12.0)
check("two rows", len(s.rows), 2)
check("unit label m2", s.unit_label, "m2")
check("total with 10% waste = 51.7", s.last_area, 51.7)
check("net total = 47", s.last_net, 47.0)
check("no openings yet", s.opening_count, 0)

# ---------------------------------------------------------------------------
print("\n== 4. door deduction ==")
door = make_mesh_object("Door_Void", [(1, 0, 0), (1.9, 0, 0), (1.9, 0, 2.1), (1, 0, 2.1)],
                        [(0, 1, 2, 3)], make_material("Void"))
door.select_set(True)
bpy.context.view_layer.objects.active = door
check("toggle_opening ok", bpy.ops.tkl.toggle_opening(), {'FINISHED'})
check("door tagged", bool(door.get("tko_is_opening")), True)

bpy.ops.object.select_all(action='DESELECT')
bpy.ops.tkl.measure()
area_by = {row.group: row.area for row in s.rows}
check("Paint after door 33.11", area_by.get("Paint", 0.0), 33.11)
check("Tile unchanged 12", area_by.get("Tile", 0.0), 12.0)
check("opening counted", s.opening_count, 1)
check("Void material absent from table", "Void" in area_by, False)
check("total (33.11+12)*1.1", s.last_area, 45.11 * 1.1)

# ---------------------------------------------------------------------------
print("\n== 5. window in a different wall ==")
win = make_mesh_object("Win_Void", [(0, 1, 1), (0, 2, 1), (0, 2, 2), (0, 1, 2)],
                       [(0, 1, 2, 3)], make_material("Void"))
win["tko_is_opening"] = True
bpy.ops.tkl.measure()
area_by = {row.group: row.area for row in s.rows}
check("Paint with door+window 32.11", area_by.get("Paint", 0.0), 33.11 - 1.0)
check("two openings", s.opening_count, 2)

# ---------------------------------------------------------------------------
print("\n== 6. waste percentage drives the total ==")
s.waste_pct = 0.0
bpy.ops.tkl.measure()
check("0% waste total = 44.11", s.last_area, 44.11)
s.waste_pct = 15.0
bpy.ops.tkl.measure()
check("15% waste total", s.last_area, 44.11 * 1.15)
s.waste_pct = 10.0
bpy.ops.tkl.measure()
check("back to 10%", s.last_area, 44.11 * 1.1)

# ---------------------------------------------------------------------------
print("\n== 7. copy table text ==")
txt = takeoff_lite._table_text(bpy.context)
lines = txt.split("\n")
check("header present", lines[0].startswith("item"), True)
check("row count = rows+2", len(lines), len(s.rows) + 2)
check("total line has two numbers", lines[-1].split("\t")[0], "TOTAL")
paint_line = [l for l in lines if l.startswith("Paint")][0]
check("paint line 3 columns", len(paint_line.split("\t")), 3)
check("clipboard operator exists", hasattr(bpy.types, "TKL_OT_copy_table"), True)

# ---------------------------------------------------------------------------
print("\n== 8. feet scene ==")
reset_scene()
sc = bpy.context.scene
sc.unit_settings.system = 'IMPERIAL'
sc.unit_settings.length_unit = 'FEET'
sc.unit_settings.scale_length = 0.3048   # 1 unit = 1 foot
mat = make_material("Plaster")
make_mesh_object("Quad", [(0, 0, 0), (10, 0, 0), (10, 0, 10), (0, 0, 10)], [(0, 1, 2, 3)], mat)
bpy.context.view_layer.update()
bpy.ops.tkl.measure()
area_by = {row.group: row.area for row in s.rows}
check("unit label sq ft", s.unit_label, "sq ft")
# 10 ft x 10 ft = 100 ft2 = 9.2903 m2, expressed back in ft2
check("100 ft2 surface", area_by.get("Plaster", 0.0), 100.0, 1e-2)

# ---------------------------------------------------------------------------
print("\n== 9. selection scope ==")
reset_scene()
m1 = make_material("A")
o1 = make_mesh_object("Big", [(0, 0, 0), (2, 0, 0), (2, 0, 2), (0, 0, 2)], [(0, 1, 2, 3)], m1)
o2 = make_mesh_object("Small", [(0, 1, 0), (1, 1, 0), (1, 1, 1), (0, 1, 1)], [(0, 1, 2, 3)], m1)
bpy.context.view_layer.update()
bpy.ops.object.select_all(action='DESELECT')
bpy.ops.tkl.measure()
check("all objects = 5.0", s.rows[0].area, 5.0)
s.respect_selection = True
o2.select_set(True)
bpy.context.view_layer.objects.active = o2
bpy.ops.tkl.measure()
check("selected only = 1.0", s.rows[0].area, 1.0)

# ---------------------------------------------------------------------------
print("\n== 10. clear ==")
check("clear ok", bpy.ops.tkl.clear(), {'FINISHED'})
check("rows empty", len(s.rows), 0)
check("total zeroed", s.last_area, 0.0)

# ---------------------------------------------------------------------------
print("\n%d checks, %d failures" % (CHECKS[0], len(FAILS)))
for f in FAILS:
    print("  FAIL " + f)
print("RESULT: " + ("ALL PASS" if not FAILS else "FAILED"))
