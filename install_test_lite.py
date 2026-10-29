"""Install-from-disk test: unzip into a user scripts dir, enable, measure, copy.

This is the gate that matters - the zip has to work as a stranger would use it.

Run with:
    BLENDER_USER_SCRIPTS=<tmp> blender -b --factory-startup --python install_test_lite.py
"""
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ZIP = os.path.join(HERE, "dist", "takeoff_lite-0.1.1.zip")

import bpy
import addon_utils

FAILS = []


def check(name, cond, detail=""):
    print("%-50s %s %s" % (name, "ok  " if cond else "FAIL", detail))
    if not cond:
        FAILS.append(name)


print("zip:", ZIP, os.path.getsize(ZIP), "bytes")
scripts = os.environ.get("BLENDER_USER_SCRIPTS")
print("BLENDER_USER_SCRIPTS:", scripts)
check("BLENDER_USER_SCRIPTS set", bool(scripts))

names = zipfile.ZipFile(ZIP).namelist()
check("zip has package dir", all(n.startswith("takeoff_lite/") for n in names), str(names[:3]))
check("zip has manifest", "takeoff_lite/blender_manifest.toml" in names)
check("zip has core", "takeoff_lite/core.py" in names)
check("zip has readme", "takeoff_lite/README.md" in names)
check("no __pycache__ in zip", not any("__pycache__" in n for n in names))
check("no .pyc in zip", not any(n.endswith(".pyc") for n in names))

dest = os.path.join(scripts, "addons")
os.makedirs(dest, exist_ok=True)
with zipfile.ZipFile(ZIP) as z:
    z.extractall(dest)
check("extracted to disk", os.path.isdir(os.path.join(dest, "takeoff_lite")))

# make sure the source tree isn't what we're importing
sys.path = [p for p in sys.path if os.path.join(HERE, "src") not in p]
# Blender scanned the scripts dir at startup, before we unzipped; a real user
# restarts or hits Refresh, which puts this same dir on sys.path.
sys.path.insert(0, dest)

mods = addon_utils.modules()
found = [m for m in mods if m.__name__ == "takeoff_lite"]
check("module discovered", bool(found), str([m.__name__ for m in mods if "takeoff" in m.__name__]))

res = addon_utils.enable("takeoff_lite", default_set=False, persistent=True)
ok = bool(addon_utils.check("takeoff_lite")[1])
check("addon enabled", ok, str(res))
check("scene.tkl registered", hasattr(bpy.types.Scene, "tkl"))
check("operator present", hasattr(bpy.ops.tkl, "measure"))

import takeoff_lite
got_dir = os.path.abspath(os.path.dirname(takeoff_lite.__file__)).replace("\\", "/").lower()
want_dir = os.path.abspath(dest).replace("\\", "/").lower()
check("imported from the installed copy", got_dir.startswith(want_dir), got_dir)

# build one 4x3 room + floor and measure
for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob, do_unlink=True)

paint = bpy.data.materials.new("Plaster")
paint.use_nodes = True
tile = bpy.data.materials.new("Tile")
tile.use_nodes = True
H = 2.5


def quad(name, verts, mat):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], [(0, 1, 2, 3)])
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.data.materials.append(mat)
    return ob


quad("Wall_S", [(0, 0, 0), (4, 0, 0), (4, 0, H), (0, 0, H)], paint)
quad("Wall_N", [(0, 3, 0), (4, 3, 0), (4, 3, H), (0, 3, H)], paint)
quad("Wall_W", [(0, 0, 0), (0, 3, 0), (0, 3, H), (0, 0, H)], paint)
quad("Wall_E", [(4, 0, 0), (4, 3, 0), (4, 3, H), (4, 0, H)], paint)
quad("Floor", [(0, 0, 0), (4, 0, 0), (4, 3, 0), (0, 3, 0)], tile)

bpy.context.view_layer.update()
bpy.ops.object.select_all(action='DESELECT')

res = bpy.ops.tkl.measure()
check("measure FINISHED", 'FINISHED' in res, str(res))
s = bpy.context.scene.tkl
areas = {r.group: r.area for r in s.rows}
check("Plaster 35 m2", abs(areas.get("Plaster", 0) - 35.0) < 1e-4, "%.4f" % areas.get("Plaster", 0))
check("Tile 12 m2", abs(areas.get("Tile", 0) - 12.0) < 1e-4, "%.4f" % areas.get("Tile", 0))
check("total incl 10% waste = 51.7", abs(s.last_area - 51.7) < 1e-4, "%.4f" % s.last_area)

# door deduction through the installed copy
door = quad("Door_Void", [(1, 0, 0), (1.9, 0, 0), (1.9, 0, 2.1), (1, 0, 2.1)],
            bpy.data.materials.new("Void"))
door.select_set(True)
bpy.context.view_layer.objects.active = door
bpy.ops.tkl.toggle_opening()
bpy.ops.object.select_all(action='DESELECT')
bpy.ops.tkl.measure()
areas = {r.group: r.area for r in s.rows}
check("Plaster 33.11 after door", abs(areas.get("Plaster", 0) - 33.11) < 1e-4, "%.4f" % areas.get("Plaster", 0))

txt = takeoff_lite._table_text(bpy.context)
check("table text has TOTAL", txt.strip().endswith("TOTAL\t%.3f\t%.3f" % (s.last_net, s.last_area)) or
      "TOTAL" in txt.split("\n")[-1], txt.split("\n")[-1])

print("\ninstall test: %d failures" % len(FAILS))
print("RESULT: " + ("ALL PASS" if not FAILS else "FAILED"))
