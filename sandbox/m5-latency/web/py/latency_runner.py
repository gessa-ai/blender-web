# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# M5 latency-budget WASM-SIDE runner. Runs INSIDE the windowed blender_browser
# wasm module, launched by latency-boot.js's `--python-expr` stager, which has
# already decoded the ui_simulate `modules` package (easy_keys, ui_test_utils),
# the probe module (m5_latency) and this runner into WasmFS at /m5lat and set
# sys.argv = [_, '--', <mod.func>, <N>, <SPACING>].
#
# Emits M5LAT_* status lines on raw fd 2 (os.write) - the only reliable
# Python->browser channel on this build (bare print()/stderr never flush; see
# notes/m5-windowed-replay.md). Calls NO GPU-readback/screenshot op.

import os
import sys

_ROOT = "/m5lat"
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _emit(*parts):
    try:
        os.write(2, (" ".join(str(p) for p in parts) + "\n").encode("utf-8"))
    except Exception:
        pass


def _argv_tail():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def main():
    if "bpy" not in sys.modules:
        raise Exception("This must run inside Blender")
    import bpy

    tail = _argv_tail()
    if not tail:
        _emit("M5LAT_USAGE", "expected -- <module.func> [N] [SPACING]")
        return
    session = tail[0]
    n = int(tail[1]) if len(tail) > 1 else None
    spacing = float(tail[2]) if len(tail) > 2 else None
    _emit("M5LAT_BEGIN", session, n, spacing)

    from modules import easy_keys

    mod_name, fn_name = session.split(".", 1)

    bpy.context.preferences.view.show_developer_ui = True
    easy_keys.setup_default_preferences(bpy.context.preferences)

    mod = __import__(mod_name)
    if n is not None:
        mod.N = n
    if spacing is not None:
        mod.SPACING = spacing
    test_fn = getattr(mod, fn_name)

    def on_error():
        _emit("M5LAT_SESSION_ERROR", session)

    def on_exit():
        _emit("M5LAT_EXIT", session)
        # Quit LAST; the dump-free latency run has nothing else to flush.
        try:
            bpy.ops.wm.quit_blender()
        except Exception:
            pass

    easy_keys.run(test_fn(), on_error=on_error, on_exit=on_exit)
    _emit("M5LAT_ARMED", session)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import traceback
        _emit("M5LAT_FATAL", repr(exc))
        for ln in traceback.format_exc().splitlines():
            _emit("M5LAT_TB", ln)
