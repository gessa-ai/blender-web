#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Browser/build-free parser adversarial checks for strict raw runners."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile


HERE = Path(__file__).resolve().parent


def module(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


m1 = module("run_m1")
m2 = module("run_m2")
m2deps = module("run_m2_deps")
m3 = module("run_m3")


def main() -> int:
    negatives: list[str] = []

    def reject(name: str, operation) -> None:
        try:
            operation()
        except (m1.RunError, m2.RunError, m2deps.RunError, m3.RunError):
            negatives.append(name)
        else:
            raise AssertionError(f"negative parser fixture unexpectedly passed: {name}")

    assert m1.parse_gtest_names("Suite.\n  First\n  Second\n") == ["Suite.First", "Suite.Second"]
    assert m1.parse_gtest_names("Suite.\n  First\n  First\n") == [
        "Suite.First@occurrence=1", "Suite.First@occurrence=2"]
    reject("gtest_duplicate_multiplicity", lambda: m1.require_exact_gtest_names(
        m1.parse_gtest_names("Suite.\n  First\n  First\n"),
        m1.parse_gtest_names("Suite.\n  First\n"), 1))
    reject("gtest_occurrence_encoding_collision", lambda: m1.parse_gtest_names(
        "Suite.\n  First@occurrence=1\n"))
    reject("gtest_orphan_case", lambda: m1.parse_gtest_names("  First\n"))
    assert len(m2.suite_rows()) == 75
    detector_row = {
        "id": m2.DETECTOR_ACTIVE_ID,
        "status": m2.DETECTOR_ACTIVE_STATUS,
        "evidence": "fixture ADR-004 detector evidence",
    }
    detector_active = m2.active_deferral_rows({"deferred": [detector_row]})
    detector_raw = m2.DETECTOR_ACTIVE_MARKER.replace("0xADDR", "0x1234").encode()
    detector_normalized = m2.DETECTOR_ACTIVE_MARKER.encode()
    assert m2.failure_deferral_records(
        m2.DETECTOR_ACTIVE_SUITE, detector_active, detector_raw, detector_normalized
    ) == (
        [m2.DETECTOR_ACTIVE_ID], [{
            "id": m2.DETECTOR_ACTIVE_ID,
            "status": m2.DETECTOR_ACTIVE_STATUS,
            "evidence": detector_row["evidence"],
            "marker": m2.DETECTOR_ACTIVE_MARKER,
        }])
    reject("m2_detector_unknown_status", lambda: m2.active_deferral_rows({"deferred": [
        dict(detector_row, status="detector-pending")]}))
    reject("m2_detector_wrong_id", lambda: m2.active_deferral_rows({"deferred": [
        dict(detector_row, id="wasm32-other-collision")]}))
    reject("m2_detector_wrong_suite", lambda: m2.failure_deferral_records(
        "blendfile_io", detector_active, detector_raw, detector_normalized))
    reject("m2_detector_missing_marker", lambda: m2.failure_deferral_records(
        m2.DETECTOR_ACTIVE_SUITE, detector_active, b"unrelated failure",
        detector_normalized))
    reject("m2_detector_wrong_marker", lambda: m2.failure_deferral_records(
        m2.DETECTOR_ACTIVE_SUITE, detector_active, detector_raw,
        detector_normalized.replace(b"ADR-004", b"ADR-005")))
    native_body = b".\n----------------------------------------------------------------------\nRan 1 test in 0.001s\n\nOK\n"
    wasm_body = native_body.replace(b"0.001s", b"0.018s")
    native_raw = (
        native_body + m2.ALLOCATOR_LINE
        + b"Blender 5.2.0 LTS (hash fbe6228777e7 built 2026-07-14 01:31:22)\n"
    )
    wasm_raw = (
        m2.ALLOCATOR_LINE + m2.WASM_BANNER_LINE
        + b"00:10.327  translation      | WARNING 'locale' data path for translations not found\n"
        + wasm_body
    )
    expected_normalized = native_body.replace(
        b"Ran 1 test in 0.001s", b"Ran 1 tests in <T>s"
    )
    assert m2.normalized_bytes(native_raw, wasm=False) == expected_normalized
    assert m2.normalized_bytes(wasm_raw, wasm=True) == expected_normalized
    trailing_blanks = b"\n" * 5
    assert m2.normalized_bytes(
        m2.ALLOCATOR_LINE + m2.WASM_BANNER_LINE + wasm_body + trailing_blanks,
        wasm=True,
    ) == expected_normalized + trailing_blanks
    native_banner = (
        b"Blender 5.2.0 LTS (hash fbe6228777e7 built 2026-07-14 01:31:22)\n"
    )
    timed_native = b".00:01.140  reports          | ERROR Array length mismatch\n"
    timed_wasm = b".00:03.769  reports          | ERROR Array length mismatch\n"
    timed_expected = b".<LOG_TIME>  reports          | ERROR Array length mismatch\n"
    assert m2.normalized_bytes(
        m2.ALLOCATOR_LINE + m2.WASM_BANNER_LINE + timed_wasm, wasm=True
    ) == timed_expected
    assert m2.normalized_bytes(
        timed_native + m2.ALLOCATOR_LINE + native_banner, wasm=False
    ) == timed_expected
    denoiser_warning = (
        b"00:01.002  bpy.rna          | WARNING current value '4' matches no enum in "
        b"'CyclesRenderSettings', '', 'denoiser'\n"
    )
    assert m2.normalized_bytes(
        m2.ALLOCATOR_LINE + m2.WASM_BANNER_LINE + denoiser_warning + wasm_body,
        wasm=True, suite=m2.NO_DENOISER_SUITE,
    ) == expected_normalized
    assert m2.NO_DENOISER_NORMALIZED_LINE in m2.normalized_bytes(
        m2.ALLOCATOR_LINE + m2.WASM_BANNER_LINE + denoiser_warning,
        wasm=True, suite="script_pyapi_bpy_app",
    )
    assert m2.normalized_bytes(
        b"before\n" + m2.ALLOCATOR_LINE + native_banner + b"after\n", wasm=False
    ) == b"before\nafter\n"
    assert m2.normalized_bytes(
        b"before\n" + m2.ALLOCATOR_LINE + m2.WASM_BANNER_LINE
        + b"00:10.327  translation      | WARNING 'locale' data path for translations not found\n"
        + b"after\n", wasm=True
    ) == b"before\nafter\n"
    # Normalization may remove only the exact, position-bound runtime envelope.
    # Failure signatures and unknown/near-match warnings remain byte-visible.
    for signature in (
        b"FAILED (failures=1)\n",
        b"Traceback (most recent call last):\n  File \"fixture.py\", line 1\nAssertionError: boom\n",
        b"WARNING fixture test warning\n",
        b'Add-on not loaded: "cycles", cause: No module named \'cycles-extra\'\n',
        b'Add-on not loaded: "cycles", cause: No module named \'cycles\'\n',
        b"0:01.123  reports          | WARNING malformed short clock\n",
        b"00:01.12  reports          | WARNING malformed fractional clock\n",
        b"00:01.123 reports          | WARNING malformed separator\n",
        b"ERROR:root:code for hash fixture_hash was not found.\n",
        b"Traceback (most recent call last):\n  File \"fixture.py\", line 1\nValueError: unsupported hash type fixture_hash\n",
        b"Traceback (most recent call last):\n  File \"fixture.py\", line 1\nModuleNotFoundError: No module named '_multiprocessing'; REAL FAILURE\n",
        b"fixture.py:1: physical_memory: AssertionError: boom\n",
        b"Blender 5.2.0 LTS (hash deadbeefdead built 2099-01-01 00:00:00)\n",
    ):
        adversarial = m2.ALLOCATOR_LINE + m2.WASM_BANNER_LINE + signature
        assert signature in m2.normalized_bytes(adversarial, wasm=True)
    exact_multiprocessing_noise = (
        b"Traceback (most recent call last):\n"
        b"  File \"fixture.py\", line 1\n"
        b"ModuleNotFoundError: No module named '_multiprocessing'\n"
    )
    assert m2.normalized_bytes(
        m2.ALLOCATOR_LINE + m2.WASM_BANNER_LINE + exact_multiprocessing_noise,
        wasm=True,
    ) == b""
    reject("m2_normalizer_wrong_native_banner", lambda: m2.normalized_bytes(
        native_body + m2.ALLOCATOR_LINE
        + b"Blender 5.2.0 LTS (hash deadbeefdead built 2026-07-14 01:31:22)\n",
        wasm=False,
    ))
    reject("m2_normalizer_misplaced_locale_warning", lambda: m2.normalized_bytes(
        m2.ALLOCATOR_LINE + m2.WASM_BANNER_LINE + b"test output\n"
        + b"00:10.327  translation      | WARNING 'locale' data path for translations not found\n",
        wasm=True,
    ))
    reject("m2_normalizer_missing_scoped_denoiser_warning", lambda: m2.normalized_bytes(
        m2.ALLOCATOR_LINE + m2.WASM_BANNER_LINE + wasm_body,
        wasm=True, suite=m2.NO_DENOISER_SUITE,
    ))
    reject("m2_normalizer_duplicate_scoped_denoiser_warning", lambda: m2.normalized_bytes(
        m2.ALLOCATOR_LINE + m2.WASM_BANNER_LINE
        + denoiser_warning + denoiser_warning + wasm_body,
        wasm=True, suite=m2.NO_DENOISER_SUITE,
    ))
    reject("m2_normalizer_duplicate_banner_pair", lambda: m2.normalized_bytes(
        m2.ALLOCATOR_LINE + m2.WASM_BANNER_LINE
        + m2.ALLOCATOR_LINE + m2.WASM_BANNER_LINE,
        wasm=True,
    ))

    native_scratch = Path("/fixture/m2/scratch/blendfile_io/native")
    wasm_scratch = Path("/fixture/m2/scratch/blendfile_io/wasm")
    native_paths = b"".join(
        str(native_scratch / f"fixture-{number}.blend").encode() + b"\n"
        for number in range(m2.SCRATCH_ROOT_OCCURRENCES)
    )
    wasm_paths = b"".join(
        str(wasm_scratch / f"fixture-{number}.blend").encode() + b"\n"
        for number in range(m2.SCRATCH_ROOT_OCCURRENCES)
    )
    native_scratch_raw = (
        native_paths + m2.ALLOCATOR_LINE
        + b"Blender 5.2.0 LTS (hash fbe6228777e7 built 2026-07-14 01:31:22)\n"
    )
    wasm_scratch_raw = m2.ALLOCATOR_LINE + m2.WASM_BANNER_LINE + wasm_paths
    expected_scratch = b"".join(
        m2.SCRATCH_ROOT_TOKEN + f"/fixture-{number}.blend\n".encode()
        for number in range(m2.SCRATCH_ROOT_OCCURRENCES)
    )
    assert m2.normalized_bytes(
        native_scratch_raw, wasm=False, suite=m2.SCRATCH_ROOT_SUITE,
        scratch_root=native_scratch,
    ) == expected_scratch
    assert m2.normalized_bytes(
        wasm_scratch_raw, wasm=True, suite=m2.SCRATCH_ROOT_SUITE,
        scratch_root=wasm_scratch,
    ) == expected_scratch
    near_match = str(native_scratch.parent / "native-other/visible.blend").encode()
    assert near_match in m2.normalized_bytes(
        near_match + b"\n" + native_scratch_raw,
        wasm=False, suite=m2.SCRATCH_ROOT_SUITE, scratch_root=native_scratch,
    )
    arbitrary_path = b"/arbitrary/unowned/path/visible.blend"
    assert arbitrary_path in m2.normalized_bytes(
        arbitrary_path + b"\n" + native_scratch_raw,
        wasm=False, suite=m2.SCRATCH_ROOT_SUITE, scratch_root=native_scratch,
    )
    reject("m2_scratch_root_missing_occurrence", lambda: m2.normalized_bytes(
        native_scratch_raw.replace(
            str(native_scratch / "fixture-0.blend").encode(), b"/wrong/fixture-0.blend"
        ),
        wasm=False, suite=m2.SCRATCH_ROOT_SUITE, scratch_root=native_scratch,
    ))
    reject("m2_scratch_root_extra_occurrence", lambda: m2.normalized_bytes(
        native_scratch_raw + str(native_scratch / "extra.blend").encode() + b"\n",
        wasm=False, suite=m2.SCRATCH_ROOT_SUITE, scratch_root=native_scratch,
    ))
    reject("m2_scratch_root_reserved_token_in_raw", lambda: m2.normalized_bytes(
        native_scratch_raw + m2.SCRATCH_ROOT_TOKEN + b"\n",
        wasm=False, suite=m2.SCRATCH_ROOT_SUITE, scratch_root=native_scratch,
    ))

    animation_scratch = Path("/fixture/m2/scratch/bl_animation_action/native")
    animation_path = (
        animation_scratch / "bl_animation_action/liboverride-action-slot.blend"
    )
    animation_raw_line = (
        b'00:00.817  blend            | Read blend: "'
        + os.fsencode(animation_path) + b'"\n'
    )
    animation_raw = (
        animation_raw_line + m2.ALLOCATOR_LINE
        + b"Blender 5.2.0 LTS (hash fbe6228777e7 built 2026-07-14 01:31:22)\n"
    )
    assert m2.normalized_bytes(
        animation_raw, wasm=False, suite="bl_animation_action",
        scratch_root=animation_scratch,
    ) == m2.ANIMATION_TEMP_READ
    animation_near_match = os.fsencode(
        animation_scratch.parent / "native-other/visible.blend"
    )
    assert animation_near_match in m2.normalized_bytes(
        animation_near_match + b"\n" + animation_raw,
        wasm=False, suite="bl_animation_action", scratch_root=animation_scratch,
    )
    reject("m2_animation_scratch_root_missing_occurrence", lambda: m2.normalized_bytes(
        animation_raw.replace(os.fsencode(animation_scratch), b"/wrong/scratch", 1),
        wasm=False, suite="bl_animation_action", scratch_root=animation_scratch,
    ))
    reject("m2_animation_scratch_root_extra_occurrence", lambda: m2.normalized_bytes(
        animation_raw + os.fsencode(animation_scratch / "extra.blend") + b"\n",
        wasm=False, suite="bl_animation_action", scratch_root=animation_scratch,
    ))
    reject("m2_animation_scratch_root_reserved_token_in_raw", lambda: m2.normalized_bytes(
        animation_raw + m2.SCRATCH_ROOT_TOKEN + b"\n",
        wasm=False, suite="bl_animation_action", scratch_root=animation_scratch,
    ))

    liblink_scratch = Path("/fixture/m2/scratch/blendfile_liblink/native")
    liblink_paths = b"".join(
        os.fsencode(liblink_scratch / f"blendfile_io/fixture-{number}.blend") + b"\n"
        for number in range(m2.SCRATCH_ROOT_POLICIES["blendfile_liblink"])
    )
    liblink_raw = (
        liblink_paths + m2.ALLOCATOR_LINE
        + b"Blender 5.2.0 LTS (hash fbe6228777e7 built 2026-07-14 01:31:22)\n"
    )
    expected_liblink = b"".join(
        m2.SCRATCH_ROOT_TOKEN + f"/blendfile_io/fixture-{number}.blend\n".encode()
        for number in range(m2.SCRATCH_ROOT_POLICIES["blendfile_liblink"])
    )
    assert m2.normalized_bytes(
        liblink_raw, wasm=False, suite="blendfile_liblink",
        scratch_root=liblink_scratch,
    ) == expected_liblink
    liblink_near_match = os.fsencode(
        liblink_scratch.parent / "native-other/visible.blend"
    )
    assert liblink_near_match in m2.normalized_bytes(
        liblink_near_match + b"\n" + liblink_raw,
        wasm=False, suite="blendfile_liblink", scratch_root=liblink_scratch,
    )
    reject("m2_liblink_scratch_root_missing_occurrence", lambda: m2.normalized_bytes(
        liblink_raw.replace(os.fsencode(liblink_scratch), b"/wrong/scratch", 1),
        wasm=False, suite="blendfile_liblink", scratch_root=liblink_scratch,
    ))
    reject("m2_liblink_scratch_root_extra_occurrence", lambda: m2.normalized_bytes(
        liblink_raw + os.fsencode(liblink_scratch / "extra.blend") + b"\n",
        wasm=False, suite="blendfile_liblink", scratch_root=liblink_scratch,
    ))
    reject("m2_liblink_scratch_root_reserved_token_in_raw", lambda: m2.normalized_bytes(
        liblink_raw + m2.SCRATCH_ROOT_TOKEN + b"\n",
        wasm=False, suite="blendfile_liblink", scratch_root=liblink_scratch,
    ))

    library_sets_canonical = b"\n".join(
        [m2.LIBRARY_OVERRIDE_SET_CANONICAL]
        * m2.LIBRARY_OVERRIDE_SET_OCCURRENCES
    ) + b"\n"
    library_sets_reversed = b"\n".join(
        [m2.LIBRARY_OVERRIDE_SET_REVERSED]
        * m2.LIBRARY_OVERRIDE_SET_OCCURRENCES
    ) + b"\n"
    assert m2.canonicalize_library_override_sets(
        library_sets_reversed
    ) == library_sets_canonical
    assert m2.canonicalize_library_override_sets(
        library_sets_canonical
    ) == library_sets_canonical
    reject(
        "m2_library_set_missing_occurrence",
        lambda: m2.canonicalize_library_override_sets(
            library_sets_reversed.replace(m2.LIBRARY_OVERRIDE_SET_REVERSED, b"", 1)
        ),
    )
    reject(
        "m2_library_set_extra_occurrence",
        lambda: m2.canonicalize_library_override_sets(
            library_sets_reversed + m2.LIBRARY_OVERRIDE_SET_REVERSED + b"\n"
        ),
    )
    reject(
        "m2_library_set_mixed_order",
        lambda: m2.canonicalize_library_override_sets(
            library_sets_reversed.replace(
                m2.LIBRARY_OVERRIDE_SET_REVERSED,
                m2.LIBRARY_OVERRIDE_SET_CANONICAL,
                1,
            )
        ),
    )
    library_set_near = b"{'IDPOINTER_ITEM_USE_ID', 'UNKNOWN'}"
    assert library_set_near in m2.canonicalize_library_override_sets(
        library_sets_reversed + library_set_near + b"\n"
    )

    # Exact structured canonicalizers: known record inventories may reorder,
    # while unknown content, duplicate rows, or changed cardinality stays red.
    keymap_first = [f"\tFixture Keymap {number:03d}\n".encode() for number in range(159)]
    keymap_second = [
        f"    ('Fixture {number:03d}', 'EMPTY', 'WINDOW', []),\n".encode()
        for number in range(28)
    ]
    keymap_ordered = b"".join([
        m2.KEYMAP_FIRST_HEADER, *keymap_first, m2.KEYMAP_SECOND_HEADER,
        *keymap_second, *m2.KEYMAP_TAIL,
    ])
    keymap_reversed = b"".join([
        m2.KEYMAP_FIRST_HEADER, *reversed(keymap_first), m2.KEYMAP_SECOND_HEADER,
        *reversed(keymap_second), *m2.KEYMAP_TAIL,
    ])
    assert m2.canonicalize_keymap_inventory(keymap_ordered) == m2.canonicalize_keymap_inventory(
        keymap_reversed
    )
    reject("m2_keymap_duplicate_inventory", lambda: m2.canonicalize_keymap_inventory(
        keymap_ordered.replace(keymap_first[1], keymap_first[0], 1)
    ))
    reject("m2_keymap_unknown_tail", lambda: m2.canonicalize_keymap_inventory(
        keymap_ordered + b"WARNING unexpected\n"
    ))

    def physics_body(suite: str) -> bytes:
        blend_file, tests = m2.PHYSICS_ORDER[suite]
        lines = [
            f'<LOG_TIME>  blend            | Read blend: "<REPO>/upstream/tests/files/physics/{blend_file}"\n'.encode(),
            b"\n",
        ]
        for test_name, frames in tests:
            lines.append(f"START {test_name} test.\n".encode())
            lines.extend(
                f"bake: frame {frame} :: {frames}\n".encode()
                for frame in range(1, frames + 1)
            )
            lines.extend([
                f"PASSED {test_name} test successfully.\n".encode(), b"Results:\n",
                b"Mesh Comparison : Same\n", b"Mesh Validation : Valid\n", b"\n", b"\n",
            ])
        lines.append(b"Blender quit\n")
        return b"".join(lines)

    for suite in m2.PHYSICS_ORDER:
        ordered = physics_body(suite)
        reordered = b"".join(reversed(ordered.splitlines(keepends=True)))
        assert m2.canonicalize_physics_records(ordered, suite) == m2.canonicalize_physics_records(
            reordered, suite
        )
    cloth = physics_body("physics_cloth")
    reject("m2_physics_missing_frame", lambda: m2.canonicalize_physics_records(
        cloth.replace(b"bake: frame 7 :: 15\n", b"", 1), "physics_cloth"
    ))
    reject("m2_physics_unknown_warning", lambda: m2.canonicalize_physics_records(
        cloth + b"WARNING unexpected\n", "physics_cloth"
    ))

    gtest_native = (
        b"[       OK ] complex_merge_case (0 ms)\n"
        b"[==========] 1 tests from 1 test case ran. (0 ms total)\n"
    )
    gtest_wasm = gtest_native.replace(b"(0 ms)", b"(3 ms)").replace(
        b"(0 ms total)", b"(4 ms total)"
    )
    gtest_expected = (
        b"[       OK ] complex_merge_case (<T> ms)\n"
        b"[==========] 1 tests from 1 test case ran. (<T> ms total)\n"
    )
    assert m2.normalized_bytes(
        gtest_native + m2.ALLOCATOR_LINE + native_banner, wasm=False,
        suite="object_modifier_array",
    ) == gtest_expected
    assert m2.normalized_bytes(
        m2.ALLOCATOR_LINE + m2.WASM_BANNER_LINE + gtest_wasm, wasm=True,
        suite="object_modifier_array",
    ) == gtest_expected
    gtest_near_match = b"[  INFO    ] complex_merge_case (3 ms)\n"
    assert gtest_near_match in m2.normalized_bytes(
        m2.ALLOCATOR_LINE + m2.WASM_BANNER_LINE + gtest_near_match, wasm=True,
    )

    registry = {
        item: {"id": item, **contract} for item, contract in m2.PASS_DELTA_LEDGER.items()
    }
    rna_native = b"prefix\n" + b"".join(m2.rna_menu_lines(m2.RNA_NATIVE_MENU)) + b"suffix\n"
    rna_wasm = b"prefix\n" + b"".join(m2.rna_menu_lines(m2.RNA_WASM_MENU)) + b"suffix\n"
    assert m2.pass_delta_records("bl_rna_paths", registry, rna_native, rna_wasm)[0] == [
        "os-shell-affordances"
    ]
    reject("m2_rna_menu_reordered", lambda: m2.pass_delta_records(
        "bl_rna_paths", registry, rna_native,
        rna_wasm.replace(
            m2.rna_menu_lines(m2.RNA_WASM_MENU)[0] + m2.rna_menu_lines(m2.RNA_WASM_MENU)[1],
            m2.rna_menu_lines(m2.RNA_WASM_MENU)[1] + m2.rna_menu_lines(m2.RNA_WASM_MENU)[0], 1,
        ),
    ))

    animation_info = m2.ANIMATION_INFO_LIBRARY
    animation_missing = m2.ANIMATION_MISSING_DATA
    native_group = (
        b"ERROR: one of the ID's for the groups to assign to is invalid "
        b"(ptr=0xADDR, val=0x0)\n"
    )
    wasm_group = native_group.replace(b"val=0x0", b"val=0")
    summary = b"----------------------------------------------------------------------\nRan 32 tests in <T>s\n\nOK\n"
    animation_native = b"prefix\n" + (
        b"." * 23 + m2.ANIMATION_REMAP_READ + m2.ANIMATION_SECOND_REMAP_READ
        + m2.ANIMATION_SAVED + m2.ANIMATION_TEMP_READ + animation_info
        + m2.ANIMATION_LAYERED_READ + summary + m2.ANIMATION_ASSIGNMENT_WARNING
        + native_group + m2.ANIMATION_FCURVE_ERROR
    )
    animation_wasm = b"prefix\n" + (
        b"." * 4 + m2.ANIMATION_ASSIGNMENT_WARNING + b"." * 6 + wasm_group
        + m2.ANIMATION_FCURVE_ERROR + b"." * 13 + m2.ANIMATION_REMAP_READ
        + m2.ANIMATION_SECOND_REMAP_READ + m2.ANIMATION_SAVED
        + m2.ANIMATION_TEMP_READ + m2.ANIMATION_OBJECTDATA_WARNING + animation_info
        + animation_missing + m2.ANIMATION_LAYERED_READ + summary
    )
    assert m2.pass_delta_records(
        "bl_animation_action", registry, animation_native, animation_wasm
    )[0] == ["wasm32-animation-action-objectdata"]
    reject("m2_animation_warning_relocated", lambda: m2.pass_delta_records(
        "bl_animation_action", registry, animation_native,
        animation_wasm.replace(m2.ANIMATION_OBJECTDATA_WARNING, b"", 1)
        + m2.ANIMATION_OBJECTDATA_WARNING,
    ))
    native_library_phase = m2.ANIMATION_TEMP_READ + animation_info + m2.ANIMATION_LAYERED_READ
    wasm_library_phase = (
        m2.ANIMATION_TEMP_READ + m2.ANIMATION_OBJECTDATA_WARNING + animation_info
        + animation_missing + m2.ANIMATION_LAYERED_READ
    )
    relocated_native_phase = animation_native.replace(native_library_phase, b"", 1).replace(
        b"prefix\n", b"prefix\n" + native_library_phase, 1
    )
    relocated_wasm_phase = animation_wasm.replace(wasm_library_phase, b"", 1).replace(
        b"prefix\n", b"prefix\n" + wasm_library_phase, 1
    )
    reject("m2_animation_whole_phase_relocated", lambda: m2.pass_delta_records(
        "bl_animation_action", registry, relocated_native_phase, relocated_wasm_phase,
    ))

    library_following = b"library-shared-following\n"
    library_prefix = b"".join(
        f"library-prefix-{number:02d}\n".encode()
        for number in range(m2.LIBRARY_OVERRIDE_PHASE_BEFORE_INDEX)
    )
    library_native_phase = b"".join(m2.LIBRARY_OVERRIDE_NATIVE_PHASE)
    library_wasm_phase = b"".join(m2.LIBRARY_OVERRIDE_WASM_PHASE)
    library_native = (
        library_prefix + m2.LIBRARY_OVERRIDE_PHASE_BEFORE + library_native_phase
        + m2.LIBRARY_OVERRIDE_PHASE_AFTER + library_following + b"suffix\n"
    )
    library_wasm = (
        library_prefix + m2.LIBRARY_OVERRIDE_PHASE_BEFORE + library_wasm_phase
        + m2.LIBRARY_OVERRIDE_PHASE_AFTER + library_following + b"suffix\n"
    )
    assert m2.pass_delta_records(
        "blendfile_library_overrides", registry, library_native, library_wasm
    )[0] == ["wasm32-library-override-idname-allocation"]
    reject("m2_library_association_changed", lambda: m2.pass_delta_records(
        "blendfile_library_overrides", registry, library_native,
        library_wasm.replace(
            m2.LIBRARY_OVERRIDE_WASM_PHASE[1],
            m2.LIBRARY_OVERRIDE_NATIVE_PHASE[1], 1,
        ),
    ))
    reject("m2_library_block_relocated", lambda: m2.pass_delta_records(
        "blendfile_library_overrides", registry, library_native,
        library_wasm.replace(
            library_wasm_phase,
            b"".join([
                m2.LIBRARY_OVERRIDE_WASM_PHASE[0],
                m2.LIBRARY_OVERRIDE_WASM_PHASE[2],
                m2.LIBRARY_OVERRIDE_WASM_PHASE[1],
                *m2.LIBRARY_OVERRIDE_WASM_PHASE[3:],
            ]), 1,
        ),
    ))
    def relocate_library_phase(payload: bytes, phase: bytes) -> bytes:
        without = payload.replace(phase, b"", 1)
        return without.replace(library_following, library_following + phase, 1)

    reject("m2_library_whole_phase_relocated", lambda: m2.pass_delta_records(
        "blendfile_library_overrides", registry,
        relocate_library_phase(library_native, library_native_phase),
        relocate_library_phase(library_wasm, library_wasm_phase),
    ))
    resolved_registry = {key: dict(value) for key, value in registry.items()}
    resolved_registry["wasm32-animation-action-objectdata"] = dict(
        resolved_registry["wasm32-animation-action-objectdata"], status="resolved"
    )
    reject("m2_pass_delta_resolved_status", lambda: m2.pass_delta_records(
        "bl_animation_action", resolved_registry, animation_native, animation_wasm
    ))
    reject("m2_deps_skipped_nonruntime_missing_source", lambda:
           m2deps.require_dependency_notice_source("epoxy-fixture", {
               "status": "skipped", "shipped": False, "notes": "not runtime-linked",
           }))

    with tempfile.TemporaryDirectory(prefix="final-m0-m3-runners-") as temp:
        root = Path(temp)

        linux_libdir = root / "linux-libdir"
        (linux_libdir / "zeta/lib").mkdir(parents=True)
        (linux_libdir / "alpha/lib").mkdir(parents=True)
        library_dirs = m1.linux_bundled_library_dirs(linux_libdir)
        assert library_dirs == [
            (linux_libdir / "alpha/lib").resolve(),
            (linux_libdir / "zeta/lib").resolve(),
        ]
        loader_env = m1.environment_with_library_dirs(
            {"PATH": "/fixture/bin", "LD_LIBRARY_PATH": "/fixture/fallback"},
            library_dirs,
        )
        assert loader_env == {
            "PATH": "/fixture/bin",
            "LD_LIBRARY_PATH": os.pathsep.join([
                os.fspath(library_dirs[0]),
                os.fspath(library_dirs[1]),
                "/fixture/fallback",
            ]),
        }
        reject("m1_linux_loader_empty", lambda: m1.environment_with_library_dirs({}, []))

        def device_limit_fixture(label: str) -> dict[str, Path]:
            fixture_root = root / label
            fields = m3.WEBGPU_DEVICE_LIMIT_FIELDS
            cpp = "".join(
                f"required_limits.{field} = supported_limits.{field};\n"
                for field in fields
            )
            paths = {
                "native_context": fixture_root / "GHOST_ContextWGPU.cc",
                "web_fallback": fixture_root / "GHOST_ContextWGPUWeb.cc",
                "worker_preinit": fixture_root / "wgpu-preinit-worker.js",
            }
            fixture_root.mkdir()
            paths["native_context"].write_text(
                cpp + "device_desc.requiredLimits = &required_limits;\n"
            )
            paths["web_fallback"].write_text(
                cpp + "desc.requiredLimits = &required_limits;\n"
            )
            paths["worker_preinit"].write_text(
                "var requiredLimits = {\n"
                + "".join(
                    f"  {field}: adapter.limits.{field},\n" for field in fields
                )
                + "};\nadapter.requestDevice({requiredLimits: requiredLimits,});\n"
            )
            return paths

        canonical_limits = device_limit_fixture("device-limits-positive")
        m3.require_webgpu_device_limit_contract(canonical_limits)

        def reject_limit_contract(label: str, key: str, change) -> None:
            paths = device_limit_fixture(label)
            path = paths[key]
            path.write_text(change(path.read_text()))
            m3.require_webgpu_device_limit_contract(paths)

        first_limit = m3.WEBGPU_DEVICE_LIMIT_FIELDS[0]
        second_limit = m3.WEBGPU_DEVICE_LIMIT_FIELDS[1]
        reject("m3_device_limits_missing_native", lambda: reject_limit_contract(
            "device-limits-missing", "native_context", lambda text: text.replace(
                f"required_limits.{first_limit} = supported_limits.{first_limit};\n", "", 1
            )))
        reject("m3_device_limits_duplicate_fallback", lambda: reject_limit_contract(
            "device-limits-duplicate", "web_fallback", lambda text: text.replace(
                f"required_limits.{first_limit} = supported_limits.{first_limit};\n",
                f"required_limits.{first_limit} = supported_limits.{first_limit};\n" * 2,
                1,
            )))
        reject("m3_device_limits_wrong_cpp_source", lambda: reject_limit_contract(
            "device-limits-source", "native_context", lambda text: text.replace(
                f"supported_limits.{second_limit}", f"device_limits.{second_limit}", 1
            )))
        reject("m3_device_limits_wrong_worker_value", lambda: reject_limit_contract(
            "device-limits-worker", "worker_preinit", lambda text: text.replace(
                f"adapter.limits.{second_limit}", f"adapter.limits.{first_limit}", 1
            )))

        def cache_marker_fixture(label: str) -> Path:
            path = root / label / "wgpu_shader_compiler.cc"
            path.parent.mkdir()
            path.write_text(
                "bool emit_cache_result(const std::string &name) {\n"
                '  const char *census_dir = std::getenv("BW_SHADER_CACHE_CENSUS_DIR");\n'
                "  if (census_dir == nullptr) { return true; }\n"
                '  const char *active_dir = std::getenv("BW_SHADER_CACHE_DIR");\n'
                "  if (active_dir == nullptr || active_dir[0] == '\\0' || "
                "std::strcmp(active_dir, census_dir) != 0) { return false; }\n"
                "  return true;\n}\n"
                "void compile() { if (emit_cache_result(sources.name)) {} }\n",
                encoding="utf-8",
            )
            return path

        canonical_marker = cache_marker_fixture("cache-marker-positive")
        m3.require_cache_marker_activation_contract(canonical_marker)

        def reject_marker_contract(label: str, change) -> None:
            path = cache_marker_fixture(label)
            path.write_text(change(path.read_text(encoding="utf-8")), encoding="utf-8")
            m3.require_cache_marker_activation_contract(path)

        reject("m3_cache_marker_pre_activation_not_suppressed", lambda:
               reject_marker_contract(
                   "cache-marker-preactivation",
                   lambda text: text.replace("{ return false; }", "{ return true; }", 1),
               ))
        reject("m3_cache_marker_wrong_active_directory_accepted", lambda:
               reject_marker_contract(
                   "cache-marker-wrong-directory",
                   lambda text: text.replace(
                       "std::strcmp(active_dir, census_dir) != 0", "active_dir == census_dir", 1
                   ),
               ))

        canonical_m3_cache = root / "m3-canonical-CMakeCache.txt"
        canonical_m3_cache.write_text(
            "CMAKE_BUILD_TYPE:STRING=Release\n"
            "CMAKE_GENERATOR:INTERNAL=Ninja\n"
            f"CMAKE_HOME_DIRECTORY:INTERNAL={(root / 'upstream').resolve()}\n"
            "WITH_GTESTS:BOOL=ON\n"
            "WITH_GPU_BACKEND_TESTS:BOOL=ON\n"
            "WITH_GPU_DRAW_TESTS:BOOL=ON\n"
            "WITH_OPENSUBDIV:BOOL=ON\n"
            "WITH_WEBGPU_BACKEND:BOOL=ON\n"
        )
        m3.require_m3_cmake_cache(canonical_m3_cache, root=root)
        opensubdiv_off_cache = root / "m3-opensubdiv-off-CMakeCache.txt"
        opensubdiv_off_cache.write_text(
            canonical_m3_cache.read_text().replace(
                "WITH_OPENSUBDIV:BOOL=ON", "WITH_OPENSUBDIV:BOOL=OFF", 1
            )
        )
        reject("m3_opensubdiv_disabled", lambda:
               m3.require_m3_cmake_cache(opensubdiv_off_cache, root=root))
        draw_tests_off_cache = root / "m3-draw-tests-off-CMakeCache.txt"
        draw_tests_off_cache.write_text(
            canonical_m3_cache.read_text().replace(
                "WITH_GPU_DRAW_TESTS:BOOL=ON", "WITH_GPU_DRAW_TESTS:BOOL=OFF", 1
            )
        )
        reject("m3_gpu_draw_tests_disabled", lambda:
               m3.require_m3_cmake_cache(draw_tests_off_cache, root=root))

        osd_members = "version.cpp.o\nglslPatchShaderSource.cpp.o\n"
        osd_defined = (
            "00000ca1 T OpenSubdiv::v3_7_0::Osd::GLSLPatchShaderSource::"
            "GetPatchBasisShaderSource()\n"
        )
        osd_undefined = "glslPatchShaderSource.cpp.o:\n U _Znwm\n"
        osd_smoke = (
            "OSD_WASM_REFINE nverts_level1=26 glsl_bytes=4096 param=1 evaluate=1\n"
        )
        m3.require_opensubdiv_binary_proof(
            osd_members, osd_defined, osd_undefined, osd_smoke
        )
        reject("m3_opensubdiv_missing_glsl_member", lambda:
               m3.require_opensubdiv_binary_proof(
                   "version.cpp.o\n", osd_defined, osd_undefined, osd_smoke))
        reject("m3_opensubdiv_missing_defined_symbol", lambda:
               m3.require_opensubdiv_binary_proof(
                   osd_members, "", osd_undefined, osd_smoke))
        reject("m3_opensubdiv_gl_api_import", lambda:
               m3.require_opensubdiv_binary_proof(
                   osd_members, osd_defined, osd_undefined + " U _glCreateShader\n",
                   osd_smoke))
        reject("m3_opensubdiv_bad_wasm_smoke", lambda:
               m3.require_opensubdiv_binary_proof(
                   osd_members, osd_defined, osd_undefined,
                   osd_smoke.replace("evaluate=1", "evaluate=0")))

        canonical_runtime = root / "canonical-runtime"
        canonical_runtime.write_text("canonical")
        canonical_runtime = canonical_runtime.resolve()
        alternate_runtime = root / "alternate-runtime"
        alternate_runtime.write_text("canonical")
        alternate_runtime = alternate_runtime.resolve()
        assert m1.canonical_file(
            canonical_runtime, canonical_runtime, "fixture runtime"
        ) == canonical_runtime
        assert m2.canonical_file(
            canonical_runtime, canonical_runtime, "fixture runtime"
        ) == canonical_runtime
        reject("m1_runtime_alternate_path", lambda: m1.canonical_file(
            alternate_runtime, canonical_runtime, "fixture runtime"))
        reject("m2_runtime_alternate_path", lambda: m2.canonical_file(
            alternate_runtime, canonical_runtime, "fixture runtime"))
        gtest = root / "gtest.json"
        gtest.write_text(json.dumps({
            "tests": 1, "failures": 0,
            "testsuites": [{"name": "Suite", "testsuite": [
                {"name": "First", "status": "RUN", "result": "COMPLETED"}
            ]}],
        }))
        assert m1.parse_gtest_json(gtest) == (1, 0, {"Suite.First"})
        duplicate_json = root / "gtest-duplicate.json"
        duplicate_json.write_text(json.dumps({
            "tests": 2, "failures": 0,
            "testsuites": [{"name": "Suite", "testsuite": [
                {"name": "First", "status": "RUN", "result": "COMPLETED"},
                {"name": "First", "status": "RUN", "result": "COMPLETED"},
            ]}],
        }))
        assert m1.parse_gtest_json(duplicate_json) == (
            2, 0, {"Suite.First@occurrence=1", "Suite.First@occurrence=2"})
        bad_counter = root / "gtest-bad.json"
        bad_counter.write_text(gtest.read_text().replace('"tests": 1', '"tests": 2'))
        reject("gtest_counter_tamper", lambda: m1.parse_gtest_json(bad_counter))

        assets = root / "upstream/tests/files"
        assets.mkdir(parents=True)
        canonical_assets = ["--test-assets-dir", str(assets.resolve())]
        assert m1.require_gtest_arguments(
            "blenlib", canonical_assets, root=root
        ) == canonical_assets
        assert m1.require_gtest_arguments("bmesh_core", [], root=root) == []
        reject("gtest_assets_missing_argument", lambda: m1.require_gtest_arguments(
            "blenlib", [], root=root))
        reject("gtest_assets_wrong_argument", lambda: m1.require_gtest_arguments(
            "blenlib", ["--test-assets-dir", str(root / "upstream/tests")], root=root))
        real_assets = root / "real-test-assets"
        real_assets.mkdir()
        assets.rmdir()
        assets.symlink_to(real_assets, target_is_directory=True)
        reject("gtest_assets_symlink", lambda: m1.canonical_gtest_arguments(
            "blenlib", root=root))
        assets.unlink()
        assets.mkdir()

        native_artifact = root / "native/bin/tests/BLI_test"
        native_artifact.parent.mkdir(parents=True)
        native_artifact.write_text("native")
        (root / "native/CMakeCache.txt").write_text(
            f"CMAKE_BUILD_TYPE:STRING=Release\nCMAKE_GENERATOR:INTERNAL=Ninja\n"
            f"CMAKE_HOME_DIRECTORY:INTERNAL={root / 'upstream'}\nWITH_GMP:BOOL=OFF\n"
            "WITH_TESTS_SINGLE_BINARY:BOOL=ON\nWITH_TESTS_BMESH_CORE_PARITY:BOOL=ON\n")
        wasm_artifact = root / "wasm/bin/tests/BLI_test.js"
        wasm_artifact.parent.mkdir(parents=True)
        wasm_artifact.write_text("wasm")
        (root / "wasm/CMakeCache.txt").write_text(
            f"CMAKE_BUILD_TYPE:STRING=Release\nCMAKE_GENERATOR:INTERNAL=Ninja\n"
            f"CMAKE_HOME_DIRECTORY:INTERNAL={root / 'upstream'}\n"
            f"CMAKE_TOOLCHAIN_FILE:FILEPATH={m1.ROOT / 'tools/emsdk/upstream/emscripten/cmake/Modules/Platform/Emscripten.cmake'}\n"
            "WITH_GMP:BOOL=OFF\nWITH_TESTS_SINGLE_BINARY:BOOL=ON\n"
            "WITH_TESTS_BMESH_CORE_PARITY:BOOL=ON\n")
        native_config = m1.cmake_configuration(
            native_artifact, wasm=False, expected_source=root / "upstream")[1]
        wasm_config = m1.cmake_configuration(
            wasm_artifact, wasm=True, expected_source=root / "upstream")[1]
        assert native_config["toolchain"] == "native"
        assert wasm_config["toolchain"] == "emscripten"
        m1.require_parity_build_contract(
            "blenlib", native_artifact, wasm_artifact, native_config, wasm_config)
        reject("cmake_wrong_toolchain", lambda: m1.cmake_configuration(
            native_artifact, wasm=True, expected_source=root / "upstream"))
        duplicate_cache = root / "duplicate/bin/tests/BLI_test"
        duplicate_cache.parent.mkdir(parents=True)
        duplicate_cache.write_text("native")
        (root / "duplicate/CMakeCache.txt").write_text(
            f"CMAKE_BUILD_TYPE:STRING=Release\nCMAKE_GENERATOR:INTERNAL=Ninja\n"
            f"CMAKE_HOME_DIRECTORY:INTERNAL={root / 'upstream'}\n"
            "WITH_GMP:BOOL=OFF\nWITH_GMP:BOOL=ON\n"
            "WITH_TESTS_SINGLE_BINARY:BOOL=ON\nWITH_TESTS_BMESH_CORE_PARITY:BOOL=ON\n")
        reject("cmake_duplicate_key", lambda: m1.cmake_configuration(
            duplicate_cache, wasm=False, expected_source=root / "upstream"))
        disabled_config = dict(native_config, with_tests_bmesh_core_parity=False)
        reject("cmake_bmesh_parity_disabled", lambda: m1.require_parity_build_contract(
            "blenlib", native_artifact, wasm_artifact, disabled_config, wasm_config))
        reject("bmesh_monolithic_mislabeled", lambda: m1.require_parity_build_contract(
            "bmesh_core", native_artifact.with_name("blender_test"), wasm_artifact,
            native_config, wasm_config))
        m1.require_allocator_contract(
            "  LINK_FLAGS = -pthread -sMALLOC=mimalloc", "blenlib", wasm=True)
        m1.require_allocator_contract(
            "  LINK_FLAGS = -pthread -sMALLOC=mimalloc -sMALLOC=dlmalloc -sINITIAL_MEMORY=33554432",
            "bmesh_core", wasm=True)
        m1.require_allocator_contract("  LINK_FLAGS = -pthread", "bmesh_core", wasm=False)
        m1.require_initial_memory_contract(
            "  LINK_FLAGS = -pthread -sMALLOC=mimalloc -sMALLOC=dlmalloc -sINITIAL_MEMORY=33554432",
            "bmesh_core", wasm=True)
        m1.require_initial_memory_contract(
            "  LINK_FLAGS = -pthread", "blenlib", wasm=True)
        m1.require_initial_memory_contract(
            "  LINK_FLAGS = -pthread", "bmesh_core", wasm=False)
        assert m1.emscripten_setting_values(
            "-sMALLOC=mimalloc -s MALLOC=dlmalloc", "MALLOC"
        ) == ["mimalloc", "dlmalloc"]
        reject("bmesh_allocator_override_missing", lambda: m1.require_allocator_contract(
            "  LINK_FLAGS = -pthread -sMALLOC=mimalloc", "bmesh_core", wasm=True))
        reject("bmesh_allocator_wrong_last", lambda: m1.require_allocator_contract(
            "  LINK_FLAGS = -pthread -sMALLOC=dlmalloc -sMALLOC=mimalloc",
            "bmesh_core", wasm=True))
        for token, suffix in (
            ("bmesh_allocator_late_split_equals", "-s MALLOC=mimalloc"),
            ("bmesh_allocator_late_split_bare", "-s MALLOC mimalloc"),
            ("bmesh_allocator_late_compact_bare", "-sMALLOC mimalloc"),
        ):
            reject(token, lambda suffix=suffix: m1.require_allocator_contract(
                "  LINK_FLAGS = -sMALLOC=mimalloc -sMALLOC=dlmalloc " + suffix,
                "bmesh_core", wasm=True))
        reject("native_allocator_injection", lambda: m1.require_allocator_contract(
            "  LINK_FLAGS = -s MALLOC=dlmalloc", "bmesh_core", wasm=False))
        reject("bmesh_allocator_malformed_empty", lambda: m1.require_allocator_contract(
            "  LINK_FLAGS = -sMALLOC=mimalloc -sMALLOC=dlmalloc -sMALLOC=",
            "bmesh_core", wasm=True))
        reject("bmesh_allocator_bare_missing_value", lambda: m1.require_allocator_contract(
            "  LINK_FLAGS = -sMALLOC=mimalloc -sMALLOC=dlmalloc -s MALLOC",
            "bmesh_core", wasm=True))
        reject("bmesh_allocator_compact_bare_false_green", lambda: m1.require_allocator_contract(
            "  LINK_FLAGS = -sMALLOC mimalloc -sMALLOC dlmalloc",
            "bmesh_core", wasm=True))
        reject("bmesh_allocator_split_bare_false_green", lambda: m1.require_allocator_contract(
            "  LINK_FLAGS = -s MALLOC mimalloc -s MALLOC dlmalloc",
            "bmesh_core", wasm=True))
        reject("bmesh_initial_memory_missing", lambda: m1.require_initial_memory_contract(
            "  LINK_FLAGS = -sMALLOC=mimalloc -sMALLOC=dlmalloc",
            "bmesh_core", wasm=True))
        reject("bmesh_initial_memory_too_small", lambda: m1.require_initial_memory_contract(
            "  LINK_FLAGS = -sINITIAL_MEMORY=16777216",
            "bmesh_core", wasm=True))
        reject("bmesh_initial_memory_late_override", lambda: m1.require_initial_memory_contract(
            "  LINK_FLAGS = -sINITIAL_MEMORY=33554432 -s INITIAL_MEMORY=16777216",
            "bmesh_core", wasm=True))
        reject("bmesh_initial_memory_compact_bare_false_green", lambda: m1.require_initial_memory_contract(
            "  LINK_FLAGS = -sINITIAL_MEMORY 33554432",
            "bmesh_core", wasm=True))
        reject("bmesh_initial_memory_split_bare_false_green", lambda: m1.require_initial_memory_contract(
            "  LINK_FLAGS = -s INITIAL_MEMORY 33554432",
            "bmesh_core", wasm=True))
        reject("bmesh_initial_memory_legacy_alias", lambda: m1.require_initial_memory_contract(
            "  LINK_FLAGS = -sINITIAL_MEMORY=33554432 -sTOTAL_MEMORY=16777216",
            "bmesh_core", wasm=True))
        reject("bmesh_initial_memory_direct_linker", lambda: m1.require_initial_memory_contract(
            "  LINK_FLAGS = -sINITIAL_MEMORY=33554432 -Wl,--initial-memory=16777216",
            "bmesh_core", wasm=True))
        reject("bmesh_initial_memory_direct_linker_split", lambda: m1.require_initial_memory_contract(
            "  LINK_FLAGS = -sINITIAL_MEMORY=33554432 --initial-memory 16777216",
            "bmesh_core", wasm=True))
        reject("bli_initial_memory_injection", lambda: m1.require_initial_memory_contract(
            "  LINK_FLAGS = -sINITIAL_MEMORY=33554432", "blenlib", wasm=True))
        reject("native_initial_memory_injection", lambda: m1.require_initial_memory_contract(
            "  LINK_FLAGS = -sINITIAL_MEMORY=33554432", "bmesh_core", wasm=False))

        no_work_root = root / "build-native-m1-parity"
        no_work_target = "bin/tests/BLI_test"
        no_work_command = m1.ninja_locked_command("-n", no_work_target)
        m1.require_ninja_no_work_result(
            no_work_command,
            no_work_root,
            0,
            m1.NINJA_NO_WORK_STDOUT,
            b"",
            expected_build_root=no_work_root,
            expected_target=no_work_target,
        )
        reject("ninja_no_work_wrong_cwd", lambda: m1.require_ninja_no_work_result(
            no_work_command, root, 0, m1.NINJA_NO_WORK_STDOUT, b"",
            expected_build_root=no_work_root, expected_target=no_work_target))
        reject("ninja_no_work_raw_bypass", lambda: m1.require_ninja_no_work_result(
            ["ninja", "-n", no_work_target], no_work_root, 0,
            m1.NINJA_NO_WORK_STDOUT, b"", expected_build_root=no_work_root,
            expected_target=no_work_target))
        reject("ninja_no_work_stale", lambda: m1.require_ninja_no_work_result(
            no_work_command, no_work_root, 0,
            b"[1/1] Linking CXX executable bin/tests/BLI_test\n", b"",
            expected_build_root=no_work_root, expected_target=no_work_target))
        reject("ninja_no_work_nonzero", lambda: m1.require_ninja_no_work_result(
            no_work_command, no_work_root, 1, b"", b"ninja: error: failed\n",
            expected_build_root=no_work_root, expected_target=no_work_target))
        reject("ninja_no_work_wrong_target", lambda: m1.require_ninja_no_work_result(
            m1.ninja_locked_command("-n", "bin/tests/blender_test"), no_work_root, 0,
            m1.NINJA_NO_WORK_STDOUT, b"", expected_build_root=no_work_root,
            expected_target=no_work_target))
        reject("ninja_no_work_wrong_output", lambda: m1.require_ninja_no_work_result(
            no_work_command, no_work_root, 0, b"ninja: no work to do.\nextra\n", b"",
            expected_build_root=no_work_root, expected_target=no_work_target))
        reject("ninja_no_work_nonempty_stderr", lambda: m1.require_ninja_no_work_result(
            no_work_command, no_work_root, 0, m1.NINJA_NO_WORK_STDOUT,
            b"ninja: warning: unexpected diagnostic\n",
            expected_build_root=no_work_root, expected_target=no_work_target))

        m3_no_work_root = root / "build-native-gpu"
        m3_no_work_target = "blender_test"
        m3_no_work_command = m3.ninja_locked_command("-n", m3_no_work_target)
        m3.require_ninja_no_work_result(
            m3_no_work_command,
            m3_no_work_root,
            0,
            m3.NINJA_NO_WORK_STDOUT,
            b"",
            expected_build_root=m3_no_work_root,
            expected_target=m3_no_work_target,
        )
        reject("m3_ninja_no_work_stale_output", lambda:
               m3.require_ninja_no_work_result(
                   m3_no_work_command, m3_no_work_root, 0,
                   b"[1/1] Linking CXX executable bin/tests/blender_test\n", b"",
                   expected_build_root=m3_no_work_root,
                   expected_target=m3_no_work_target))
        reject("m3_ninja_no_work_wrong_root", lambda:
               m3.require_ninja_no_work_result(
                   m3_no_work_command, root, 0, m3.NINJA_NO_WORK_STDOUT, b"",
                   expected_build_root=m3_no_work_root,
                   expected_target=m3_no_work_target))
        reject("m3_ninja_no_work_raw_bypass", lambda:
               m3.require_ninja_no_work_result(
                   ["ninja", "-n", m3_no_work_target],
                   m3_no_work_root, 0, m3.NINJA_NO_WORK_STDOUT, b"",
                   expected_build_root=m3_no_work_root,
                   expected_target=m3_no_work_target))
        reject("m3_ninja_no_work_wrong_target", lambda:
               m3.require_ninja_no_work_result(
                   m3.ninja_locked_command("-n", "bin/tests/blender_test"),
                   m3_no_work_root, 0, m3.NINJA_NO_WORK_STDOUT, b"",
                   expected_build_root=m3_no_work_root,
                   expected_target=m3_no_work_target))
        reject("m3_ninja_no_work_nonzero", lambda:
               m3.require_ninja_no_work_result(
                   m3_no_work_command, m3_no_work_root, 1, b"",
                   b"ninja: error: failed\n",
                   expected_build_root=m3_no_work_root,
                   expected_target=m3_no_work_target))
        reject("m3_ninja_no_work_nonempty_stderr", lambda:
               m3.require_ninja_no_work_result(
                   m3_no_work_command, m3_no_work_root, 0,
                   m3.NINJA_NO_WORK_STDOUT,
                   b"ninja: warning: unexpected diagnostic\n",
                   expected_build_root=m3_no_work_root,
                   expected_target=m3_no_work_target))

        gpu_names = [f"test_{index:03d}" for index in range(m3.GPU_TEST_COUNT)]
        gpu_list = "GPUWebGPUTest.\n" + "".join(f"  {name}\n" for name in gpu_names)
        assert m3.parse_gpu_test_list(gpu_list) == gpu_names
        reject("gpu_list_unexpected_suite", lambda: m3.parse_gpu_test_list(
            gpu_list + "OtherSuite.\n  hidden\n"
        ))
        stale_gpu_list = (
            "GPUWebGPUTest.\n" + "".join(f"  {name}\n" for name in gpu_names[:-1])
        )
        reject("gpu_stale_196_census", lambda: m3.parse_gpu_test_list(stale_gpu_list))

        gpu_name = "GPUWebGPUTest.test_000"
        gpu_run = root / "gpu-webgpu-run.log"
        gpu_run.write_text(f"[ RUN      ] {gpu_name}\n[       OK ] {gpu_name} (1 ms)\n")
        m3.parse_gpu_webgpu_test_run(gpu_run, gpu_name)
        gpu_run_error = root / "gpu-webgpu-run-error.log"
        gpu_run_error.write_text(
            gpu_run.read_text()
            + "[WebGPU] uncaptured device error (type 2): delayed pipeline failure\n"
        )
        reject("gpu_pass_with_uncaptured_device_error", lambda:
               m3.parse_gpu_webgpu_test_run(gpu_run_error, gpu_name))
        gpu_run_leak = root / "gpu-webgpu-run-leak.log"
        gpu_run_leak.write_text(gpu_run.read_text() + "Error: Not freed memory blocks: 1\n")
        reject("gpu_pass_with_memory_leak", lambda:
               m3.parse_gpu_webgpu_test_run(gpu_run_leak, gpu_name))
        gpu_run_wrong = root / "gpu-webgpu-run-wrong.log"
        gpu_run_wrong.write_text(gpu_run.read_text().replace(
            gpu_name, "GPUWebGPUTest.test_001"
        ))
        reject("gpu_run_wrong_identity", lambda:
               m3.parse_gpu_webgpu_test_run(gpu_run_wrong, gpu_name))
        gpu_run_suffix = root / "gpu-webgpu-run-suffix.log"
        gpu_run_suffix.write_text(gpu_run.read_text().replace(gpu_name, gpu_name + "_SUFFIX"))
        reject("gpu_run_suffix_alias", lambda:
               m3.parse_gpu_webgpu_test_run(gpu_run_suffix, gpu_name))

        draw_list = (
            "DrawWebGPUTest.\n"
            "  draw_curves_lib\n"
            "  draw_debug_lifetime_rebind\n"
        )
        assert m3.parse_draw_webgpu_test_list(draw_list) == list(m3.DRAW_WEBGPU_TESTS)
        reject("draw_webgpu_missing_test", lambda: m3.parse_draw_webgpu_test_list(
            draw_list.replace("  draw_debug_lifetime_rebind\n", "", 1)))
        reject("draw_webgpu_stale_identity", lambda: m3.parse_draw_webgpu_test_list(
            draw_list.replace("draw_debug_lifetime_rebind", "draw_debug_display_only", 1)))
        reject("draw_webgpu_unexpected_suite", lambda: m3.parse_draw_webgpu_test_list(
            draw_list + "OtherSuite.\n  hidden\n"))
        draw_name = m3.DRAW_WEBGPU_TESTS[0]
        draw_run = root / "draw-webgpu-run.log"
        draw_run.write_text(
            f"[ RUN      ] {draw_name}\n[       OK ] {draw_name} (1 ms)\n"
        )
        m3.parse_draw_webgpu_test_run(draw_run, draw_name)
        draw_run_error = root / "draw-webgpu-run-error.log"
        draw_run_error.write_text(
            draw_run.read_text()
            + "[WebGPU] uncaptured device error (type 2): delayed draw failure\n"
        )
        reject("draw_webgpu_run_device_error", lambda:
               m3.parse_draw_webgpu_test_run(draw_run_error, draw_name))
        draw_run_leak = root / "draw-webgpu-run-leak.log"
        draw_run_leak.write_text(draw_run.read_text() + "Error: Not freed memory blocks: 1\n")
        reject("draw_webgpu_run_memory_leak", lambda:
               m3.parse_draw_webgpu_test_run(draw_run_leak, draw_name))
        draw_run_wrong = root / "draw-webgpu-run-wrong.log"
        draw_run_wrong.write_text(draw_run.read_text().replace(
            draw_name, m3.DRAW_WEBGPU_TESTS[1]
        ))
        reject("draw_webgpu_run_wrong_identity", lambda:
               m3.parse_draw_webgpu_test_run(draw_run_wrong, draw_name))
        draw_run_suffix = root / "draw-webgpu-run-suffix.log"
        draw_run_suffix.write_text(
            draw_run.read_text().replace(draw_name, draw_name + "_SUFFIX")
        )
        reject("draw_webgpu_run_suffix_alias", lambda:
               m3.parse_draw_webgpu_test_run(draw_run_suffix, draw_name))

        canonical_names = root / "canonical-names.txt"
        canonical_names.write_text("alpha\nbeta\n", encoding="utf-8")
        assert m3.exact_name_manifest(canonical_names, 2, "fixture") == ["alpha", "beta"]
        malformed_names = root / "malformed-names.txt"
        malformed_names.write_text("alpha\nalpha\n", encoding="utf-8")
        reject("canonical_manifest_duplicate", lambda:
               m3.exact_name_manifest(malformed_names, 2, "fixture"))

        snapshot_input = root / "snapshot-input.bin"
        snapshot_input.write_bytes(b"before")
        snapshot_before = m3.critical_input_snapshot({"fixture": snapshot_input}, root=root)
        snapshot_input.write_bytes(b"after")
        if m3.critical_input_snapshot({"fixture": snapshot_input}, root=root) == snapshot_before:
            raise AssertionError("critical input mutation was not detected")

        names = [m3.REQUIRED_SHADER_ID] + [
            f"shader_{index:04d}" for index in range(m3.STATIC_SHADER_COUNT - 1)
        ]
        cold = root / "cold.log"
        census = "".join(
            f"BW_SHADER_RESULT PASS {name}\nBW_SHADER_CACHE_RESULT MISS {name}\n"
            for name in names
        )
        cold.write_text(
            f"{m3.CENSUS_BEGIN}\n{census}{m3.CENSUS_END}\n"
        )
        assert m3.parse_static(cold, "MISS")[0] == names
        warm = root / "warm.log"
        warm.write_text(cold.read_text().replace(
            "BW_SHADER_CACHE_RESULT MISS", "BW_SHADER_CACHE_RESULT HIT"
        ))
        assert m3.parse_static(warm, "HIT")[0] == names
        missing = root / "missing.log"
        missing.write_text(
            f"{m3.CENSUS_BEGIN}\n" + "".join(
                f"BW_SHADER_RESULT PASS {name}\nBW_SHADER_CACHE_RESULT MISS {name}\n"
                for name in names[:-1]
            ) + f"{m3.CENSUS_END}\n"
        )
        reject("shader_missing_row", lambda: m3.parse_static(missing, "MISS"))
        stale_substitution = root / "stale-fullscreen-substitution.log"
        stale_substitution.write_text(cold.read_text().replace(
            m3.REQUIRED_SHADER_ID, m3.FORBIDDEN_SHADER_ID))
        reject("shader_stale_fullscreen_substitution",
               lambda: m3.parse_static(stale_substitution, "MISS"))
        false_green = root / "false-green.log"
        false_green.write_text(cold.read_text().replace(
            "BW_SHADER_RESULT PASS shader_0000", "BW_SHADER_RESULT FAIL shader_0000", 1))
        reject("shader_failed_row", lambda: m3.parse_static(false_green, "MISS"))
        cache_mix = root / "cache-mix.log"
        cache_mix.write_text(cold.read_text().replace(
            "BW_SHADER_CACHE_RESULT MISS shader_0000",
            "BW_SHADER_CACHE_RESULT HIT shader_0000", 1))
        reject("cold_cache_false_hit", lambda: m3.parse_static(cache_mix, "MISS"))
        warm_cache_mix = root / "warm-cache-mix.log"
        warm_cache_mix.write_text(warm.read_text().replace(
            "BW_SHADER_CACHE_RESULT HIT shader_0000",
            "BW_SHADER_CACHE_RESULT MISS shader_0000", 1))
        reject("warm_cache_false_miss", lambda: m3.parse_static(warm_cache_mix, "HIT"))
        duplicate_cache = root / "duplicate-cache.log"
        duplicate_cache.write_text(cold.read_text().replace(
            f"{m3.CENSUS_END}\n",
            f"BW_SHADER_CACHE_RESULT MISS shader_0000\n{m3.CENSUS_END}\n", 1))
        reject("shader_cache_duplicate_name",
               lambda: m3.parse_static(duplicate_cache, "MISS"))
        mismatched_cache = root / "mismatched-cache.log"
        mismatched_cache.write_text(cold.read_text().replace(
            "BW_SHADER_CACHE_RESULT MISS shader_0000",
            "BW_SHADER_CACHE_RESULT MISS truncated_shader", 1))
        reject("shader_cache_keyset_mismatch",
               lambda: m3.parse_static(mismatched_cache, "MISS"))
        uncaptured_error = root / "uncaptured-device-error.log"
        uncaptured_error.write_text(cold.read_text().replace(
            "BW_SHADER_RESULT PASS shader_0001",
            "[WebGPU] uncaptured device error (type 2): invalid bind group layout\n"
            "BW_SHADER_RESULT PASS shader_0001", 1))
        reject("shader_uncaptured_device_error",
               lambda: m3.parse_static(uncaptured_error, "MISS"))
        pre_census_error = root / "pre-census-device-error.log"
        pre_census_error.write_text(
            "[WebGPU] uncaptured device error (type 2): fixture setup failure\n"
            + cold.read_text()
        )
        reject("shader_pre_census_device_error",
               lambda: m3.parse_static(pre_census_error, "MISS"))
        post_census_error = root / "post-census-device-error.log"
        post_census_error.write_text(
            cold.read_text()
            + "[WebGPU] uncaptured device error (type 2): delayed pipeline failure\n"
        )
        reject("shader_post_census_device_error",
               lambda: m3.parse_static(post_census_error, "MISS"))
        post_census_leak = root / "post-census-memory-leak.log"
        post_census_leak.write_text(
            cold.read_text() + "Error: Not freed memory blocks: 1\n"
        )
        reject("shader_post_census_memory_leak",
               lambda: m3.parse_static(post_census_leak, "MISS"))
        no_boundary = root / "no-boundary.log"
        no_boundary.write_text(census)
        reject("shader_census_missing_boundary", lambda: m3.parse_static(no_boundary, "MISS"))
        duplicate_boundary = root / "duplicate-boundary.log"
        duplicate_boundary.write_text(
            f"{m3.CENSUS_BEGIN}\n{m3.CENSUS_BEGIN}\n{census}{m3.CENSUS_END}\n"
        )
        reject("shader_census_duplicate_boundary",
               lambda: m3.parse_static(duplicate_boundary, "MISS"))
        escaped_result = root / "escaped-result.log"
        escaped_result.write_text(
            "BW_SHADER_RESULT PASS escaped\n"
            f"{m3.CENSUS_BEGIN}\n{census}{m3.CENSUS_END}\n"
        )
        reject("shader_result_outside_census",
               lambda: m3.parse_static(escaped_result, "MISS"))
        escaped_cache = root / "escaped-cache.log"
        escaped_cache.write_text(
            "BW_SHADER_CACHE_RESULT MISS fixture_bootstrap\n"
            f"{m3.CENSUS_BEGIN}\n{census}{m3.CENSUS_END}\n"
        )
        reject("shader_cache_outside_census",
               lambda: m3.parse_static(escaped_cache, "MISS"))

        cache_root = root / "cache-contract"
        cache_root.mkdir()
        (cache_root / ("0" * 32 + ".wgslc")).write_bytes(b"first")
        (cache_root / ("1" * 32 + ".wgslc")).write_bytes(b"second")
        cache_rows = m3.cache_manifest_rows(cache_root, expected_count=2)
        assert len(cache_rows) == 2
        m3.require_cache_unchanged(cache_rows, list(cache_rows))
        reject("shader_cache_missing_file",
               lambda: m3.cache_manifest_rows(cache_root, expected_count=3))
        bad_name_root = root / "cache-bad-name"
        bad_name_root.mkdir()
        (bad_name_root / "not-a-content-key.wgslc").write_bytes(b"bad")
        reject("shader_cache_noncanonical_filename",
               lambda: m3.cache_manifest_rows(bad_name_root, expected_count=1))
        symlink_root = root / "cache-symlink"
        symlink_root.mkdir()
        symlink_target = root / "cache-target"
        symlink_target.write_bytes(b"target")
        (symlink_root / ("2" * 32 + ".wgslc")).symlink_to(symlink_target)
        reject("shader_cache_symlink_entry",
               lambda: m3.cache_manifest_rows(symlink_root, expected_count=1))
        reject("shader_cache_warm_mutation",
               lambda: m3.require_cache_unchanged(
                   cache_rows, [cache_rows[0], cache_rows[1] + "x"]))

    print(json.dumps({
        "schema": 1, "verdict": "PASS", "positive": 23,
        "negative": len(negatives), "negative_checks": negatives,
        "m2_suite_count": 75, "m3_gpu_count": m3.GPU_TEST_COUNT,
        "m3_shader_count": m3.STATIC_SHADER_COUNT,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
