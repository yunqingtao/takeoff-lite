bl_info = {
    "name": "Takeoff Lite",
    "author": "Tiger M.M",
    "version": (0, 1, 1),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Takeoff",
    "description": "Surface area per material, openings deducted",
    "category": "Object",
}

import bpy

from .core import (scene_metres_per_unit, to_display_area, area_unit_name,
                   surface_rows, apply_waste_and_price, totals)

OPENING_KEY = "tko_is_opening"
PAID_URL = "https://tnnt.gumroad.com/l/takeoff-studio"


# ---------------------------------------------------------------------------
# state
# ---------------------------------------------------------------------------

class TKL_Row(bpy.types.PropertyGroup):
    group: bpy.props.StringProperty()
    area: bpy.props.FloatProperty(precision=3)
    area_with_waste: bpy.props.FloatProperty(precision=3)
    faces: bpy.props.IntProperty()


class TKL_Settings(bpy.types.PropertyGroup):
    group_by: bpy.props.EnumProperty(
        name="Group by",
        items=(("MATERIAL", "Material", "One row per material - this is what you order"),
               ("OBJECT", "Object + material", "One row per object and material")),
        default="MATERIAL",
    )
    waste_pct: bpy.props.FloatProperty(name="Waste %", default=10.0, min=0.0, max=200.0)
    respect_selection: bpy.props.BoolProperty(name="Selected only", default=False)
    include_hidden: bpy.props.BoolProperty(name="Include hidden", default=False)
    rows: bpy.props.CollectionProperty(type=TKL_Row)
    row_index: bpy.props.IntProperty()
    opening_count: bpy.props.IntProperty()
    unit_label: bpy.props.StringProperty(default="m2")
    last_area: bpy.props.FloatProperty(default=0.0)
    last_net: bpy.props.FloatProperty(default=0.0)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _is_opening(obj):
    return bool(obj.get(OPENING_KEY))


def _targets(context):
    s = context.scene.tkl
    objs = list(context.selected_objects) if s.respect_selection else list(context.scene.objects)
    out = []
    for o in objs:
        if o.type != 'MESH':
            continue
        if _is_opening(o):
            continue
        if not s.include_hidden and o.hide_get():
            continue
        out.append(o)
    return out


def _openings(context):
    s = context.scene.tkl
    objs = list(context.selected_objects) if s.respect_selection else list(context.scene.objects)
    return [o for o in objs if o.type == 'MESH' and _is_opening(o)]


def _compute(context):
    """Measure the scene into scene.tkl.rows. Returns (rows, totals)."""
    s = context.scene.tkl
    scale = scene_metres_per_unit(context.scene)
    objs = _targets(context)
    opens = _openings(context)
    if not s.respect_selection and not s.include_hidden:
        opens = [o for o in opens if not o.hide_get()]
    raw = surface_rows(objs, context.scene, openings=opens, group_by=s.group_by)
    for r in raw:
        r["area"] = r["area"] * (scale ** 2)

    unit = area_unit_name(context.scene.unit_settings.length_unit)
    factor_to_display = to_display_area(1.0, context.scene.unit_settings.length_unit)

    measured = apply_waste_and_price(raw, s.waste_pct, {})
    s.rows.clear()
    for p in measured:
        item = s.rows.add()
        item.group = p["group"]
        item.faces = p["faces"]
        item.area = p["area"] * factor_to_display
        item.area_with_waste = p["area_with_waste"] * factor_to_display

    t = totals([{"area": r.area, "area_with_waste": r.area_with_waste, "cost": 0.0}
                for r in s.rows])
    s.unit_label = unit
    s.last_area = t["area_with_waste"]
    s.last_net = t["area"]
    s.opening_count = len(opens)
    return s.rows, t


def _table_text(context):
    s = context.scene.tkl
    u = s.unit_label
    lines = ["%s\tnet %s\tincl. %s%% waste %s" % ("item", u, int(s.waste_pct), u)]
    for r in s.rows:
        lines.append("%s\t%.3f\t%.3f" % (r.group, r.area, r.area_with_waste))
    lines.append("TOTAL\t%.3f\t%.3f" % (s.last_net, s.last_area))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# operators
# ---------------------------------------------------------------------------

class TKL_OT_measure(bpy.types.Operator):
    bl_idname = "tkl.measure"
    bl_label = "Calculate Area"
    bl_description = "Measure surface area per material for the objects in scope"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        rows, t = _compute(context)
        if not len(rows):
            self.report({'WARNING'}, "Nothing measured - are the walls mesh objects?")
            return {'CANCELLED'}
        self.report({'INFO'}, "%d line(s), %s %s total" %
                    (len(rows), round(t["area_with_waste"], 2), context.scene.tkl.unit_label))
        return {'FINISHED'}


