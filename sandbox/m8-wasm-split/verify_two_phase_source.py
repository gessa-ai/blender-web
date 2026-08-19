#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fail-closed static verifier for the two-phase web scheduler source seam."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
UPSTREAM = REPO / "upstream/source/blender"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(source: str, needle: str, label: str) -> int:
    count = source.count(needle)
    if count != 1:
        raise RuntimeError(f"{label}: expected one occurrence, found {count}")
    return source.index(needle)


def ordered(source: str, needles: list[tuple[str, str]]) -> None:
    positions = [(require(source, needle, label), label) for needle, label in needles]
    if positions != sorted(positions):
        raise RuntimeError(f"ordering failed: {positions}")


def main() -> int:
    paths = {
        "task_api": UPSTREAM / "blenlib/BLI_task.h",
        "scheduler": UPSTREAM / "blenlib/intern/task_scheduler.cc",
        "threads": UPSTREAM / "blenlib/intern/threads.cc",
        "task_pool": UPSTREAM / "blenlib/intern/task_pool.cc",
        "task_tests": UPSTREAM / "blenlib/tests/BLI_task_test.cc",
        "blenlib_cmake": UPSTREAM / "blenlib/CMakeLists.txt",
        "wm": UPSTREAM / "windowmanager/intern/wm.cc",
        "wm_protocol": UPSTREAM / "windowmanager/intern/wm_web_split_protocol.hh",
        "wm_protocol_tests": UPSTREAM / "windowmanager/intern/wm_web_split_protocol_test.cc",
        "wm_cmake": UPSTREAM / "windowmanager/CMakeLists.txt",
        "imb_api": UPSTREAM / "imbuf/IMB_imbuf.hh",
        "imb_module": UPSTREAM / "imbuf/intern/module.cc",
        "imb_policy": UPSTREAM / "imbuf/intern/web_thread_policy.cc",
        "imb_tests": UPSTREAM / "imbuf/tests/IMB_web_thread_policy_test.cc",
        "imb_cmake": UPSTREAM / "imbuf/CMakeLists.txt",
        "openexr": UPSTREAM / "imbuf/intern/openexr/openexr_api.cpp",
        "openexr_policy": UPSTREAM / "imbuf/intern/openexr/openexr_thread_policy.cpp",
        "openexr_cmake": UPSTREAM / "imbuf/intern/openexr/CMakeLists.txt",
        "oiio": UPSTREAM / "imbuf/intern/oiio/openimageio_api.cpp",
        "oiio_policy": UPSTREAM / "imbuf/intern/oiio/openimageio_thread_policy.cpp",
        "oiio_cmake": UPSTREAM / "imbuf/intern/oiio/CMakeLists.txt",
        "wgpu": UPSTREAM / "gpu/webgpu/wgpu_context.cc",
        "shader": UPSTREAM / "gpu/intern/gpu_shader.cc",
        "protocol": REPO / "sandbox/m8-wasm-split/TWO_PHASE_SCHEDULER_PROTOCOL.md",
        "platform_wasm": REPO / "patches/platform_wasm.cmake",
        "single_flight": REPO / "platform_web/split/single-flight.js",
        "profile_export": REPO / "platform_web/split/profile-export.js",
        "capture_driver": REPO / "sandbox/m8-wasm-split/capture_blender_profile.mjs",
        "runtime_driver": REPO / "sandbox/m8-wasm-split/verify_blender_split_runtime.mjs",
        "runtime_preflight": REPO / "sandbox/m8-wasm-split/runtime_split_preflight.mjs",
        "runtime_preflight_tests": REPO / "sandbox/m8-wasm-split/test_runtime_split_preflight.mjs",
        "runtime_state_monitor_tests": REPO / "sandbox/m8-wasm-split/test_runtime_state_monitor.py",
        "runtime_render_export_tests": REPO / "sandbox/m8-wasm-split/test_runtime_render_export.py",
        "profile_union": REPO / "sandbox/m8-wasm-split/merge_profiles.py",
        "finalizer": REPO / "scripts/finalize-wasm-split.py",
        "closure_selfcheck": REPO / "sandbox/m8-wasm-split/test_controller_closure.py",
        "controller_keep_selfcheck": REPO / "sandbox/m8-wasm-split/test_controller_keep_functions.py",
        "view_refresh_tests": REPO / "sandbox/m8-wasm-split/test_shared_memory_view_refresh.py",
        "range_sync_tests": REPO / "sandbox/m8-wasm-split/test_pthread_memory_range_sync.py",
        "capture_atomic_tests": REPO / "sandbox/m8-wasm-split/test_capture_atomic_diagnostics.py",
        "capture_entry_tests": REPO / "sandbox/m8-wasm-split/test_capture_thread_entry_diagnostics.py",
        "capture_late_tests": REPO / "sandbox/m8-wasm-split/test_capture_late_worker_attestation.mjs",
        "single_flight_late_tests": REPO / "sandbox/m8-wasm-split/test_single_flight_late_worker_attestation.mjs",
        "single_flight_fifo_tests": REPO / "sandbox/m8-wasm-split/test_single_flight_fifo_install.py",
        "view_growth_driver": REPO / "sandbox/m8-wasm-split/pthread-view-growth/verify.mjs",
        "view_growth_index": REPO / "sandbox/m8-wasm-split/pthread-view-growth/index.html",
        "view_growth_helper": REPO / "sandbox/m8-wasm-split/pthread-view-growth/helper.fixture.js",
        "view_growth_observer": REPO / "sandbox/m8-wasm-split/pthread-view-growth/gsab-observer.js",
        "pthread_harness": REPO / "sandbox/m8-wasm-split/pthread-lifecycle/verify.mjs",
        "pthread_lifecycle_source": UPSTREAM / "blenlib/tests/BLI_task_web_lifecycle.cc",
        "stack_policy_driver": REPO / "sandbox/m8-wasm-split/pthread-stack-policy/verify.py",
        "stack_policy_source": REPO / "sandbox/m8-wasm-split/pthread-stack-policy/stack_policy.c",
        "stack_policy_twin_source": REPO / "sandbox/m8-wasm-split/pthread-stack-policy/twin.c",
        "stack_policy_parser_tests": REPO / "sandbox/m8-wasm-split/test_link_stack_policy.py",
    }
    source = {name: path.read_text(encoding="utf-8") for name, path in paths.items()}

    require(source["scheduler"], "task_scheduler_web_split_is_ready{false}", "web false init")
    require(
        source["scheduler"],
        "static std::atomic<int> task_scheduler_num_threads{1}",
        "atomic scheduler count",
    )
    require(
        source["scheduler"],
        "int BLI_task_scheduler_num_threads()\n{\n"
        "  return task_scheduler_num_threads.load(std::memory_order_acquire);\n}",
        "atomic scheduler read",
    )
    require(
        source["threads"],
        "static std::atomic<int> threads_override_num{0}",
        "atomic thread override",
    )
    require(
        source["threads"],
        "threads_override_num.store(num, std::memory_order_release)",
        "atomic override write",
    )
    scheduler_reconfigure = source["scheduler"].split(
        "bool BLI_task_scheduler_reconfigure", 1
    )[1].split("bool BLI_task_scheduler_web_split_ready", 1)[0]
    ordered(
        scheduler_reconfigure,
        [
            ("tbb::global_control *replacement = MEM_new<tbb::global_control>",
             "construct replacement"),
            ("std::exchange(task_scheduler_global_control, replacement)", "swap replacement"),
            ("MEM_delete(previous)", "delete old control"),
            ("BLI_task_scheduler_active_threads() != num_threads", "verify active value"),
            ("std::exchange(task_scheduler_global_control, rollback)", "swap rollback"),
            ("MEM_delete(failed)", "delete failed control"),
        ],
    )
    pool = source["task_pool"]
    normalize_at = require(
        pool,
        "!BLI_task_scheduler_web_split_ready() &&\n"
        "        ELEM(this->type, TASK_POOL_BACKGROUND, TASK_POOL_BACKGROUND_SERIAL)",
        "both background pool variants",
    )
    use_threads_at = require(pool, "this->use_threads = BLI_task_scheduler_num_threads() > 1", "thread decision")
    if normalize_at >= use_threads_at:
        raise RuntimeError("background normalization must precede use_threads")
    require(pool, "this->type = TASK_POOL_NO_THREADS", "inline no-threads path")

    wm = source["wm"]
    park_control = wm.split("case WebSplitSchedulerPhase::ParkRequested:", 1)[1].split(
        "case WebSplitSchedulerPhase::PreparedRequested:", 1
    )[0]
    require(
        park_control,
        "BLI_system_num_threads_override_get() == 1",
        "PARK bootstrap scheduler-valid override observation",
    )
    for marker in ("wm_web_split_control_step_reduce", "wm_web_split_publish_step"):
        if marker not in park_control:
            raise RuntimeError(f"PARK shared production seam {marker} absent")
    ordered(
        wm.split("case WebSplitSchedulerPhase::ApplyRequested:", 1)[1].split(
            "case WebSplitSchedulerPhase::PageReadyRequested:", 1
        )[0],
        [
            ("BLI_task_scheduler_reconfigure(target_threads)", "scheduler apply"),
            ("IMB_web_thread_policy_apply(target_threads", "image apply"),
            ("g_web_split_openexr_threads.store(image_status.openexr_threads", "publish EXR"),
            ("g_web_split_oiio_threads.store(image_status.oiio_threads", "publish OIIO"),
            ("BLI_task_scheduler_web_split_mark_ready()", "native ready"),
            ("BLI_assert(reduced.error == WebSplitSchedulerError::None &&\n"
             "                 reduced.applied_generation == generation);",
             "shared applied success ACK publication"),
        ],
    )
    apply_ack_marker = "g_web_split_applied_generation.store(generation, std::memory_order_release)"
    apply_ack = wm.index(apply_ack_marker)
    control_tick = wm.split("static bool wm_web_split_control_tick", 1)[1].split("}  // namespace", 1)[0]
    if ".store(generation, std::memory_order_release)" in control_tick:
        raise RuntimeError("control tick bypasses centralized shared ACK publisher")
    if control_tick.count("wm_web_split_publish_step(") < 10:
        raise RuntimeError("control tick does not route all success/terminal paths through publisher")
    publisher = wm.split("static void wm_web_split_publish_step", 1)[1].split(
        "static bool wm_web_split_control_tick", 1
    )[0]
    if publisher.count(".store(generation, std::memory_order_release)") != 6:
        raise RuntimeError("centralized publisher must contain exactly six ACK-last release stores")
    ordered(
        wm,
        [
            ("g_web_split_parked_generation.store(generation, std::memory_order_release)",
             "PARK ACK"),
            ("g_web_split_prepared_generation.store(generation, std::memory_order_release)",
             "PREPARED ACK"),
            (apply_ack_marker, "APPLY ACK"),
            ("g_web_split_page_ready_generation.store(generation, std::memory_order_release)",
             "PAGE_READY ACK"),
            ("g_web_split_resumed_generation.store(generation, std::memory_order_release)",
             "RESUME ACK"),
        ],
    )
    ordered(
        wm,
        [
            ("if (wm_web_split_control_tick(c))", "control tick"),
            ("wm_window_events_process(c)", "events"),
            ("wm_event_do_handlers(c)", "handlers"),
            ("wm_event_do_notifiers(c)", "notifiers"),
            ("wm_draw_update(c)", "draw"),
        ],
    )
    for marker in (
        "BW_web_split_request_park",
        "BW_web_split_request_prepared",
        "BW_web_split_request_apply",
        "BW_web_split_request_page_ready",
        "BW_web_split_request_resume",
        "g_web_split_parked_generation.store(generation, std::memory_order_release)",
        "g_web_split_resumed_generation.store(generation, std::memory_order_release)",
        "BW_web_split_prepared_workers",
        "BW_web_split_prepared_stabilization_epoch",
        "BW_web_split_page_ready_workers",
        "BW_web_split_page_ready_stabilization_epoch",
        "BW_web_split_openexr_threads",
        "BW_web_split_oiio_threads",
        "BW_web_split_apply_openexr_set",
        "BW_web_split_apply_oiio_set",
        "BW_web_split_rollback_openexr_set",
        "BW_web_split_rollback_oiio_set",
        "BW_web_split_reload_required",
        "WM_jobs_has_running(wm)",
    ):
        require(wm, marker, marker)

    apply_request = wm.split(
        "EMSCRIPTEN_KEEPALIVE int BW_web_split_request_apply", 1
    )[1].split("EMSCRIPTEN_KEEPALIVE int BW_web_split_request_prepared", 1)[0]
    if "wm_web_split_validate_apply" not in apply_request or \
       "g_web_split_prepared_generation.load(std::memory_order_acquire)" not in apply_request:
        raise RuntimeError("APPLY is not gated on exact PREPARED ACK")
    resume_request = wm.split(
        "EMSCRIPTEN_KEEPALIVE int BW_web_split_request_resume", 1
    )[1].split("EMSCRIPTEN_KEEPALIVE int BW_web_split_phase", 1)[0]
    if "wm_web_split_validate_resume" not in resume_request or \
       "g_web_split_page_ready_generation.load(std::memory_order_acquire)" not in resume_request:
        raise RuntimeError("RESUME is not gated on exact PAGE_READY ACK")
    for payload in ("prepared", "page_ready"):
        for field in (
            "workers",
            "acknowledgements",
            "instances",
            "local_instances",
            "pending",
            "protocol_errors",
            "stabilization_epoch",
        ):
            require(wm, f"BW_web_split_{payload}_{field}()", f"{payload} {field} getter")
    require(wm, "BW_web_split_page_ready_late_workers()", "page-ready late worker getter")
    require(
        source["wm_protocol"],
        "late_workers != payload.workers - prepared_workers",
        "page-ready exact late-worker delta",
    )
    require(
        source["wm_protocol"],
        "page_ready_epoch <= prepared_epoch",
        "page-ready fresh stabilization epoch",
    )
    require(wm, "BW_web_split_offending_generation()", "offending generation getter")
    fail_source = wm.split("static int wm_web_split_fail", 1)[1].split(
        "static WebSplitSchedulerPhase", 1
    )[0]
    ordered(
        fail_source,
        [
            ("g_web_split_offending_generation.store(generation", "record offending generation"),
            ("g_web_split_request_generation.load", "load active transaction generation"),
            ("g_web_split_error_generation.store", "terminal active-generation ACK"),
        ],
    )

    require(
        source["task_tests"],
        "std::thread reader([&]()",
        "concurrent scheduler reader test",
    )
    require(
        source["blenlib_cmake"],
        "target_compile_definitions(bf_blenlib PRIVATE WITH_GTESTS)",
        "test seam library definition",
    )
    require(
        source["blenlib_cmake"],
        "target_compile_definitions(BLI_test PRIVATE WITH_GTESTS)",
        "test seam executable definition",
    )

    require(source["imb_api"], "IMB_web_thread_policy_apply", "public IMB aggregate")
    if "IMB_web_thread_policy_apply" in source["imb_module"] or \
       "WITH_OPENEXR" in source["imb_policy"]:
        raise RuntimeError("image policy aggregate is not isolated and unconditional")
    require(source["imb_policy"], '#include "openexr/openexr_api.h"', "unconditional EXR API")
    require(source["imb_policy"], "imb_thread_count_openexr_set(openexr_threads)", "EXR setter")
    require(source["imb_policy"], "OIIO_thread_count_set(oiio_threads)", "OIIO setter")
    require(source["imb_cmake"], "intern/web_thread_policy.cc", "aggregate archive member")
    require(
        source["openexr_policy"],
        "bool imb_thread_count_openexr_set(const int threads)",
        "isolated EXR setter",
    )
    require(
        source["openexr_policy"],
        "int imb_thread_count_openexr_get()",
        "isolated EXR getter",
    )
    require(
        source["openexr_cmake"],
        "openexr_thread_policy.cpp",
        "EXR policy archive member",
    )
    require(
        source["oiio_policy"],
        "bool OIIO_thread_count_set(const int threads)",
        "isolated OIIO setter",
    )
    require(source["oiio_policy"], "int OIIO_thread_count_get()", "isolated OIIO getter")
    require(
        source["oiio_cmake"],
        "openimageio_thread_policy.cpp",
        "OIIO policy archive member",
    )
    if "bool imb_thread_count_openexr_set" in source["openexr"] or \
       "bool OIIO_thread_count_set" in source["oiio"]:
        raise RuntimeError("image policy definitions remain co-located with broad backends")
    if source["imb_tests"].count("IMB_web_thread_policy_apply(0, 1), 0, 1") != 2:
        raise RuntimeError("aggregate test must prove bootstrap and rollback policy")
    require(
        source["imb_tests"],
        "IMB_web_thread_policy_apply(8, 8), 8, 8",
        "aggregate apply regression",
    )
    require(
        source["imb_cmake"],
        "tests/IMB_web_thread_policy_test.cc",
        "aggregate regression test target",
    )
    require(
        source["openexr"],
        "parked split-module transition has installed the deferred module. */\n"
        "  Imf::setGlobalThreadCount(0);",
        "EXR bootstrap zero",
    )
    require(
        source["openexr_policy"], "return Imf::globalThreadCount();", "EXR observed count"
    )
    require(source["oiio"], "OIIO_thread_count_set(1)", "OIIO bootstrap caller-only")
    require(
        source["oiio_policy"],
        'OIIO::getattribute("threads", threads)',
        "OIIO observed count",
    )
    require(source["wgpu"], "GCaps.use_main_context_workaround = true", "WebGPU main-context invariant")
    require(source["shader"], "if (!GPU_use_main_context_workaround())", "no GPU worker invariant")

    single_flight = source["single_flight"]
    for marker, label in (
        ('Module["bwRequestSplitPark"] =', "page PARK API"),
        ('Module["bwPrepareSplitSecondary"] =', "page PREPARED API"),
        ('Module["bwApplySplitScheduler"] =', "page APPLY API"),
        ('Module["bwMarkSplitPageReady"] =', "page PAGE_READY API"),
        ('Module["bwResumeSplitScheduler"] =', "page RESUME API"),
    ):
        require(single_flight, marker, label)
    for marker in (
        'bwSplitNativeCall("BW_web_split_request_park"',
        'bwSplitNativeCall("BW_web_split_request_prepared"',
        'bwSplitNativeCall("BW_web_split_request_apply"',
        'bwSplitNativeCall("BW_web_split_request_page_ready"',
        'bwSplitNativeCall("BW_web_split_request_resume"',
        'preparedStabilizationEpoch: bwSplitNativeRead',
        'pageReadyStabilizationEpoch: bwSplitNativeRead',
        'worker set drifted after PAGE_READY ACK',
        'PAGE_READY refuses post-entry worker install',
        'ACK generation " + message.generation',
        "worker.__bwSplitAttachedHandler === worker.onmessage",
    ):
        require(single_flight, marker, f"single-flight {marker}")
    for marker in ('"initial-before-start"', "lateInitialAckWorkerIds"):
        if marker not in single_flight:
            raise RuntimeError(f"single-flight persisted attestation {marker} absent")
    single_flight_load_wrapper = single_flight.split(
        "PThread.loadWasmModuleToWorker = function (worker) {", 1
    )[1].split("for (var bwSplitInitialWorker", 1)[0]
    ordered(single_flight_load_wrapper, [
        ("var loading = bwSplitOriginalLoadWorker(worker);", "shipping original worker load"),
        ("bwSplitAttachWorker(worker);", "shipping reattach after loader overwrite"),
        ('cmd: "bwSplitInitialInstall"', "shipping FIFO initial install"),
        ("return loading.then", "shipping loader return after FIFO post"),
    ])
    require(source["profile_export"], 'Module["bwCaptureStabilizeWorkers"] =', "capture worker stabilization")
    require(source["profile_export"], 'Module["bwCaptureAttestPageReady"]', "capture non-messaging PAGE_READY")
    require(source["profile_export"], 'Module["bwCaptureResumeAfterStable"]', "capture atomic resume")
    require(source["profile_export"], "stableRounds < 2 || finalWorkers.length < 8", "capture stable worker rounds")
    for marker in (
        'worker.__bwCaptureLoadState = "ready-before-entry"',
        "BW_SPLIT_CAPTURE_PREENTRY_ATTESTATION_V1",
        "const loading = originalLoadWasmModuleToWorker(worker);",
        "attach(worker);",
        "late pre-entry load attestation failed",
        "postApplyProbeCount",
        '"BW_web_split_request_resume"',
    ):
        if marker not in source["profile_export"]:
            raise RuntimeError(f"capture persisted attestation {marker} absent")
    profile_load_wrapper = source["profile_export"].split(
        "PThread.loadWasmModuleToWorker = (worker) => {", 1
    )[1].split("const currentWorkers", 1)[0]
    ordered(profile_load_wrapper, [
        ("const loading = originalLoadWasmModuleToWorker(worker);", "capture original worker load"),
        ("attach(worker);", "capture reattach after loader overwrite"),
        ("const tracked = Promise.resolve(loading)", "capture pre-entry load promise"),
    ])

    capture_driver = source["capture_driver"]
    require(capture_driver, "scenario: null, threads: 1", "capture threads-one default")
    require(capture_driver, "--scenario success|terminal-error required", "capture exact two scenarios")
    for marker, label in (
        ("trusted semantic interaction proof failed", "capture trusted interaction"),
        ("BW_web_split_request_park", "capture PARK"),
        ("window.__bwModule.bwCaptureStabilizeWorkers(generation)", "capture prepared stabilization"),
        ("BW_web_split_request_prepared", "capture PREPARED"),
        ("bwCaptureAttestPageReady", "capture non-messaging PAGE_READY attestation"),
        ("BW_web_split_request_page_ready", "capture PAGE_READY"),
        ("postPageReadyWorkers", "capture post-ready recheck"),
        ("bwCaptureResumeAfterStable", "capture RESUME"),
    ):
        if marker not in capture_driver:
            raise RuntimeError(f"{label} absent")
    require(capture_driver, "out-of-order APPLY was not rejected", "capture terminal-error hot path")
    if capture_driver.count("postApplyProbeCount !== 0") != 2:
        raise RuntimeError("capture must gate zero post-APPLY probes at PAGE_READY and RESUME")
    for marker in (
        "shared-memory-fixed-view-refresh-v2",
        "splitBuild.finalizer?.sha256 !== currentFinalizer.sha256",
        "splitBuild.profile_export?.sha256 !== currentProfileExport.sha256",
        "splitBuild.profile_export?.pre_entry_marker_count !== 1",
        "persisted_pre_entry_attestation",
        "profileExport: currentProfileExport",
        "BW_SPLIT_SHARED_MEMORY_VIEW_REFRESH_V1",
        "BW_SPLIT_SHARED_MEMORY_GROWABLE_VIEW_GUARD_V1",
        "refresh?.refresh_anchor_count_before !== 1",
        "refresh?.guard_anchor_count_before !== 1",
        "refresh?.growable_length_guard_count_after !== 1",
        "sharedMemoryViewRefresh: refresh",
        "finalizer: currentFinalizer",
    ):
        if marker not in capture_driver:
            raise RuntimeError(f"capture shared-memory build binding {marker} absent")

    runtime_driver = source["runtime_driver"]
    require(
        runtime_driver,
        "validateSplitArtifactIdentity(split, bin)",
        "runtime exact live artifact preflight",
    )
    require(runtime_driver, "serverLog: null, threads: 1, expectedWorkers: 8", "runtime threads-one default")
    ordered(runtime_driver, [
        ("trusted extrude did not change topology", "runtime trusted interaction"),
        ("bwRequestSplitPark", "runtime PARK"),
        ("bwPrepareSplitSecondary(generation)", "runtime PREPARED"),
        ("bwApplySplitScheduler", "runtime APPLY"),
        ("bwMarkSplitPageReady", "runtime PAGE_READY"),
        ("postPageReady = await page.evaluate", "runtime post-ready recheck"),
        ("bwResumeSplitScheduler", "runtime RESUME"),
        ("FS.writeFile('/tmp/bw-split-ready'", "runtime cold release"),
    ])
    for marker in ("pageReadyWorkerIdentity", "preparedWorkerIds", "lateInitialAckWorkerIds",
                   "lateWorkerAckDelta", "lateWorkerReconciliation",
                   "initial-before-start", "queuedInput", "transitionTimeline", "nativeFinal"):
        if marker not in runtime_driver:
            raise RuntimeError(f"runtime receipt {marker} absent")
    for marker in (
        "exactControllerKeep",
        "exact-controller-export-defined-function-keep-set-v1",
        "binary-index-callgraph-streamed-wat-closure-v1",
        "reachable_placeholder_paths.length === 0",
        "forbidden_indirect_ref_table_ops.length === 0",
        "inspected_reachable_defined_count === controllerProof.reachable_function_count",
        "controllerClosure,",
    ):
        if marker not in runtime_driver:
            raise RuntimeError(f"runtime controller-closure binding {marker} absent")
    runtime_preflight = source["runtime_preflight"]
    for marker in (
        "exact-served-split-artifact-identity-v1",
        "not the exact served bin file",
        "requireRowIdentity('primary', split.primary, primary)",
        "requireRowIdentity('secondary', split.secondary, secondary)",
        "requireRowIdentity('js', split.js, js, false)",
        "controller closure and split primary identity mismatch",
        "minimum-baseline-exact-current-worker-census-v1",
        "worker count ${status?.workerCount} is below minimum ${minimumWorkers}",
        "worker ID census is not exact and unique",
        "lifecycleIds.some((id) => !Number.isSafeInteger(id) || id < 1)",
        "workerIds.every((id) => lifecycleSet.has(id))",
        "worker lifecycle does not match exact ID census",
    ):
        if marker not in runtime_preflight:
            raise RuntimeError(f"runtime exact artifact preflight {marker} absent")
    runtime_preflight_tests = source["runtime_preflight_tests"]
    for marker in (
        "primary SHA",
        "JS SHA",
        "wrong path",
        "proof primary mismatch",
        "artifact-positive=1 artifact-negative=4",
        "wrong-type lifecycle ID",
        "nonpositive lifecycle ID",
        "census-positive=1 census-negative=5 PASS",
    ):
        if marker not in runtime_preflight_tests:
            raise RuntimeError(f"runtime artifact preflight test {marker} absent")
    require(
        source["runtime_driver"],
        'signature=(s["mode"],s["verts"]) if s is not None else None',
        "runtime topology-aware state signature",
    )
    runtime_state_monitor_tests = source["runtime_state_monitor_tests"]
    for marker in (
        r"const PY_MONITOR = String\.raw",
        "exact_block",
        "object_16",
        "object_24",
        "same-mode-topology=1",
    ):
        if marker not in runtime_state_monitor_tests:
            raise RuntimeError(f"runtime state-monitor test {marker} absent")

    for marker in (
        "_bwsr_export_png",
        "image.save_render(filepath=path,scene=scene)",
        "saved-render-png-authoritative-readback-v1",
        "preserveGuestRender",
        "nonblackPixels > 0 && rgbMax > 0",
        "renderOutputProof?.pass === true",
        "scene.render.threads_mode='FIXED'; scene.render.threads=1",
        "BKE_render_num_threads/rna_RenderSettings_threads_get must report the active value eight",
        '"threads_mode":"FIXED","requested_threads":1,"effective_threads":8',
    ):
        if marker not in runtime_driver:
            raise RuntimeError(f"runtime authoritative render export {marker} absent")
    if "image.pixels" in runtime_driver or "_bwsr_pixels" in runtime_driver:
        raise RuntimeError("runtime must not gate completed renders on stale Image pixels")
    runtime_render_export_tests = source["runtime_render_export_tests"]
    for marker in (
        r"const PY_MONITOR = String\.raw",
        "render_result_size",
        "[0, 0]",
        "saved-render-png-authoritative-readback-v1",
        "nonblack-node-gate=1",
        "canonical-cycles-post-apply-override8=1",
        "execute_node_oracle(source)",
        "negatives={negatives}+2",
    ):
        if marker not in runtime_render_export_tests:
            raise RuntimeError(f"runtime render-export test {marker} absent")

    capture_late_tests = source["capture_late_tests"]
    for marker in ("rejectPostEntry", "latePreEntryLoadIds", "postApplyProbeCount",
                   "PAGE_READY worker set drift", "BW_CAPTURE_LATE_WORKER_ATTESTATION_TEST PASS"):
        if marker not in capture_late_tests:
            raise RuntimeError(f"capture late-worker test {marker} absent")
    single_flight_late_tests = source["single_flight_late_tests"]
    for marker in ("initial-before-start", "wrong generation", "wrong instance count",
                   "duplicate ACK", "preobserved-before-load", "__bwSplitAttachedHandler",
                   "startWorker", "cmd3", "cmd2", "worker-core command dispatch",
                   "PREPARED must refresh copied status",
                   "BW_SINGLE_FLIGHT_LATE_WORKER_ATTESTATION_TEST PASS"):
        if marker not in single_flight_late_tests:
            raise RuntimeError(f"single-flight late-worker test {marker} absent")
    single_flight_fifo_tests = source["single_flight_fifo_tests"]
    for marker in (
        "patch_single_flight_runtime",
        "bwSplitInitialInstall",
        "fifo-initial-install-before-thread-entry",
        "missing_module",
        "wrong_generation",
        "wrong_worker",
        "structural negative",
        "BW_SINGLE_FLIGHT_FIFO_INSTALL_TEST PASS",
    ):
        if marker not in single_flight_fifo_tests:
            raise RuntimeError(f"single-flight FIFO test {marker} absent")
    require(
        source["finalizer"],
        'SINGLE_FLIGHT_INITIAL_DISPATCH_MARKER = "BW_SPLIT_WORKER_INITIAL_INSTALL_FIFO_V1"',
        "generated FIFO initial-install marker",
    )
    require(
        source["finalizer"],
        'msgData.workerId,\\"initial-before-start\\")){throw new Error(',
        "generated core FIFO initial delivery discriminator",
    )
    require(
        source["finalizer"],
        'msgData.workerId,\\"command\\")}else if(cmd==2){',
        "generated core command delivery discriminator",
    )
    prepared_publish = source["single_flight"].split(
        "bwSplitPreparedWorkerIds = status.workerIds.slice().sort(function (a, b) { return a - b; });",
        1,
    )[1].split("return { split: status, native: nativeStatus };", 1)[0]
    ordered(
        prepared_publish,
        [
            ("status = bwSplitStatus();", "refresh copied PREPARED page status"),
            ('bwSplitNativeCall("BW_web_split_request_prepared", [', "native PREPARED request"),
        ],
    )

    profile_union = source["profile_union"]
    require(profile_union, 'capture_scenarios != {"success", "terminal-error"}', "profile exact scenarios")
    require(profile_union, 'controller.get("status") != "PASS"', "profile controller PASS")
    finalizer = source["finalizer"]
    for marker in (
        "verify_primary_controller_closure_source",
        "return_call_indirect|call_ref|return_call_ref",
        "controller closure reaches missing target",
        'capture_scenarios != {"success", "terminal-error"}',
        "transitive_direct_call_proof",
        "binary-index-callgraph-streamed-wat-closure-v1",
        "--print-call-graph",
        "--all-features",
        "reachable_placeholder_paths",
        "forbidden_indirect_ref_table_ops",
        "PROFILE_EXPORT_SOURCE",
        '"persisted_pre_entry_attestation": True',
        '"post_apply_probe_counter": True',
        '"pre_entry_marker_count"',
        "def controller_keep_functions",
        '"--keep-funcs"',
        '"keep_functions": controller_keep',
        "exact-controller-export-defined-function-keep-set-v1",
    ):
        if marker not in finalizer:
            raise RuntimeError(f"finalizer {marker} absent")
    if finalizer.count("patch_shared_memory_view_refresh(args.js)") != 2:
        raise RuntimeError("CAPTURE and APPLY must both apply shared-memory view refresh")
    if finalizer.count('"shared_memory_view_refresh": shared_memory_view_refresh') != 2:
        raise RuntimeError("CAPTURE and APPLY receipts must both bind shared-memory view refresh")
    if finalizer.count("patch_pthread_memory_range_sync(args.js)") != 2:
        raise RuntimeError("CAPTURE and APPLY must both apply pthread memory range sync")
    if finalizer.count('"pthread_memory_range_sync": pthread_memory_range_sync') != 2:
        raise RuntimeError("CAPTURE and APPLY receipts must both bind pthread memory range sync")
    for marker in (
        "BW_SPLIT_PTHREAD_MEMORY_RANGE_SYNC_V1",
        "BW_SPLIT_PTHREAD_STACK_RANGE_SYNC_V1",
        "BW_SPLIT_PTHREAD_MAILBOX_RANGE_SYNC_V1",
        "wasmMemory.grow(0)",
        "pthread_ptr+116",
        "stackSize<=0",
        "bwSyncPthreadMemoryRange(bwMsgPtr,bwMsgPtr+116);",
    ):
        if marker not in finalizer:
            raise RuntimeError(f"pthread memory range-sync marker {marker} absent")
    for marker in (
        "exposeGrown ? grownBuffer : oldBuffer",
        "rejected('unsafe pointer'",
        "rejected('unaligned pointer'",
        "rejected('overflow pointer'",
        "rejected('grow0 remains short'",
        "metadataFailure('zero size'",
        "metadataFailure('zero high'",
        "metadataFailure('size exceeds high'",
        "metadataFailure('high outside memory'",
    ):
        require(source["range_sync_tests"], marker, f"pthread range-sync test {marker}")
    require(
        source["view_refresh_tests"],
        "growable fixed view, replaced buffer",
        "shared-memory view refresh semantic matrix",
    )
    for marker in (
        "BW_SPLIT_SHARED_MEMORY_GROWABLE_VIEW_GUARD_V1",
        "HEAP8.byteLength==getMemoryBuffer().byteLength",
        "heap8BufferShared",
        "memoryBufferShared",
        "heapU64Bytes",
    ):
        if marker not in finalizer:
            raise RuntimeError(f"shared-memory robust guard/diagnostics {marker} absent")
    for marker in ("heap8BufferShared", "memoryBufferShared", "heapU64Bytes",
                   "range_sync_tag_count_after"):
        require(source["capture_atomic_tests"], marker, f"CAPTURE atomic test {marker}")
    for marker in (
        r'typeof HEAPU64==\"undefined\"?null:HEAPU64.byteLength',
        "globalThis.__bwCaptureThreadParams??null",
        "__bwCaptureThreadEntryStages||[]",
    ):
        if marker not in finalizer:
            raise RuntimeError(f"CAPTURE atomic fail-safe diagnostic {marker} absent")
    for marker in ("heapU64Bytes\"] is None", "messageParams", "stages"):
        if marker not in source["capture_atomic_tests"]:
            raise RuntimeError(f"CAPTURE atomic optional-view test {marker} absent")
    for marker in (
        "patch_capture_thread_entry_diagnostics(args.js)",
        '"capture_thread_entry_diagnostics": capture_thread_entry_diagnostics',
        "BW_SPLIT_CAPTURE_THREAD_ENTRY_DIAG_V1",
        "BW_SPLIT_CAPTURE_THREAD_ENTRY_STAGE_V1",
        "BW_SPLIT_CAPTURE_MAIN_DIAGNOSTIC_DISPATCH_V1",
        'case "bwCaptureAtomicError"',
        'case "bwCaptureThreadEntryError"',
        "__bwCaptureAtomicDiagnostics??=[]",
        "__bwCaptureThreadEntryDiagnostics??=[]",
        "messageParams",
        "messagePthreadMatchesSelf",
        "messageRoutineMatchesInvoke",
        "messageArgMatchesInvoke",
        "stackCurrentMatchesMessageHigh",
        "stackCurrentMatchesSelfHigh",
        "tableEntryName",
        "before-establish",
        "after-thread-init",
        "after-tls",
        "before-entry",
        "stackCurrentInMemory",
        "stackHighInMemory",
        "messageStackHighInMemory",
        'cmd:"bwCaptureThreadEntryError"',
    ):
        if marker not in finalizer:
            raise RuntimeError(f"CAPTURE pthread entry diagnostics {marker} absent")
    for marker in (
        "capture-pthread-entry-stack-diagnostics-v1",
        "4 semantic + five-stage + core dispatch + 7 structural negative PASS",
        "main_dispatch_anchor_count_before",
        "main_atomic_case_count_after",
        "main_entry_case_count_after",
        "stack_high_offset",
        "stack_size_offset",
    ):
        require(source["capture_entry_tests"], marker, f"CAPTURE entry test {marker}")
    for marker in (
        "bad-message-metadata",
        "self-message-mismatch",
        "stack-current-out-of-range",
        "tableLookupCount",
        "tableEntryName",
        "messagePthreadMatchesSelf",
        "stackCurrentInMemory",
        "messageStackHighInMemory",
        "value:'131003'",
    ):
        if marker not in source["capture_entry_tests"]:
            raise RuntimeError(f"CAPTURE entry semantic test {marker} absent")
    for marker in (
        "capture_thread_entry_diagnostics",
        "BW_SPLIT_CAPTURE_THREAD_ENTRY_DIAG_V1",
        "threadEntryDiagnostics",
        "BW_SPLIT_CAPTURE_MAIN_DIAGNOSTIC_DISPATCH_V1",
        "main_dispatch_anchor_count_before",
        "main_atomic_case_count_after",
        "main_entry_case_count_after",
    ):
        if marker not in source["capture_driver"]:
            raise RuntimeError(f"CAPTURE driver entry binding {marker} absent")
    for marker in (
        "pthread_memory_range_sync",
        "pthread-cross-realm-memory-range-sync-v1",
        "BW_SPLIT_PTHREAD_MEMORY_RANGE_SYNC_V1",
        "BW_SPLIT_PTHREAD_STACK_RANGE_SYNC_V1",
        "BW_SPLIT_PTHREAD_MAILBOX_RANGE_SYNC_V1",
        "wasmMemory.grow(0)",
        "pthreadMemoryRangeSync: rangeSync",
    ):
        if marker not in source["capture_driver"]:
            raise RuntimeError(f"CAPTURE driver range-sync binding {marker} absent")
        if marker in ("pthread_memory_range_sync", "pthread-cross-realm-memory-range-sync-v1") and marker not in source["runtime_driver"]:
            raise RuntimeError(f"runtime driver range-sync binding {marker} absent")
    for marker in (
        "globalThis.__bwCaptureAtomicDiagnostics ??= []",
        "globalThis.__bwCaptureThreadEntryDiagnostics ??= []",
    ):
        if marker not in source["profile_export"]:
            raise RuntimeError(f"CAPTURE global diagnostic buffer {marker} absent")
    for name, markers in {
        "view_growth_driver": (
            "blender-web.shared-view-growth.v4",
            "shared-memory-fixed-view-refresh-v2",
            "afterOldIdentityHelper",
            "trackingAfterDirectUpdate",
            "exactGuardCount",
            "executedObserver",
        ),
        "view_growth_index": (
            "new Worker(\"gsab-observer.js\")",
            "ackCount",
            "window.__bwViewGrowth",
        ),
        "view_growth_observer": (
            'importScripts("helper.js")',
            "function oldUpdateMemoryViews()",
            "function oldIdentityOnlyGrowMemViews()",
            "new SharedArrayBuffer(initialBytes, {maxByteLength:finalBytes})",
            "afterOldDirectUpdate",
            "trackingAfterDirectUpdate",
        ),
        "view_growth_helper": (
            "if(HEAP8?.buffer?.growable)return;",
            "function growMemViews(){if(wasmMemory.buffer!=HEAP8.buffer)",
            "HEAPU64=new BigUint64Array(b)",
        ),
    }.items():
        for marker in markers:
            if marker not in source[name]:
                raise RuntimeError(f"shared-view harness {name} marker {marker} absent")
    closure_selfcheck = source["closure_selfcheck"]
    for marker in ("transitive placeholder", "return call", "call_indirect", "call_ref", "missing target"):
        if marker not in closure_selfcheck:
            raise RuntimeError(f"closure selfcheck {marker} absent")
    controller_keep_selfcheck = source["controller_keep_selfcheck"]
    for marker in (
        "controller_keep_functions",
        "missing export",
        "imported export",
        "out-of-range export",
        "duplicate defined ordinal",
    ):
        if marker not in controller_keep_selfcheck:
            raise RuntimeError(f"controller keep selfcheck {marker} absent")
    for marker in ("BLI_task_web_lifecycle", "BW_PTHREAD_LIFECYCLE_RESULT PASS", "serve_split.py", "taskPoolSource"):
        if marker not in source["pthread_harness"]:
            raise RuntimeError(f"production pthread harness {marker} absent")
    for marker in (
        "-sSTACK_SIZE=33554432",
        "-sDEFAULT_PTHREAD_STACK_SIZE=8388608",
        "BW_PTHREAD_STACK_POLICY",
        "stackPolicyPass",
        "blender-web.pthread-lifecycle.v3",
    ):
        if marker not in source["pthread_harness"]:
            raise RuntimeError(f"production pthread stack-policy harness {marker} absent")
    require(
        source["platform_wasm"],
        '" -sSTACK_SIZE=33554432 -sDEFAULT_PTHREAD_STACK_SIZE=8388608"',
        "shipping split stack policy",
    )
    if "-sDEFAULT_PTHREAD_STACK_SIZE=33554432" in source["platform_wasm"]:
        raise RuntimeError("shipping ordinary pthread default regressed to 32 MiB")
    for marker in (
        "PROXY_TO_PTHREAD WM main",
        "Ordinary pthreads use an independent 8 MB",
    ):
        if marker not in source["platform_wasm"]:
            raise RuntimeError(f"stack-policy rationale {marker} absent")
    for marker in (
        "STACK_SIZE=33554432",
        "DEFAULT_PTHREAD_STACK_SIZE=8388608",
        "shaderc/Tint",
        "Ordinary pthread",
    ):
        if marker not in source["protocol"]:
            raise RuntimeError(f"stack-policy protocol marker {marker} absent")
    for marker in (
        "proxy-main-32m-ordinary-pthread-8m-explicit-child-2m-v1",
        '"proxy_main": 33554432',
        '"ordinary_default": 8388608',
        '"explicit_child": 2097152',
        "wasm_byte_identical",
        "expected_default_literal_count",
    ):
        if marker not in source["stack_policy_driver"]:
            raise RuntimeError(f"pinned stack-policy toolchain proof {marker} absent")
    for marker in (
        "PROXY_MAIN_STACK = 32 * 1024 * 1024",
        "ORDINARY_DEFAULT_STACK = 8 * 1024 * 1024",
        "EXPLICIT_CHILD_STACK = 2 * 1024 * 1024",
        "pthread_attr_setstacksize",
        "BW_PTHREAD_STACK_POLICY_RESULT",
    ):
        if marker not in source["stack_policy_source"]:
            raise RuntimeError(f"stack-policy executable {marker} absent")
    for marker in (
        "verify_link_stack_policy",
        "stack_size_occurrences",
        "default_pthread_stack_size_occurrences",
        "effective_stack_size",
        "effective_default_pthread_stack_size",
        "proxy-main-32m-ordinary-pthread-8m-v1",
    ):
        if marker not in source["finalizer"]:
            raise RuntimeError(f"finalizer effective stack-policy binding {marker} absent")
    for marker in (
        "swapped policy",
        "missing pthread default",
        "late main-stack override",
        "late pthread-default override",
        "BW_LINK_STACK_POLICY_TEST PASS positive=2 negatives=5",
    ):
        if marker not in source["stack_policy_parser_tests"]:
            raise RuntimeError(f"stack-policy parser test {marker} absent")
    for marker in ("proxy_main_stack_size", "ordinary_pthread_stack_size", "BW_PTHREAD_STACK_POLICY"):
        if marker not in source["pthread_lifecycle_source"]:
            raise RuntimeError(f"BLI lifecycle stack-policy assertion {marker} absent")
    for marker in ("wm_web_split_apply_reduce", "wm_web_split_control_step_reduce",
                   "ProductionControlStepTerminalAckAndResumeNextTick",
                   "ProductionControlStepApplyFailureRollbackAndReload",
                   "ProductionControlStepCompletePhaseAndFailureMatrix",
                   "CompleteValidatorRejectionMatrix",
                   "ImageMismatchRollbackReloadAndAckLast", "ExactPhaseGenerationAndEpochValidation"):
        if marker not in source["wm_protocol_tests"]:
            raise RuntimeError(f"WM protocol test {marker} absent")

    receipt = {
        "schema": "blender-web.two-phase-source.v1",
        "verdict": "PASS",
        "contract": "park-prepare-apply-final-ready-resume-v1",
        "files": {
            name: {
                "path": str(path.relative_to(REPO)),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for name, path in paths.items()
        },
    }
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
