# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# M8 soak activity driver (blender-web). Registered before WM_main via the shell's
# ?pyexpr hook (base64-staged by soak.mjs). Runs INSIDE the windowed WM main loop:
#
#   * a SpaceView3D POST_PIXEL draw handler increments a real per-draw frame
#     counter (advances only when the viewport actually redraws -> a truthful
#     present-liveness signal; the C-side presentBackbuffer printf is capped at 2
#     frames so it cannot serve here);
#   * a bpy.app.timer (KICK) tags the 3D viewport for redraw each tick and, per
#     tick, executes ONE rotating operator from the M5-proven set (select-all,
#     grab/move, edit-mode Tab in/out, undo/redo) with a proper context override;
#   * every HB_TICKS ticks a compact heartbeat is written to fd 2 (the channel the
#     M5 audit proved reaches the browser console) so the Playwright soak sampler
#     can read main-loop liveness + the frame counter cheaply (no per-frame flood).
#
# EVERYTHING in the timer callback is wrapped in try/except: a raised exception
# would make Blender unregister the timer and silently end the soak. The callback
# ALWAYS returns the interval so the loop never stops on an operator error.

import bpy, os, time

_INTERVAL = 0.2          # timer period (s) -> 5 kicks/s
_HB_TICKS = 25           # heartbeat every ~5 s
_state = {
    "t0": time.time(),
    "tick": 0,
    "frames": 0,
    "ops_ok": 0,
    "ops_fail": 0,
    "phase": 0,
    "sel": True,
    "handler": None,
}


def _emit(msg):
    try:
        os.write(2, (msg + "\n").encode("utf-8", "replace"))
    except Exception:
        pass


def _draw_cb():
    _state["frames"] += 1


def _view3d_ctx():
    """Return (window, area, region) for the first 3D viewport, or (None,)*3."""
    wm = bpy.context.window_manager
    for win in wm.windows:
        scr = win.screen
        if not scr:
            continue
        for area in scr.areas:
            if area.type == "VIEW_3D":
                region = next((r for r in area.regions if r.type == "WINDOW"), None)
                return win, area, region
    return None, None, None


def _run_one_op(win, area, region):
    """Execute one rotating operator. Returns True on clean run."""
    phase = _state["phase"] % 4
    _state["phase"] += 1
    with bpy.context.temp_override(window=win, area=area, region=region):
        if phase == 0:
            # select-all toggle (churns selection state)
            act = "SELECT" if _state["sel"] else "DESELECT"
            _state["sel"] = not _state["sel"]
            if bpy.context.mode == "OBJECT":
                bpy.ops.object.select_all(action=act)
            else:
                bpy.ops.mesh.select_all(action=act)
        elif phase == 1:
            # grab/move: non-modal translate by a small delta (exercises depsgraph)
            d = 0.1 if (_state["tick"] // 4) % 2 == 0 else -0.1
            bpy.ops.transform.translate(value=(d, 0.0, 0.0))
        elif phase == 2:
            # Tab in/out: edit-mode toggle (bmesh alloc/free -- prime leak surface)
            if bpy.context.active_object is not None:
                bpy.ops.object.editmode_toggle()
        else:
            # undo / redo churn (undo-stack push/pop -- prime leak surface)
            if (_state["tick"] // 4) % 2 == 0:
                bpy.ops.ed.undo()
            else:
                bpy.ops.ed.redo()
    return True


def _tick():
    try:
        _state["tick"] += 1
        win, area, region = _view3d_ctx()
        # kick a redraw so the draw handler (frame counter) advances every tick
        if area is not None:
            try:
                area.tag_redraw()
            except Exception:
                pass
        # one operator per tick
        if win is not None and area is not None and region is not None:
            try:
                _run_one_op(win, area, region)
                _state["ops_ok"] += 1
            except Exception as e:
                _state["ops_fail"] += 1
                if _state["ops_fail"] <= 5:
                    _emit("SOAK_OPFAIL phase=%d %s: %s"
                          % (_state["phase"] % 4, type(e).__name__, str(e)[:120]))
        # throttled heartbeat
        if _state["tick"] % _HB_TICKS == 0:
            el = time.time() - _state["t0"]
            _emit("SOAK_HB t=%.1f tick=%d frames=%d ops_ok=%d ops_fail=%d"
                  % (el, _state["tick"], _state["frames"], _state["ops_ok"], _state["ops_fail"]))
    except Exception as e:
        # never let the timer die
        _emit("SOAK_TICKERR %s: %s" % (type(e).__name__, str(e)[:160]))
    return _INTERVAL


def _install():
    try:
        _state["handler"] = bpy.types.SpaceView3D.draw_handler_add(
            _draw_cb, (), "WINDOW", "POST_PIXEL")
    except Exception as e:
        _emit("SOAK_NOHANDLER %s: %s" % (type(e).__name__, str(e)[:120]))
    bpy.app.timers.register(_tick, first_interval=1.0)
    _emit("SOAK_READY interval=%.2f hb_ticks=%d" % (_INTERVAL, _HB_TICKS))


_install()
