# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# M5 tier-(c) event-simulate sessions — the GOAL.md M5 core interaction loop:
#   select (select-all / click-select), G/R/S with axis constraints,
#   Tab edit-mode, extrude, bevel, undo depth.
#
# Authored in the upstream ui_simulate DSL (modules.easy_keys / ui_test_utils).
# Each top-level function (no leading underscore) is a session: a generator that
# yields event batches; run_blender_setup-style harness drives it via a timer
# (requires --enable-event-simulate + a real GHOST window; see notes/m5-ui-simulate-prep.md).
#
# t.assert* give an immediate in-session sanity gate; the durable parity artifact
# is the post-session state dump (sandbox/corpus-prep/state_dump.py build_dump)
# captured by m5_run_session.py on_exit, diffed oracle-vs-wasm exactly.
#
# Scene: factory-startup default (Cube selected, Camera, Light). smooth_view is
# disabled by easy_keys.setup_default_preferences, so the viewport is stable and
# numeric-entry transforms are deterministic.

import modules.ui_test_utils as ui


def _v3d_center(window):
    area = ui.get_window_area_by_type(window, 'VIEW_3D')
    return ui.get_area_center(area)


def _screen_loc(window, name):
    """Screen-space (int x, y) of object `name`'s origin in the VIEW_3D window region."""
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    area = ui.get_window_area_by_type(window, 'VIEW_3D')
    region = next(r for r in area.regions if r.type == 'WINDOW')
    rv3d = region.data
    ob = window.view_layer.objects[name]
    co = location_3d_to_region_2d(region, rv3d, ob.matrix_world.translation)
    # location_3d_to_region_2d is REGION-relative; event_simulate x/y are
    # WINDOW-relative, so offset by the region's window position.
    return int(co[0]) + region.x, int(co[1]) + region.y


def _selected_count(window):
    return sum(1 for o in window.view_layer.objects if o.select_get())


# -----------------------------------------------------------------------------
# 1. Selection — select-all toggle + click-select.

def object_select_all():
    e, t, window = ui.test_window()
    e.cursor_position_set(*_v3d_center(window), move=True)
    yield
    yield e.alt.a()                         # Deselect all.
    t.assertEqual(_selected_count(window), 0)
    yield e.a()                             # Select all.
    t.assertEqual(_selected_count(window), len(window.view_layer.objects))


def object_click_select():
    e, t, window = ui.test_window()
    e.cursor_position_set(*_v3d_center(window), move=True)
    yield
    yield e.alt.a()                         # Deselect all.
    t.assertEqual(_selected_count(window), 0)

    e.cursor_position_set(*_screen_loc(window, "Cube"), move=True)
    yield
    e.leftmouse.tap()                       # Exclusive-select the Cube.
    yield
    t.assertEqual(window.view_layer.objects.active.name, "Cube")
    t.assertEqual(_selected_count(window), 1)


# -----------------------------------------------------------------------------
# 2. Transforms with axis constraints — G / R / S.

def object_transform_grxsz():
    e, t, window = ui.test_window()
    e.cursor_position_set(*_v3d_center(window), move=True)
    yield
    cube = window.view_layer.objects["Cube"]
    yield e.a()                             # Select all.

    yield e.g().x().text("2").ret()         # Grab, constrain X, +2.
    t.assertAlmostEqual(cube.location.x, 2.0, places=4)

    yield e.r().z().text("45").ret()        # Rotate, constrain Z, 45deg.
    from math import radians
    t.assertAlmostEqual(cube.rotation_euler.z, radians(45.0), places=4)

    yield e.s().text("2").ret()             # Scale uniform 2x.
    t.assertAlmostEqual(cube.scale.x, 2.0, places=4)
    t.assertAlmostEqual(cube.scale.z, 2.0, places=4)


# -----------------------------------------------------------------------------
# 3. Edit-mode toggle (Tab).

def edit_mode_toggle():
    e, t, window = ui.test_window()
    e.cursor_position_set(*_v3d_center(window), move=True)
    yield
    obj = window.view_layer.objects.active
    yield e.tab()                           # Into edit mode.
    t.assertEqual(obj.mode, 'EDIT')
    yield e.tab()                           # Back to object mode.
    t.assertEqual(obj.mode, 'OBJECT')


# -----------------------------------------------------------------------------
# 4. Mesh extrude (edit mode).

def mesh_extrude_region():
    e, t, window = ui.test_window()
    e.cursor_position_set(*_v3d_center(window), move=True)
    yield
    obj = window.view_layer.objects.active

    yield e.tab()                           # Edit mode.
    yield e.three()                         # Face select mode.
    yield e.a()                             # Select all faces.
    yield e.e().z().text("1").ret()         # Extrude region, +1 on Z.
    yield e.tab()                           # Back to object mode (flush bmesh -> mesh).
    # Default cube = 8 verts; extruding all faces adds geometry.
    t.assertGreater(len(obj.data.vertices), 8)


# -----------------------------------------------------------------------------
# 5. Mesh bevel (edit mode, numeric offset).

def mesh_bevel():
    e, t, window = ui.test_window()
    e.cursor_position_set(*_v3d_center(window), move=True)
    yield
    obj = window.view_layer.objects.active
    yield e.tab()                           # Edit mode.
    yield e.a()                             # Select all.
    yield e.ctrl.b().text("0.2").ret()      # Bevel, numeric offset 0.2.
    yield e.tab()                           # Object mode.
    t.assertGreater(len(obj.data.vertices), 8)


# -----------------------------------------------------------------------------
# 6. Undo depth — walk the undo stack and assert each rung.

def undo_depth():
    e, t, window = ui.test_window()
    e.cursor_position_set(*_v3d_center(window), move=True)
    yield
    obj = window.view_layer.objects.active

    yield e.tab()                           # Edit mode.
    yield e.a()                             # Select all.
    n0 = len(_bmesh(obj).verts)             # 8

    yield e.e().z().text("1").ret()         # Extrude 1.
    n1 = len(_bmesh(obj).verts)
    t.assertGreater(n1, n0)

    yield e.e().z().text("1").ret()         # Extrude 2.
    n2 = len(_bmesh(obj).verts)
    t.assertGreater(n2, n1)

    yield e.ctrl.z(1)                       # Undo the 2nd extrude.
    t.assertEqual(len(_bmesh(obj).verts), n1)

    yield e.ctrl.z(1)                       # Undo the 1st extrude.
    t.assertEqual(len(_bmesh(obj).verts), n0)

    yield e.ctrl.shift.z(1)                 # Redo the 1st extrude.
    t.assertEqual(len(_bmesh(obj).verts), n1)

    yield e.tab()                           # Object mode (flush for the state dump).


def _bmesh(obj):
    import bmesh
    return bmesh.from_edit_mesh(obj.data)
