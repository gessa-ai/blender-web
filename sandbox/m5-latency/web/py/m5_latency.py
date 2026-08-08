# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
#
# M5 latency-budget probe sessions (the input half of the measurement).
#
# Each session is an event-simulate generator (upstream ui_simulate DSL) that:
#   1. Calibrates the CLOG wall-clock epoch: it brackets several DIRECT
#      bpy.ops.ed.undo_push() calls with time.time() and emits M5LAT_CAL. The
#      driver pairs each with that op's `--log operator` "Started" line (whose
#      CLOG timestamp is gettimeofday-ms since a tick_start set at init, see
#      upstream/intern/clog/clog.cc write_timestamp) to solve tick_start to
#      sub-ms, so every later operator "Started" line converts to epoch seconds.
#   2. Fires N repeated keypresses that each provably change on-canvas pixels,
#      emitting M5LAT_DISPATCH i <label> <time.time()> immediately BEFORE the
#      event_simulate() call (the honest "input arrival" instant, epoch seconds).
#
# All three timestamps used downstream (dispatch, operator-start, present) live
# on ONE wall clock: Python time.time() == CLOG gettimeofday == CDP screencast
# metadata.timestamp (Network.TimeSinceEpoch). No monotonic bridging.
#
# HAZARD respected: no bpy screenshot / render / GPU-readback op is called (those
# stall the windowed WM worker, deferral gpu-sync-readback-windowed). The visible
# half is captured entirely browser-side by the driver via CDP screencast.

import os
import time
import datetime

import modules.ui_test_utils as ui

# Overridden by latency_runner from argv before the generator is created.
N = 32
SPACING = 0.6
CAL = 5


def _emit(*parts):
    try:
        os.write(2, (" ".join(str(p) for p in parts) + "\n").encode("utf-8"))
    except Exception:
        pass


def _v3d_center(window):
    area = ui.get_window_area_by_type(window, 'VIEW_3D')
    return ui.get_area_center(area)


def _run(window, e, taps):
    import bpy
    # --- Calibrate CLOG tick_start via bracketed direct operator calls. ---
    for k in range(CAL):
        t0 = time.time()
        try:
            bpy.ops.ed.undo_push(message="m5lat-cal-%d" % k)
        except Exception as exc:
            _emit("M5LAT_CAL_ERR", k, repr(exc))
        t1 = time.time()
        _emit("M5LAT_CAL", k, "%.6f" % t0, "%.6f" % t1)
        yield datetime.timedelta(seconds=0.15)

    _emit("M5LAT_PROBE_BEGIN", N, "%.3f" % SPACING, len(taps))
    for i in range(N):
        label, tap = taps[i % len(taps)]
        # Dispatch marker FIRST (input-arrival instant), then inject the event.
        _emit("M5LAT_DISPATCH", i, label, "%.6f" % time.time())
        try:
            tap(e)
        except Exception as exc:
            _emit("M5LAT_TAP_ERR", i, repr(exc))
        yield datetime.timedelta(seconds=SPACING)
    _emit("M5LAT_DONE", N)


# --- Probe variants (selectable by ?session=m5_latency.<name>) ---------------

def tab():
    """Tab edit-mode toggle: object.editmode_toggle; edit-mesh overlay appears."""
    e, t, window = ui.test_window()
    e.cursor_position_set(*_v3d_center(window), move=True)
    yield
    yield from _run(window, e, [
        ("tab_in", lambda e: e.tab.tap()),
        ("tab_out", lambda e: e.tab.tap()),
    ])


def nkey():
    """N sidebar toggle: wm.context_toggle; the whole N-panel region appears."""
    e, t, window = ui.test_window()
    e.cursor_position_set(*_v3d_center(window), move=True)
    yield
    yield from _run(window, e, [
        ("n_show", lambda e: e.n.tap()),
        ("n_hide", lambda e: e.n.tap()),
    ])


def selall():
    """Select-all toggle: object.select_all; the selection outline flips."""
    e, t, window = ui.test_window()
    e.cursor_position_set(*_v3d_center(window), move=True)
    yield
    yield from _run(window, e, [
        ("deselect", lambda e: e.alt.a.tap()),
        ("select", lambda e: e.a.tap()),
    ])
