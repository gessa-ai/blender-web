# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# In-Blender harness for one M5 event-simulate session. Modeled on upstream
# tests/python/ui_simulate/run_blender_setup.py, but instead of only pass/fail it
# captures the POST-SESSION state via sandbox/corpus-prep/state_dump.py build_dump
# so oracle and (later) wasm dumps can be diffed exactly (compare_dumps.py).
#
# Must run inside a GUI Blender (NOT --background) with --enable-event-simulate.
# Invocation (see run_oracle_sessions.sh):
#   BLENDER -p 0 0 800 600 --factory-startup --no-window-frame --no-native-pixels \
#     --enable-event-simulate --python m5_run_session.py -- \
#     --session m5_core.object_select_all --state-out <out.json>

import os
import sys
import json

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
_UI = os.path.join(_ROOT, "upstream", "tests", "python", "ui_simulate")
_SESS = os.path.join(_HERE, "sessions")
_CORPUS = os.path.join(_ROOT, "sandbox", "corpus-prep")
for p in (_UI, _SESS, _CORPUS):
    if p not in sys.path:
        sys.path.insert(0, p)


def _args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    session = state_out = None
    i = 0
    while i < len(argv):
        if argv[i] == "--session":
            session = argv[i + 1]; i += 2
        elif argv[i] == "--state-out":
            state_out = argv[i + 1]; i += 2
        else:
            i += 1
    if not session or not state_out:
        print("M5_USAGE --session <mod.func> --state-out <out.json>")
        sys.exit(2)
    return session, state_out


def main():
    if "bpy" not in sys.modules:
        raise Exception("This must run inside Blender")
    import bpy
    from modules import easy_keys
    import state_dump

    session, state_out = _args()
    mod_name, fn_name = session.split(".", 1)

    bpy.context.preferences.view.show_developer_ui = True
    easy_keys.setup_default_preferences(bpy.context.preferences)

    mod = __import__(mod_name)
    test_fn = getattr(mod, fn_name)

    state = {"done": False, "error": None}

    def _write_dump(tag):
        dump = state_dump.build_dump("m5:%s" % session)
        dump["_m5_session"] = session
        dump["_m5_result"] = tag
        text = json.dumps(dump, sort_keys=True, ensure_ascii=True, indent=1)
        with open(state_out, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.write("\n")
        import hashlib
        print("M5_STATE_%s" % tag.upper(), state_out,
              "sha256=%s" % hashlib.sha256((text + "\n").encode("utf-8")).hexdigest())

    def on_error():
        state["error"] = "session_error"
        print("M5_SESSION_ERROR", session)

    def on_exit():
        # Reached whether the session finished cleanly or errored; capture state
        # either way (tag distinguishes) so a failure is visible, not silent.
        try:
            _write_dump("error" if state["error"] else "ok")
        except Exception as exc:
            print("M5_DUMP_ERROR", repr(exc))
        try:
            bpy.ops.wm.quit_blender()
        except Exception:
            sys.exit(0)

    easy_keys.run(test_fn(), on_error=on_error, on_exit=on_exit)


if __name__ == "__main__":
    main()
