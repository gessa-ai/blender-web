#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bind rapid retained screenshots to a bounded post-queue liveness decision."""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PRODUCER = ROOT / "sandbox/p0-interaction-stress/rapid_freeze_repro.mjs"
DISPLAY_STATE = ROOT / "platform_web/ghost/GHOST_WebDisplayState.hh"
SYSTEM_HEADER = ROOT / "platform_web/ghost/GHOST_SystemWeb.hh"
SYSTEM_SOURCE = ROOT / "platform_web/ghost/GHOST_SystemWeb.cc"
WINDOW_SOURCE = ROOT / "platform_web/ghost/GHOST_WindowWeb.cc"
EVENT_BRIDGE = ROOT / "platform_web/ghost/GHOST_EventBridgeWeb.cc"
CONTEXT_SOURCE = ROOT / "platform_web/ghost/GHOST_ContextWGPUWeb.cc"


def require_once(source: str, token: str) -> None:
    if source.count(token) != 1:
        raise ValueError(f"expected exactly one {token!r}")


def validate(source: str) -> None:
    for token in (
        'const hardwareDiagnostic = process.env.BW_P0_RAPID_HARDWARE === "1";',
        'const sparseDiagnostic = process.env.BW_P0_SPARSE === "1";',
        'const sampleCadenceMs = sparseDiagnostic ? 650 : 350;',
        'hardwareDiagnostic && process.platform !== "darwin"',
        'const SOFTWARE_ADAPTER_TOKENS = Object.freeze([',
        'typeof info.isFallbackAdapter === "boolean"',
        'adapter.status !== "ACCEPTED"',
        'rapid input hardware adapter rejected: ${adapter.reason}',
        'const PY_MONITOR = String.raw`',
        'bl_idname="wm.bwp0r_input_probe"',
        '"P0R_INPUT "+json.dumps(payload',
        '"P0R_STATE "+json.dumps(state',
        'window.__BW_PYEXPR = monitor',
        'const inputMatch = /^P0R_INPUT',
        'const stateMatch = /^P0R_STATE',
        'native rapid-input monitor did not start',
        '"__bwP0RapidDomInputs"',
        'trusted: event.isTrusted === true',
        'const waitForActionDrain = async (',
        'const drainTimelines = Object.create(null);',
        'failureContext = {consoleLines, pageErrors, lifecycle, nativeInputs, nativeStates, drainTimelines};',
        'drainTimelines[name] = [];',
        'elapsedMs: Date.now() - started,',
        'drainTimelines[name].push({',
        'nativeDeliveryComplete, nativeStateComplete, timeoutMs = 12000,',
        'if (nativeStates.length === 0) throw new Error("native rapid-input monitor did not start");',
        "current.sha256 !== baseline",
        "current.ticks > counterBaseline.ticks",
        "current.presents > counterBaseline.presents",
        "current.retries > counterBaseline.retries",
        "current.inputRedraw.terminal > counterBaseline.inputRedraw.terminal",
        "current.inputRedraw.admitted >= current.inputRedraw.terminal",
        "current.inputRedraw.dispatched >= current.inputRedraw.terminal",
        "current.inputRedraw.presented >= current.inputRedraw.terminal",
        "current.inputRedraw.contentPresented >= current.inputRedraw.terminal",
        "current.inputRedraw.episode === counterBaseline.inputRedraw.episode",
        "nativeDeliveryComplete(current)",
        "ghostWindowSettled(current)",
        "(!hardwareDiagnostic || nativeStateComplete(current))",
        'operator === "WM_OT_bwp0r_input_probe"',
        'await page.waitForTimeout(sampleCadenceMs);',
        'const hardwareIsolatedOrbitStateComplete = (current, baseline) =>',
        'current.nativeState?.selected_count === baseline.nativeState?.selected_count',
        'if (sparseDiagnostic) {',
        '"isolated-orbit-drain",',
        'current, isolatedOrbitInputBaseline, {left: 0, middle: 1, keys: 0}',
        '(current) => hardwareIsolatedOrbitStateComplete(current, isolatedOrbitBaseline)',
        '"isolated-recovery-orbit",',
        'const isolatedRecoveryBaseline = await sample("isolated-recovery-baseline");',
        'current, isolatedRecoveryInputBaseline, {left: 0, middle: 1, keys: 0}',
        '(current) => hardwareIsolatedOrbitStateComplete(current, isolatedRecoveryBaseline)',
        'const orbitBeforeClick = steps.find((step) => step.name === "orbit-before-click");',
        'const ghostInputDeliveryComplete = (current, baseline, expected) =>',
        'current.ghostInput.leftPresses >= baseline.leftPresses + expected.left',
        'current.ghostInput.leftReleases >= baseline.leftReleases + expected.left',
        'current.ghostInput.middlePresses >= baseline.middlePresses + expected.middle',
        'current.ghostInput.middleReleases >= baseline.middleReleases + expected.middle',
        'current.ghostInput.keyPresses >= baseline.keyPresses + expected.keys',
        'current.ghostInput.keyReleases >= baseline.keyReleases + expected.keys',
        '(current.ghostInput.heldMask & 0x3) === 0',
        'nativeState: nativeState ? {...nativeState} : null,',
        'const stateArraysEqual = (left, right) =>',
        'const stateArrayChanged = (left, right) => !stateArraysEqual(left, right);',
        'const hardwareActionStateComplete = (current, baseline) =>',
        'current.nativeState?.active_object === "Cube"',
        'current.nativeState?.selected_count === 1',
        'stateArrayChanged(current.nativeState?.view_rotation, baseline.nativeState?.view_rotation)',
        'stateArrayChanged(current.nativeState?.location, baseline.nativeState?.location)',
        'const hardwareRecoveryStateComplete = (current, baseline) =>',
        'stateArraysEqual(current.nativeState?.location, baseline.nativeState?.location)',
        'const rapidInputBaseline = steps.at(-1).ghostInput;',
        'const drainTimeoutMs = hardwareDiagnostic ? 12000 : 30000;',
        'current, rapidInputBaseline, {left: 2, middle: 2, keys: 1}',
        '(current) => hardwareActionStateComplete(current, orbitBeforeClick)',
        'current, recoveryInputBaseline, {left: 0, middle: 1, keys: 0}',
        'const recoveryBaseline = await sample("recovery-baseline");',
        '(current) => hardwareRecoveryStateComplete(current, recoveryBaseline)',
        'let actionDrain;',
        '"action-drain",\n      orbitBeforeClick.sha256,\n      orbitBeforeClick,',
        '"recovery-orbit",\n      recoveryBaseline.sha256,\n      recoveryBaseline,',
        "retainedActionFramesEqual,",
        "failureContext.lastSample = result",
        "steps: failureContext?.steps || []",
        "lastSample: failureContext?.lastSample || null",
        "nativeInputs: failureContext?.nativeInputs || []",
        "nativeStates: failureContext?.nativeStates || []",
        "retained.length === 5 ? new Set(retained).size === 1 : null",
        "eventTail: (failureContext?.consoleLines || [])",
        "inputRedrawLines: (failureContext?.consoleLines || [])",
        "actionDrainMs: actionDrain.settleMs",
        "recoveryOrbitMs: recoveryOrbit.settleMs",
        'schema: 1,\n    mode: sparseDiagnostic ? "slow-sparse" : "rapid-burst"',
        "drainTimelines,",
        "nativeStateContract,",
        "actionComplete: hardwareActionStateComplete(actionDrain, orbitBeforeClick)",
        "recoveryComplete: hardwareRecoveryStateComplete(recoveryOrbit, recoveryBaseline)",
        "if (pageErrors.length !== 0 || lifecycle.length !== 0)",
    ):
        require_once(source, token)
    if source.index("current.sha256 !== baseline") > source.index("return {...current"):
        raise ValueError("pixel and counter liveness is checked after accepting the sample")
    if source.index('"action-drain",\n      orbitBeforeClick.sha256') > source.index(
        '"recovery-orbit",\n      recoveryBaseline.sha256'
    ):
        raise ValueError("recovery orbit precedes queued-action drain")
    if "steps.slice(steps.indexOf(orbitBeforeClick) + 1).find" in source:
        raise ValueError("an intermediate action can still satisfy the terminal drain")
    if "retainedActionFramesEqual" not in source or "throw new Error" not in source:
        raise ValueError("producer lost diagnostic retained-frame reporting or fail-closed outcome")


