# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# M5 tier-(c) WASM-SIDE event-simulate runner (the browser half of the oracle
# sandbox/m5-prep/m5_run_session.py). Runs INSIDE the windowed blender_browser
# wasm module, launched by a `--python-expr` stager (m5-boot.js) that has already
# decoded the ui_simulate `modules` package, the session module m5_core and
# state_dump into WasmFS at /m5 and set sys.argv = [_, '--', <session>]. Driven by
# the GHOST-web WM main loop + `--enable-event-simulate`.
#
# CHANNEL FACTS (probed on this build, see notes/m5-windowed-replay.md):
#   * wasm stdout is block-buffered and never flushes (WM_main is an
#     emscripten_set_main_loop that returns without the process exiting), so a
#     bare print() and even sys.stderr.write()+flush() NEVER reach the JS console.
#   * os.write(2, ...) (raw fd 2) DOES reach the console per newline. It is the
#     only reliable Python->browser channel, so every emission here uses it.
#   * The `--log operator` CLOG lines also land on fd 2 in the native
#     "HH:MM.mmm  operator | Started bpy.ops...." form, so the operator trace is
#     collected straight off the console by the driver - no file needed.
#   * The post-session bpy.data dump is emitted as base64 chunks on fd 2 (race
#     free) AND written to /m5/out.json (readable via FS.readFile from the browser
#     thread as a cross-check).
#
# It calls NO bpy screenshot / render / GPU-readback op (those crash the WM worker
# on the windowed build; deferral gpu-sync-readback-windowed). The dump is pure
# bpy-data mirroring, exactly the native method. It quits at the very end so the
# closing wm.quit_blender() lands in the trace exactly like the native golden
# (logged before teardown; the dump is already emitted, so a teardown abort is
# harmless).

import os
import sys
import base64
import json
import hashlib

_ROOT = "/m5"
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

STATE_OUT = "/m5/out.json"
CHUNK = 1500


def _emit(*parts):
    line = " ".join(str(p) for p in parts) + "\n"
    try:
        os.write(2, line.encode("utf-8"))
    except Exception:
        pass


def _emit_chunks(tag, text):
    b = base64.b64encode(text.encode("utf-8")).decode("ascii")
    n = (len(b) + CHUNK - 1) // CHUNK
    for i in range(n):
        piece = b[i * CHUNK:(i + 1) * CHUNK]
        try:
            os.write(2, ("%s %d %d %s\n" % (tag, i, n, piece)).encode("ascii"))
        except Exception:
            pass


def _session_name():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return argv[0] if argv else None


def main():
    if "bpy" not in sys.modules:
        raise Exception("This must run inside Blender")
    import bpy

    session = _session_name()
    if not session:
        _emit("M5_USAGE", "expected -- <module.func>")
        return
    _emit("M5_BEGIN", session)

    from modules import easy_keys
    import state_dump

    mod_name, fn_name = session.split(".", 1)

    bpy.context.preferences.view.show_developer_ui = True
    easy_keys.setup_default_preferences(bpy.context.preferences)

    mod = __import__(mod_name)
    test_fn = getattr(mod, fn_name)

    state = {"error": None}

    def on_error():
        state["error"] = "session_error"
        _emit("M5_SESSION_ERROR", session)

    def on_exit():
        tag = "error" if state["error"] else "ok"
        try:
            dump = state_dump.build_dump("m5:%s" % session)
            dump["_m5_session"] = session
            dump["_m5_result"] = tag
            text = json.dumps(dump, sort_keys=True, ensure_ascii=True, indent=1) + "\n"
            with open(STATE_OUT, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            sha = hashlib.sha256((text + "\n").encode("utf-8")).hexdigest()
            _emit("M5_STATE_%s" % tag.upper(), STATE_OUT, "len=%d" % len(text),
                  "sha256=%s" % sha)
            _emit_chunks("M5_OUT", text)
            _emit("M5_OUT_END", session)
        except Exception as exc:
            import traceback
            _emit("M5_DUMP_ERROR", repr(exc))
            for ln in traceback.format_exc().splitlines():
                _emit("M5_TB", ln)
        _emit("M5_DONE", session)
        # Quit LAST so the closing bpy.ops.wm.quit_blender() line lands in the
        # operator trace exactly like the native golden (logged before GPU
        # teardown; dump already emitted, so a teardown abort is harmless).
        try:
            bpy.ops.wm.quit_blender()
        except Exception:
            pass

    easy_keys.run(test_fn(), on_error=on_error, on_exit=on_exit)
    _emit("M5_ARMED", session)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import traceback
        _emit("M5_FATAL", repr(exc))
        for ln in traceback.format_exc().splitlines():
            _emit("M5_TB", ln)
