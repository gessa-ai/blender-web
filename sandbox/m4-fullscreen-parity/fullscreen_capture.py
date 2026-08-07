# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported/extended for the web from sandbox/m4-golden-prep/m4_capture.py @ fbe6228777e7
#
# M4-fullscreen-parity - in-Blender driver to capture a FULL-WINDOW native golden
# with Blender's OWN screenshot operator (bpy.ops.screen.screenshot), which reads
# the window client-area framebuffer (WM_window_pixels_read, screendump.cc:70) -
# exactly what canvas.toDataURL() / a CDP canvas screenshot reads on the wasm side.
#
# This is the same mechanics as m4-golden-prep's m4_capture.py, restricted to the
# WORKSPACE state (the whole Blender window: topbar with File/Edit, toolbar,
# 3D viewport with the shaded default cube + grid + gizmos, outliner + properties
# sidebar, status bar). The splash is NEVER shown here - this is a clean, honest
# full-window comparison target with no popup to dismiss and no event injection.
#
#   --mode workspace  : the post-splash default Layout. The startup splash is
#                       suppressed by setting show_splash=False at module scope:
#                       --python-expr / --python runs (ARG_PASS_FINAL) BEFORE
#                       WM_init_splash_on_startup (creator.cc:661), so the splash
#                       never appears.
#   --mode splash     : kept for parity with m4_capture.py (auto-shown Quick Setup
#                       splash over the cube); not the fullscreen-parity target.
#
# Must run in a GUI Blender (NOT --background) so the WM event loop drives the
# bpy.app.timers callback and the framebuffer is drawn. screenshot forces a full
# WM_redraw_windows before reading pixels (screendump.cc:69), so a modest --delay
# only needs to cover startup, not draw settling.
import bpy
import sys


def getarg(name, default=None):
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return argv[argv.index(name) + 1] if name in argv else default


OUT = getarg("--out")
MODE = getarg("--mode", "workspace")
DELAY = float(getarg("--delay", "1.0"))

if not OUT:
    print("FULLSCREEN_CAPTURE_USAGE --out <file.png> --mode <splash|workspace> [--delay S]")
    sys.exit(2)

# Workspace state: suppress the startup splash entirely (USER_SPLASH_DISABLE).
if MODE == "workspace":
    bpy.context.preferences.view.show_splash = False


def shot_and_quit():
    bpy.ops.screen.screenshot(filepath=OUT)
    try:
        bpy.ops.wm.quit_blender()
    except Exception:
        import os
        os._exit(0)
    return None


bpy.app.timers.register(shot_and_quit, first_interval=DELAY)