def validate_delivery_sources(
    source: str,
    display: str,
    system_header: str,
    system_source: str,
    event_bridge: str,
    context_source: str,
) -> None:
    for token in (
        "input_button_press_counters[button].fetch_add(1u, std::memory_order_relaxed);",
        "input_button_release_counters[button].fetch_add(1u, std::memory_order_relaxed);",
        "input_button_mask.fetch_or(bit, std::memory_order_release);",
        "input_button_mask.fetch_and(~bit, std::memory_order_release);",
        "input_key_press_counter : input_key_release_counter",
        "input_button_mask.load(std::memory_order_acquire)",
        "input_cursor_counter.fetch_add(1u, std::memory_order_relaxed);",
        "input_button_wm_press_counters[button].fetch_add(1u, std::memory_order_relaxed);",
        "input_button_wm_release_counters[button].fetch_add(1u, std::memory_order_relaxed);",
        "input_button_wm_mask.fetch_or(bit, std::memory_order_release);",
        "input_button_wm_mask.fetch_and(~bit, std::memory_order_release);",
        "input_key_wm_press_counter : input_key_wm_release_counter",
        "input_button_wm_mask.load(std::memory_order_acquire)",
        "input_cursor_wm_counter.fetch_add(1u, std::memory_order_relaxed);",
        "inline std::atomic<uint64_t> input_redraw_terminal_generation{0};",
        "inline std::atomic<uint64_t> input_redraw_admitted_generation{0};",
        "inline std::atomic<uint64_t> input_redraw_dispatched_generation{0};",
        "inline std::atomic<uint64_t> input_redraw_presented_generation{0};",
        "inline std::atomic<uint64_t> input_redraw_content_presented_generation{0};",
        "class InputRedrawFrameProvenance {",
        "void begin(const uint64_t dispatched_generation)",
        "frame_generation_ = dispatched_generation;",
        "uint64_t generation_for_present(const uint64_t completed_frame_generation) const",
        "return completed_frame_generation != 0u ? completed_frame_generation : frame_generation_;",
        "uint64_t input_redraw_generation = 0;",
        "redraw_trace_state.input_redraw_generation =\n"
        "      input_redraw_dispatched_generation.load(std::memory_order_acquire);",
        "inline uint64_t request_input_redraw_retry()",
        "return input_generation;",
        "inline void note_input_redraw_terminal(const uint64_t input_generation)",
        "input_redraw_terminal_generation.store(input_generation, std::memory_order_release);",
        "inline void note_input_redraw_admitted(const uint64_t input_generation)",
        "input_redraw_admitted_generation.store(input_generation, std::memory_order_release);",
        "inline uint64_t input_redraw_terminal_count()",
        "inline uint64_t input_redraw_admitted_count()",
        "inline bool note_input_redraw_dispatched(const uint64_t input_generation)",
        "input_redraw_dispatched_generation.compare_exchange_weak(",
        "inline uint64_t input_redraw_dispatched_count()",
        "inline bool note_input_redraw_presented(const uint64_t input_generation)",
        "input_redraw_presented_generation.compare_exchange_weak(",
        "inline uint64_t input_redraw_presented_count()",
        "inline void input_redraw_trace_frame_begin(",
        "inline bool input_redraw_trace_capturing()",
        "inline void input_redraw_trace_note(",
        "inline RedrawTraceSnapshot input_redraw_trace_snapshot()",
        "inline bool input_redraw_content_trace_complete(",
        "inline uint32_t input_redraw_content_trace_stage_mask(",
        "inline bool note_input_redraw_content_presented(",
        "return input_redraw_content_trace_stage_mask(trace, input_generation) == 0x3fu;",
        "input_redraw_content_presented_generation.compare_exchange_weak(",
        "inline uint64_t input_redraw_content_presented_count()",
    ):
        require_once(display, token)
    require_once(
        system_header,
        "/** Update one tracked button and publish a diagnostic edge only on a real state transition. */",
    )
    require_once(
        system_header,
        "void requestInputRedrawRetry(const char *terminal_kind = nullptr,",
    )
    require_once(
        system_header,
        "bool input_redraw_dispatch_consumer_registration_attempted_ = false;",
    )
    require_once(
        system_header,
        "bool input_redraw_dispatch_consumer_registered_ = false;",
    )
    for token in (
        "const bool was_down = buttons_.get(button);",
        "buttons_.set(button, down);",
        "if (was_down != down)",
        "ghost_web::note_input_button(uint32_t(button), down);",
        "const uint64_t episode_before = ghost_web::redraw_episode_generation();",
        "const uint64_t input_generation = ghost_web::request_input_redraw_retry();",
        "const uint64_t episode_after = ghost_web::redraw_episode_generation();",
        "ghost_web::note_input_redraw_terminal(input_generation);",
        '"[bw] GHOST-input-redraw terminal kind=%s code=%u input=%llu "',
        "const bool input_redraw_pending_admission =",
        "ghost_web::input_redraw_admitted_count();",
        "ghost_web::note_input_redraw_admitted(input_redraw_generation);",
        '"[bw] GHOST-input-redraw admitted input=%llu terminal=%llu "',
        '"[bw] GHOST-input-redraw withheld input=%llu terminal=%llu "',
        "class GHOST_EventWindowUpdateWeb final : public GHOST_Event",
        "class GHOST_InputRedrawDispatchConsumer final : public GHOST_IEventConsumer",
        "ghost_web::note_input_redraw_dispatched(payload->input_redraw_generation)",
        "ghost_web::note_input_button_wm_dispatch(",
        "ghost_web::note_input_key_wm_dispatch(",
        "ghost_web::note_input_cursor_wm_dispatch();",
        '"[bw] GHOST-input-event WM-queued type=%d button=%d "',
        '"[bw] GHOST-input-redraw dispatched input=%llu terminal=%llu "',
        "if (!input_redraw_dispatch_consumer_registration_attempted_)",
        "input_redraw_dispatch_consumer_registration_attempted_ = true;",
        "input_redraw_dispatch_consumer_registered_ = true;",
        "std::make_unique<GHOST_EventWindowUpdateWeb>(",
        "input_redraw_pending_admission ? input_redraw_generation : 0u",
    ):
        require_once(system_source, token)
    require_once(event_bridge, "ghost_web::note_input_key(down);")
    require_once(event_bridge, "ghost_web::note_input_cursor();")
    require_once(
        event_bridge,
        'sys.requestInputRedrawRetry(down ? nullptr : "button-up", uint32_t(button));',
    )
    require_once(
        event_bridge,
        'sys.requestInputRedrawRetry(down ? nullptr : "key-up", uint32_t(key));',
    )
    for token in (
        "bw_input_button_press_count(const uint32_t button)",
        "bw_input_button_release_count(const uint32_t button)",
        "bw_input_key_press_count(void)",
        "bw_input_key_release_count(void)",
        "bw_input_button_mask(void)",
        "bw_input_cursor_count(void)",
        "bw_input_button_wm_press_count(const uint32_t button)",
        "bw_input_button_wm_release_count(const uint32_t button)",
        "bw_input_key_wm_press_count(void)",
        "bw_input_key_wm_release_count(void)",
        "bw_input_button_wm_mask(void)",
        "bw_input_cursor_wm_count(void)",
        "bw_input_redraw_retry_count(void)",
        "bw_input_redraw_terminal_count(void)",
        "bw_input_redraw_admitted_count(void)",
        "bw_input_redraw_dispatched_count(void)",
        "bw_input_redraw_presented_count(void)",
        "bw_input_redraw_content_presented_count(void)",
        "return double(ghost_web::input_button_press_count(button));",
        "return double(ghost_web::input_button_release_count(button));",
        "return double(ghost_web::input_key_press_count());",
        "return double(ghost_web::input_key_release_count());",
        "return double(ghost_web::input_buttons_held_mask());",
        "return double(ghost_web::input_cursor_count());",
        "return double(ghost_web::input_button_wm_press_count(button));",
        "return double(ghost_web::input_button_wm_release_count(button));",
        "return double(ghost_web::input_key_wm_press_count());",
        "return double(ghost_web::input_key_wm_release_count());",
        "return double(ghost_web::input_buttons_wm_held_mask());",
        "return double(ghost_web::input_cursor_wm_count());",
        "return double(ghost_web::input_redraw_retry_generation());",
        "return double(ghost_web::input_redraw_terminal_count());",
        "return double(ghost_web::input_redraw_admitted_count());",
        "return double(ghost_web::input_redraw_dispatched_count());",
        "return double(ghost_web::input_redraw_presented_count());",
        "return double(ghost_web::input_redraw_content_presented_count());",
        "input_redraw_frame_provenance_.begin(ghost_web::input_redraw_dispatched_count());",
        "const uint64_t input_redraw_frame_generation =",
        "input_redraw_frame_provenance_.generation_for_present(",
        "barrier_redraw_trace.input_redraw_generation",
        "const ghost_web::RedrawTraceSnapshot input_redraw_trace =",
        "input_redraw_trace.input_redraw_generation == input_redraw_frame_generation",
        "ghost_web::note_input_redraw_presented(input_redraw_frame_generation)",
        "ghost_web::note_input_redraw_content_presented(",
        '"[bw] GHOST-input-redraw presented input=%llu terminal=%llu "',
        '"[bw] GHOST-input-redraw content input=%llu terminal=%llu "',
        '"[bw] GHOST-input-redraw content-miss input=%llu terminal=%llu "',
        '"trace=%llu available=%d stages=0x%02x "',
        '"draws=%llu offscreen=%llu window=%llu "',
        '"background=%llu/%d grid=%llu/%d display=%llu/%d last=%llu/%d "',
        '"frame-bound=1 present=%llu\\n"',
    ):
        require_once(context_source, token)
    if source.count('readArg("_bw_input_button_press_count"') != 2:
        raise ValueError("producer must sample left and middle GHOST press counters")
    if source.count('readArg("_bw_input_button_release_count"') != 2:
        raise ValueError("producer must sample left and middle GHOST release counters")
    if source.count("wmInputDeliveryComplete(") != 4:
        raise ValueError("producer must enforce WM-queue delivery for all four drains")
    for token in (
        'keyPresses: read("_bw_input_key_press_count")',
        'keyReleases: read("_bw_input_key_release_count")',
        'heldMask: read("_bw_input_button_mask")',
        'published: read("_bw_input_redraw_retry_count")',
        'terminal: read("_bw_input_redraw_terminal_count")',
        'admitted: read("_bw_input_redraw_admitted_count")',
        'dispatched: read("_bw_input_redraw_dispatched_count")',
        'presented: read("_bw_input_redraw_presented_count")',
        'contentPresented: read("_bw_input_redraw_content_presented_count")',
        'episode: read("_bw_redraw_episode_count")',
        'cursorMoves: read("_bw_input_cursor_count")',
        'wmLeftPresses: readArg("_bw_input_button_wm_press_count", 0)',
        'wmLeftReleases: readArg("_bw_input_button_wm_release_count", 0)',
        'wmMiddlePresses: readArg("_bw_input_button_wm_press_count", 1)',
        'wmMiddleReleases: readArg("_bw_input_button_wm_release_count", 1)',
        'wmKeyPresses: read("_bw_input_key_wm_press_count")',
        'wmKeyReleases: read("_bw_input_key_wm_release_count")',
        'wmHeldMask: read("_bw_input_button_wm_mask")',
        'wmCursorMoves: read("_bw_input_cursor_wm_count")',
        'wmInput: {...current.wmInput}',
        'const wmInputDeliveryComplete = (current, baseline, expected) =>',
    ):
        require_once(source, token)