class TKL_OT_toggle_opening(bpy.types.Operator):
    bl_idname = "tkl.toggle_opening"
    bl_label = "Mark as Opening"
    bl_description = "Tag selected objects as doors/windows: their faces are subtracted from whatever they sit in"

    def execute(self, context):
        objs = [o for o in context.selected_objects if o.type == 'MESH']
        if not objs:
            self.report({'WARNING'}, "Select the door/window mesh first")
            return {'CANCELLED'}
        state = None
        for o in objs:
            new = not _is_opening(o)
            o[OPENING_KEY] = new
            state = new
        self.report({'INFO'}, "%s: %s" % (len(objs), "opening" if state else "surface"))
        return {'FINISHED'}


class TKL_OT_clear_openings(bpy.types.Operator):
    bl_idname = "tkl.clear_openings"
    bl_label = "Clear Openings"
    bl_description = "Remove the opening tag from every object in the scene"

    def execute(self, context):
        n = 0
        for o in context.scene.objects:
            if _is_opening(o):
                del o[OPENING_KEY]
                n += 1
        self.report({'INFO'}, "Cleared %d opening tag(s)" % n)
        return {'FINISHED'}


class TKL_OT_copy_table(bpy.types.Operator):
    bl_idname = "tkl.copy_table"
    bl_label = "Copy Table"
    bl_description = "Copy the measured table to the clipboard as tab separated text"

    def execute(self, context):
        s = context.scene.tkl
        if not len(s.rows):
            self.report({'WARNING'}, "Nothing to copy - calculate first")
            return {'CANCELLED'}
        context.window_manager.clipboard = _table_text(context)
        self.report({'INFO'}, "Table copied (%d lines)" % len(s.rows))
        return {'FINISHED'}


class TKL_OT_clear(bpy.types.Operator):
    bl_idname = "tkl.clear"
    bl_label = "Clear Table"

    def execute(self, context):
        s = context.scene.tkl
        s.rows.clear()
        s.last_area = 0.0
        s.last_net = 0.0
        return {'FINISHED'}


class TKL_OT_buy(bpy.types.Operator):
    bl_idname = "tkl.buy"
    bl_label = "Get prices and CSV"
    bl_description = "Open the Takeoff Studio page (unit prices, line costs, quote CSV)"

    def execute(self, context):
        bpy.ops.wm.url_open(url=PAID_URL)
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

class TKL_UL_rows(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.label(text=item.group[:28])
            row.label(text="%.2f" % item.area)
            row.label(text="%.2f" % item.area_with_waste)


class TKL_PT_panel(bpy.types.Panel):
    bl_label = "Takeoff Lite"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Takeoff"

    def draw(self, context):
        s = context.scene.tkl
        layout = self.layout

        col = layout.column(align=True)
        col.prop(s, "group_by")
        col.prop(s, "waste_pct")
        row = col.row(align=True)
        row.prop(s, "respect_selection", toggle=True)
        row.prop(s, "include_hidden", toggle=True)

        layout.operator("tkl.measure", icon='DRIVER_DISTANCE')

        box = layout.box()
        row = box.row(align=True)
        row.label(text="Opening deduction")
        row.label(text="%d tagged" % s.opening_count)
        row = box.row(align=True)
        row.operator("tkl.toggle_opening", text="Mark/Unmark")
        row.operator("tkl.clear_openings", text="Clear")

        box = layout.box()
        box.label(text="Area  (%s)" % s.unit_label)
        if len(s.rows):
            head = box.row(align=True)
            head.label(text="material")
            head.label(text="net")
            head.label(text="+waste")
        box.template_list("TKL_UL_rows", "", s, "rows", s, "row_index", rows=6)

        if len(s.rows):
            box.label(text="Total %s %s" % (round(s.last_area, 2), s.unit_label))

        layout.operator("tkl.copy_table", icon='COPYDOWN')
        layout.operator("tkl.clear", icon='X')

        layout.separator()
        col = layout.column(align=True)
        col.label(text="Unit price, line costs and the")
        col.label(text="quote CSV are in Takeoff Studio.")
        col.operator("tkl.buy", icon='URL')


class TKL_PT_props_panel(bpy.types.Panel):
    bl_label = "Takeoff Lite"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"
    bl_order = 0

    draw = TKL_PT_panel.draw


classes = (
    TKL_Row, TKL_Settings,
    TKL_UL_rows,
    TKL_OT_measure, TKL_OT_toggle_opening, TKL_OT_clear_openings,
    TKL_OT_copy_table, TKL_OT_clear, TKL_OT_buy,
    TKL_PT_panel, TKL_PT_props_panel,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.tkl = bpy.props.PointerProperty(type=TKL_Settings)


def unregister():
    del bpy.types.Scene.tkl
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
