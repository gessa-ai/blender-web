# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# M4 golden capture driver. Run INSIDE the pinned official Blender 5.2.0
# (oracle/blender-5.2.0) via `--python capture.py -- <mode> <run> <outdir>`.
#
#   mode=clean : opens a pre-saved default-cube .blend (splash suppressed), then
#                captures full-window (no splash) + viewport workbench via
#                render.opengl + an EEVEE-Next still of the default cube.
#   mode=splash: factory-startup (splash shown); captures the full window with the
#                splash on top == the literal M4 gate frame (splash + default cube).
#
# Captures run from a timer so the window/GPU context is live. Deterministic:
# fixed render resolution, TAA sample count, and view state (from the saved file).
import bpy, sys, os, json

argv = sys.argv[sys.argv.index("--") + 1:]
MODE, RUN, OUTDIR = argv[0], argv[1], argv[2]
os.makedirs(OUTDIR, exist_ok=True)

RES_X, RES_Y = 1280, 720          # screen-independent render resolution
EEVEE_SAMPLES = 16                 # fixed TAA render samples for the EEVEE still


def _find_view3d():
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        return win, area, region
    return None, None, None


def _facts():
    win = bpy.context.window_manager.windows[0]
    sysp = bpy.context.preferences.system
    sc = bpy.context.scene
    return {
        "mode": MODE, "run": RUN,
        "blender_version": bpy.app.version_string,
        "build_hash": bpy.app.build_hash.decode() if isinstance(bpy.app.build_hash, bytes) else str(bpy.app.build_hash),
        "window_width_px": win.width, "window_height_px": win.height,
        "pref_pixel_size": sysp.pixel_size,      # 2.0 on retina == backing scale
        "pref_ui_scale": sysp.ui_scale,
        "pref_dpi": sysp.dpi,
        "render_res_x": sc.render.resolution_x, "render_res_y": sc.render.resolution_y,
        "render_pct": sc.render.resolution_percentage,
        "engine": sc.render.engine,
    }


def _prep_scene():
    sc = bpy.context.scene
    sc.render.resolution_x = RES_X
    sc.render.resolution_y = RES_Y
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_mode = 'RGBA'
    sc.render.image_settings.color_depth = '8'


def _save_render(path):
    img = bpy.data.images.get('Render Result')
    img.save_render(filepath=path)


def capture():
    facts = _facts()
    try:
        win, area, region = _find_view3d()
        _prep_scene()

        if MODE == 'clean':
            # (a1) full window, no splash (file loaded -> splash suppressed).
            with bpy.context.temp_override(window=win):
                bpy.ops.screen.screenshot(
                    filepath=os.path.join(OUTDIR, f"A_fullwindow_nosplash.run{RUN}.png"))
            # (a2) viewport workbench via render.opengl (deterministic, off-window).
            if area is not None:
                with bpy.context.temp_override(window=win, area=area, region=region):
                    bpy.ops.render.opengl(write_still=False, view_context=True)
                _save_render(os.path.join(OUTDIR, f"B_viewport_workbench.run{RUN}.png"))
            # (c) EEVEE still of the default cube (M6 seed). In 5.2 EEVEE-Next is
            # the only EEVEE, keyed 'BLENDER_EEVEE'. Non-fatal so a render hiccup
            # never loses A/B or the facts dump.
            try:
                sc = bpy.context.scene
                sc.render.engine = 'BLENDER_EEVEE'
                try:
                    sc.eevee.taa_render_samples = EEVEE_SAMPLES
                except Exception as e:
                    print("EEVEE sample set skipped:", e)
                bpy.ops.render.render(write_still=False)
                _save_render(os.path.join(OUTDIR, f"C_eevee_cube.run{RUN}.png"))
                facts["engine_eevee"] = sc.render.engine
                facts["eevee_samples"] = EEVEE_SAMPLES
            except Exception as e:
                import traceback; traceback.print_exc()
                print("EEVEE_CAPTURE_FAIL", repr(e))
                facts["eevee_error"] = repr(e)

        elif MODE == 'splash':
            # (b) full window WITH splash on top == the M4 gate frame.
            with bpy.context.temp_override(window=win):
                bpy.ops.screen.screenshot(
                    filepath=os.path.join(OUTDIR, f"D_fullwindow_splash.run{RUN}.png"))

        with open(os.path.join(OUTDIR, f"facts.{MODE}.run{RUN}.json"), "w") as f:
            json.dump(facts, f, indent=2, sort_keys=True)
        print("CAPTURE_OK", MODE, RUN, json.dumps(facts))
    except Exception as e:
        import traceback; traceback.print_exc()
        print("CAPTURE_FAIL", MODE, RUN, repr(e))
    finally:
        bpy.ops.wm.quit_blender()
    return None


# Fire once after the UI + GPU context are up.
bpy.app.timers.register(capture, first_interval=2.0)