def validate_worker_state_sources(
    source: str,
    display: str,
    system_source: str,
    window_source: str,
) -> None:
    """Bind sparse failures to the WM worker's focus and cursor-grab ownership."""
    for token in (
        'browserFocusActive: read("_bw_browser_focus_active")',
        'pointerLockState: read("_bw_pointer_lock_state")',
        'pointerLockRequestedMode: read("_bw_pointer_lock_requested_mode")',
        'cursorGrabMode: read("_bw_cursor_grab_mode")',
        'ghostWindow: {...current.ghostWindow},',
        'const ghostWindowSettled = (current) =>',
        'current.ghostWindow.browserFocusActive === 1',
        'current.ghostWindow.pointerLockState === 0',
        'current.ghostWindow.pointerLockRequestedMode === 0',
        'current.ghostWindow.cursorGrabMode === 0',
    ):
        require_once(source, token)
    for token in (
        "inline std::atomic<int32_t> browser_focus_active_state{-1};",
        "inline std::atomic<int32_t> pointer_lock_state{-1};",
        "inline std::atomic<int32_t> pointer_lock_requested_mode{-1};",
        "inline std::atomic<int32_t> cursor_grab_mode{-1};",
        "inline void publish_browser_focus_active(const bool active)",
        "inline void publish_cursor_grab_state(",
        "cursor_grab_mode.store(effective_mode, std::memory_order_release);",
        "inline int32_t browser_focus_active()",
        "inline int32_t pointer_lock_state_value()",
        "inline int32_t pointer_lock_requested_mode_value()",
        "inline int32_t cursor_grab_mode_value()",
    ):
        require_once(display, token)
    for token in (
        "bw_browser_focus_active(void)",
        "bw_pointer_lock_state(void)",
        "bw_pointer_lock_requested_mode(void)",
        "bw_cursor_grab_mode(void)",
        "return double(ghost_web::browser_focus_active());",
        "return double(ghost_web::pointer_lock_state_value());",
        "return double(ghost_web::pointer_lock_requested_mode_value());",
        "return double(ghost_web::cursor_grab_mode_value());",
    ):
        require_once(system_source, token)
    if system_source.count(
        "ghost_web::publish_browser_focus_active(browser_focus_active_);"
    ) != 3:
        raise ValueError("browser focus publication must cover seed, transition, and retirement")
    for token in (
        "void GHOST_WindowWeb::publishCursorGrabDiagnostic() const",
        "ghost_web::publish_cursor_grab_state(",
        "publishCursorGrabDiagnostic();",
    ):
        if token not in window_source:
            raise ValueError(f"missing WM cursor-grab diagnostic boundary {token!r}")


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"mutation input count differs for {old!r}")
    return source.replace(old, new, 1)


