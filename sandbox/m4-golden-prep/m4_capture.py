# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# M4-golden-prep — in-Blender driver to capture the M4 first-pixels goldens with
# Blender's OWN screenshot operator (bpy.ops.screen.screenshot), which reads the
# window client-area framebuffer exactly as canvas.toDataURL() will on the wasm
# side. Two states:
#   --mode splash     : the auto-shown startup splash (Quick Setup) over the
#                       default cube. Fresh variant (no "Import previous prefs")
#                       is guaranteed by launching with BLENDER_USER_CONFIG set to
#                       an empty dir (see capture_m4_golden.sh) which makes
#                       PREFERENCES_OT_copy_prev.poll() return False
#                       (userpref.py:154-159) -> can_import False, matching a
#                       fresh-OPFS wasm boot.
#   --mode workspace  : the post-splash default Layout (cube/camera/light). The
#                       startup splash is suppressed by setting show_splash=False
#                       at module scope: --python runs (ARG_PASS_FINAL) BEFORE
#                       WM_init_splash_on_startup (creator.cc:661), so the splash
#                       never appears -> no popup to dismiss, no event injection.
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
    print("M4_CAPTURE_USAGE --out <file.png> --mode <splash|workspace> [--delay S]")
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