def self_check(
    source: str,
    display: str,
    system_header: str,
    system_source: str,
    window_source: str,
    event_bridge: str,
    context_source: str,
) -> None:
    validate(source)
    validate_delivery_sources(
        source, display, system_header, system_source, event_bridge, context_source
    )
    validate_worker_state_sources(source, display, system_source, window_source)
    mutations = (
        replace_once(source, 'timeoutMs = 12000', 'timeoutMs = 120000'),
        replace_once(source, "current.sha256 !== baseline", "current.sha256 === baseline"),
        replace_once(
            source,
            "current.ticks > counterBaseline.ticks",
            "current.ticks >= counterBaseline.ticks",
        ),
        replace_once(
            source,
            "current.presents > counterBaseline.presents",
            "current.presents >= counterBaseline.presents",
        ),
        replace_once(
            source,
            "current.retries > counterBaseline.retries",
            "current.retries >= counterBaseline.retries",
        ),
        replace_once(
            source,
            "current.inputRedraw.terminal > counterBaseline.inputRedraw.terminal",
            "current.inputRedraw.terminal >= counterBaseline.inputRedraw.terminal",
        ),
        replace_once(
            source,
            "current.inputRedraw.admitted >= current.inputRedraw.terminal",
            "current.inputRedraw.admitted < current.inputRedraw.terminal",
        ),
        replace_once(
            source,
            "current.inputRedraw.dispatched >= current.inputRedraw.terminal",
            "current.inputRedraw.dispatched < current.inputRedraw.terminal",
        ),
        replace_once(
            source,
            "current.inputRedraw.presented >= current.inputRedraw.terminal",
            "current.inputRedraw.presented < current.inputRedraw.terminal",
        ),
        replace_once(
            source,
            "current.inputRedraw.contentPresented >= current.inputRedraw.terminal",
            "current.inputRedraw.contentPresented < current.inputRedraw.terminal",
        ),
        replace_once(
            source,
            "current.inputRedraw.episode === counterBaseline.inputRedraw.episode",
            "current.inputRedraw.episode !== counterBaseline.inputRedraw.episode",
        ),
        replace_once(source, "nativeDeliveryComplete(current)", "true"),
        replace_once(source, "ghostWindowSettled(current)", "true"),
        replace_once(
            source,
            "(!hardwareDiagnostic || nativeStateComplete(current))",
            "true",
        ),
        replace_once(
            source,
            'operator === "WM_OT_bwp0r_input_probe"',
            'operator !== "WM_OT_bwp0r_input_probe"',
        ),
        replace_once(
            source,
            "const sampleCadenceMs = sparseDiagnostic ? 650 : 350;",
            "const sampleCadenceMs = sparseDiagnostic ? 0 : 350;",
        ),
        replace_once(
            source,
            '"isolated-orbit-drain",',
            '"isolated-orbit-skipped",',
        ),
        replace_once(
            source,
            "current.nativeState?.selected_count === baseline.nativeState?.selected_count",
            "true",
        ),
        replace_once(
            source,
            'current, rapidInputBaseline, {left: 2, middle: 2, keys: 1}',
            'current, rapidInputBaseline, {left: 2, middle: 1, keys: 1}',
        ),
        replace_once(
            source,
            'current, recoveryInputBaseline, {left: 0, middle: 1, keys: 0}',
            'current, recoveryInputBaseline, {left: 0, middle: 0, keys: 0}',
        ),
        replace_once(
            source,
            "current.ghostInput.keyPresses >= baseline.keyPresses + expected.keys",
            "current.ghostInput.keyPresses >= baseline.keyPresses",
        ),
        replace_once(
            source,
            "(current.ghostInput.heldMask & 0x3) === 0",
            "true",
        ),
        replace_once(
            source,
            'current.nativeState?.active_object === "Cube"',
            "true",
        ),
        replace_once(
            source,
            "current.nativeState?.selected_count === 1",
            "true",
        ),
        replace_once(
            source,
            "stateArrayChanged(current.nativeState?.location, baseline.nativeState?.location)",
            "true",
        ),
        replace_once(
            source,
            "stateArraysEqual(current.nativeState?.location, baseline.nativeState?.location)",
            "true",
        ),
        replace_once(
            source,
            "const drainTimeoutMs = hardwareDiagnostic ? 12000 : 30000;",
            "const drainTimeoutMs = 30000;",
        ),
        replace_once(
            source,
            '"action-drain",\n      orbitBeforeClick.sha256,\n      orbitBeforeClick,',
            '"action-drain",\n      steps.at(-1).sha256,\n      steps.at(-1),',
        ),
        replace_once(
            source,
            '"recovery-orbit",\n      recoveryBaseline.sha256,\n      recoveryBaseline,',
            '"recovery-orbit",\n      orbitBeforeClick.sha256,\n      orbitBeforeClick,',
        ),
        replace_once(
            source,
            "if (pageErrors.length !== 0 || lifecycle.length !== 0)",
            "if (pageErrors.length !== 0 && lifecycle.length !== 0)",
        ),
        replace_once(
            source,
            'hardwareDiagnostic && process.platform !== "darwin"',
            'hardwareDiagnostic && process.platform === "darwin"',
        ),
        replace_once(
            source,
            'adapter.status !== "ACCEPTED"',
            'adapter.status === "ACCEPTED"',
        ),
        replace_once(
            source,
            "steps: failureContext?.steps || []",
            "steps: [],",
        ),
        replace_once(
            source,
            "lastSample: failureContext?.lastSample || null",
            "lastSample: null",
        ),
        replace_once(
            source,
            "nativeInputs: failureContext?.nativeInputs || []",
            "nativeInputs: [],",
        ),
        replace_once(
            source,
            "nativeStates: failureContext?.nativeStates || []",
            "nativeStates: [],",
        ),
        replace_once(source, "trusted: event.isTrusted === true", "trusted: true"),
        replace_once(
            source,
            'if (nativeStates.length === 0) throw new Error("native rapid-input monitor did not start");',
            'if (false) throw new Error("native rapid-input monitor did not start");',
        ),
    )
    rejected = 0
    for mutation in mutations:
        try:
            validate(mutation)
        except ValueError:
            rejected += 1
    if rejected != len(mutations):
        raise ValueError(f"mutation self-check rejected {rejected}/{len(mutations)}")

    delivery_mutations = (
        (source, replace_once(
            display,
            "input_button_mask.fetch_and(~bit, std::memory_order_release);",
            "input_button_mask.fetch_or(bit, std::memory_order_release);",
        ), system_header, system_source, event_bridge, context_source),
        (source, display, system_header, replace_once(
            system_source, "if (was_down != down)", "if (true)"
        ), event_bridge, context_source),
        (source, display, system_header, system_source, replace_once(
            event_bridge, "ghost_web::note_input_key(down);", ""
        ), context_source),
        (source, display, system_header, system_source, event_bridge, replace_once(
            context_source,
            "return double(ghost_web::input_button_release_count(button));",
            "return double(ghost_web::input_button_press_count(button));",
        )),
        (source, replace_once(
            display,
            "input_redraw_admitted_generation.store(input_generation, std::memory_order_release);",
            "",
        ), system_header, system_source, event_bridge, context_source),
        (source, display, system_header, replace_once(
            system_source,
            "ghost_web::note_input_redraw_admitted(input_redraw_generation);",
            "",
        ), event_bridge, context_source),
        (source, display, system_header, system_source, replace_once(
            event_bridge,
            'sys.requestInputRedrawRetry(down ? nullptr : "button-up", uint32_t(button));',
            "sys.requestInputRedrawRetry();",
        ), context_source),
        (source, display, system_header, system_source, event_bridge, replace_once(
            context_source,
            "return double(ghost_web::input_redraw_admitted_count());",
            "return double(ghost_web::input_redraw_terminal_count());",
        )),
        (source, replace_once(
            display,
            "input_redraw_dispatched_generation.compare_exchange_weak(",
            "input_redraw_dispatched_generation.compare_exchange_strong(",
        ), system_header, system_source, event_bridge, context_source),
        (source, display, system_header, replace_once(
            system_source,
            "ghost_web::note_input_redraw_dispatched(payload->input_redraw_generation)",
            "false",
        ), event_bridge, context_source),
        (source, display, system_header, replace_once(
            system_source,
            "input_redraw_pending_admission ? input_redraw_generation : 0u",
            "0u",
        ), event_bridge, context_source),
        (source, display, system_header, system_source, event_bridge, replace_once(
            context_source,
            "return double(ghost_web::input_redraw_dispatched_count());",
            "return double(ghost_web::input_redraw_admitted_count());",
        )),
        (source, replace_once(
            display,
            "input_redraw_presented_generation.compare_exchange_weak(",
            "",
        ), system_header, system_source, event_bridge, context_source),
        (source, display, system_header, system_source, event_bridge, replace_once(
            context_source,
            "ghost_web::note_input_redraw_presented(input_redraw_frame_generation)",
            "false",
        )),
        (source, display, system_header, system_source, event_bridge, replace_once(
            context_source,
            "return double(ghost_web::input_redraw_presented_count());",
            "return double(ghost_web::input_redraw_admitted_count());",
        )),
        (source, display, system_header, system_source, event_bridge, replace_once(
            context_source,
            "input_redraw_frame_provenance_.begin(ghost_web::input_redraw_dispatched_count());",
            "input_redraw_frame_provenance_.begin(0u);",
        )),
        (source, display, system_header, system_source, event_bridge, replace_once(
            context_source,
            "barrier_redraw_trace.input_redraw_generation",
            "0u",
        )),
        (source, replace_once(
            display,
            "return completed_frame_generation != 0u ? completed_frame_generation : frame_generation_;",
            "return input_redraw_dispatched_generation.load(std::memory_order_acquire);",
        ), system_header, system_source, event_bridge, context_source),
        (source, replace_once(
            display,
            "input_redraw_content_presented_generation.compare_exchange_weak(",
            "input_redraw_content_presented_generation.compare_exchange_strong(",
        ), system_header, system_source, event_bridge, context_source),
        (source, display, system_header, system_source, event_bridge, replace_once(
            context_source,
            "ghost_web::note_input_redraw_content_presented(",
            "ghost_web::input_redraw_content_trace_complete(",
        )),
        (source, display, system_header, system_source, event_bridge, replace_once(
            context_source,
            "return double(ghost_web::input_redraw_content_presented_count());",
            "return double(ghost_web::input_redraw_presented_count());",
        )),
        (source, display, system_header, system_source, event_bridge, replace_once(
            context_source,
            "input_redraw_trace.input_redraw_generation == input_redraw_frame_generation",
            "input_redraw_trace.input_redraw_generation != input_redraw_frame_generation",
        )),
        (source, replace_once(
            display,
            "return input_redraw_content_trace_stage_mask(trace, input_generation) == 0x3fu;",
            "return input_redraw_content_trace_stage_mask(trace, input_generation) != 0x3fu;",
        ), system_header, system_source, event_bridge, context_source),
        (source, display, system_header, system_source, event_bridge, replace_once(
            context_source,
            '"[bw] GHOST-input-redraw content-miss input=%llu terminal=%llu "',
            '"[bw] GHOST-input-redraw content-unknown input=%llu terminal=%llu "',
        )),
        (source, replace_once(
            display,
            "input_button_wm_mask.fetch_and(~bit, std::memory_order_release);",
            "input_button_wm_mask.fetch_or(bit, std::memory_order_release);",
        ), system_header, system_source, event_bridge, context_source),
        (source, display, system_header, replace_once(
            system_source,
            "ghost_web::note_input_button_wm_dispatch(",
            "ghost_web::note_input_button(",
        ), event_bridge, context_source),
        (source, display, system_header, system_source, replace_once(
            event_bridge,
            "ghost_web::note_input_cursor();",
            "",
        ), context_source),
        (source, display, system_header, system_source, event_bridge, replace_once(
            context_source,
            "return double(ghost_web::input_button_wm_release_count(button));",
            "return double(ghost_web::input_button_release_count(button));",
        )),
        (replace_once(
            source,
            'wmMiddleReleases: readArg("_bw_input_button_wm_release_count", 1)',
            'wmMiddleReleases: readArg("_bw_input_button_wm_press_count", 1)',
        ), display, system_header, system_source, event_bridge, context_source),
        (replace_once(
            source,
            "const wmInputDeliveryComplete = (current, baseline, expected) =>",
            "const wmInputDeliveryIgnored = (current, baseline, expected) =>",
        ), display, system_header, system_source, event_bridge, context_source),
    )
    delivery_rejected = 0
    delivery_survivors = []
    for index, mutation in enumerate(delivery_mutations):
        try:
            validate_delivery_sources(*mutation)
        except ValueError:
            delivery_rejected += 1
        else:
            delivery_survivors.append(index)
    if delivery_rejected != len(delivery_mutations):
        raise ValueError(
            f"delivery mutation self-check rejected {delivery_rejected}/{len(delivery_mutations)} "
            f"survivors={delivery_survivors}"
        )

    worker_state_mutations = (
        (replace_once(
            source,
            'pointerLockState: read("_bw_pointer_lock_state")',
            'pointerLockState: null',
        ), display, system_source, window_source),
        (source, replace_once(
            display,
            "cursor_grab_mode.store(effective_mode, std::memory_order_release);",
            "cursor_grab_mode.store(requested_mode, std::memory_order_release);",
        ), system_source, window_source),
        (source, display, replace_once(
            system_source,
            "return double(ghost_web::browser_focus_active());",
            "return -1.0;",
        ), window_source),
        (source, display, system_source, replace_once(
            window_source,
            "ghost_web::publish_cursor_grab_state(",
            "ghost_web::publish_cursor_grab_state_disabled(",
        )),
    )
    worker_state_rejected = 0
    for mutation in worker_state_mutations:
        try:
            validate_worker_state_sources(*mutation)
        except ValueError:
            worker_state_rejected += 1
    if worker_state_rejected != len(worker_state_mutations):
        raise ValueError(
            "worker-state mutation self-check rejected "
            f"{worker_state_rejected}/{len(worker_state_mutations)}"
        )
    print(
        "P0J_RAPID_INPUT_DRAIN_SELFCHECK_PASS "
        f"mutations={rejected + delivery_rejected + worker_state_rejected} "
        f"delivery={delivery_rejected} worker_state={worker_state_rejected}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    source = PRODUCER.read_text(encoding="utf-8")
    display = DISPLAY_STATE.read_text(encoding="utf-8")
    system_header = SYSTEM_HEADER.read_text(encoding="utf-8")
    system_source = SYSTEM_SOURCE.read_text(encoding="utf-8")
    window_source = WINDOW_SOURCE.read_text(encoding="utf-8")
    event_bridge = EVENT_BRIDGE.read_text(encoding="utf-8")
    context_source = CONTEXT_SOURCE.read_text(encoding="utf-8")
    if args.self_check:
        self_check(
            source,
            display,
            system_header,
            system_source,
            window_source,
            event_bridge,
            context_source,
        )
    else:
        validate(source)
        validate_delivery_sources(
            source, display, system_header, system_source, event_bridge, context_source
        )
        validate_worker_state_sources(source, display, system_source, window_source)
        print(
            "P0J_RAPID_INPUT_DRAIN_SOURCE_PASS "
            "bound_ms=12000 counters=wm,present,retry,ghost-input,focus,grab"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(f"P0J_RAPID_INPUT_DRAIN_SOURCE_FAIL {error}")
        raise SystemExit(1)
