#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent, fail-closed M0--M3 closeout verifier.

The verifier consumes evidence; it does not run builds and it never mutates the
repository.  Its input schema is intentionally narrow so that a producer cannot
turn an omitted check, an unbound label, or an invented field into a green run.
"""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import sys
from typing import Any
from urllib.parse import quote_from_bytes, unquote_to_bytes


SCHEMA = 1
MAX_FRESHNESS_SECONDS = 24 * 60 * 60
BLENDER_BRANCH = "blender-v5.2-release"
BLENDER_COMMIT = "fbe6228777e7d9afefcd61a413844e790ae75db7"
EMSDK_VERSION = "6.0.5"
EMSDK_RELEASE_COMMIT = "dbd755b5da399329c2576f6e3dfa7f419f5d8409"
EMSDK_REPO_COMMIT = "1ab2e627b1a84567f5284d1baaa5f6be7ccf07de"
EMCC_COMMIT = "1db513782be24469589d7cb8a1f1834e9a33f271"

M0_ARTIFACTS = {
    "blender_web_cmake": "patches/blender_web.cmake",
    "buildwrap": "harness/buildwrap.sh",
    "ci_workflow": ".github/workflows/m0.yml",
    "deps_ledger": "ledger/deps.json",
    "deferred_ledger": "ledger/deferred.json",
    "m0_selfcheck": "scripts/m0-selfcheck.py",
    "ninja_locked": "scripts/ninja-locked.sh",
    "oracle_receipt": "scripts/m0-oracle-receipt.py",
    "oracle_dockerfile": "containers/oracle/Dockerfile",
    "oracle_pin": "oracle/PIN",
    "oracle_toolchain": "oracle/TOOLCHAIN",
    "oracle_wrapper": "scripts/oracle-container.sh",
    "native_oracle": "oracle/bpy.sh",
    "reuse_config": "reuse.toml",
}
NINJA_LOCKED_RELATIVE = "../scripts/ninja-locked.sh"

MAIN_CORPUS = {
    "animation",
    "armature",
    "collections_instancing",
    "curves_text",
    "materials_nodes",
    "mesh_dense",
    "modifiers",
    "startup",
    "stress_mixed",
}
VERSIONING_PASS = {
    "v255_nodegroup25",
    "v260_bhead4",
    "v272_ge_framing",
    "v272_ge_keyboard",
    "v273_ge_2dexample",
    "v273_ge_glsl249",
    "v283_fcurve",
    "v300_smallbhead8",
    "v306_nodegroup36",
    "v402_layered_action",
}
VERSIONING_REFUSE = {"v230_be_ctrlobject", "v236_be_pathdist"}

M2_KEYS = (
    "script_pyapi_bpy_app", "script_pyapi_bpy_app_tempdir",
    "script_pyapi_bpy_path", "script_pyapi_bpy_utils_units",
    "script_pyapi_mathutils", "script_pyapi_bpy_driver_secure_eval",
    "script_pyapi_idprop", "script_pyapi_idprop_datablock",
    "script_pyapi_prop", "script_pyapi_prop_array", "script_pyapi_text",
    "script_pyapi_bmesh", "script_pyapi_grease_pencil",
    "script_pyapi_annotations", "id_management", "bl_rna_paths",
    "bl_rna_accessors", "imbuf_py_api", "operator_function_py_api",
    "operator_wrap_py_api", "blendfile_io", "global_undo",
    "geometry_attributes", "mesh_join", "object_edit", "object_api",
    "node_tools", "compositing_node_group", "sequencer_strip_naming",
    "bl_brush", "bl_voxel_remesh", "bl_sculpt_brush_curve_presets",
    "bl_animation_bake", "bl_animation_rename", "bl_animation_nla_strip",
    "bl_animation_pose_slide", "script_load_keymap", "script_validate_keymap",
    "bl_animation_armature", "bl_animation_drivers", "bl_animation_shapekey",
    "bl_animation_fcurves", "bl_animation_action", "bl_animation_keyframing",
    "bl_animation_motion_path", "bl_pose_assets", "bl_rigging_symmetrize",
    "vertex_group_painting", "bl_node_structure_type_inference",
    "bl_node_socket_usage_inference", "bl_node_group_compat",
    "bl_node_group_interface", "bl_node_copy_operators", "bl_node_link_drag",
    "bl_sculpt_mask", "bl_sculpt_face_set", "bl_multires",
    "bl_sculpt_mesh_filter", "bl_sculpt_automasking", "bl_sculpt_brushes",
    "bl_vertex_paint_brushes", "bl_weight_paint_brushes",
    "bl_texture_paint_brushes", "bl_voxel_remesh_compare", "physics_cloth",
    "physics_softbody", "physics_dynamic_paint", "physics_particle_system",
    "physics_particle_instance", "bl_constraints", "blendfile_liblink",
    "blendfile_relationships", "blendfile_library_overrides", "mesh_validate",
    "object_modifier_array",
)
M2_SKIP = {
    "script_pyapi_doc_gen", "script_load_addons", "script_load_modules",
    "script_disk_file_hash_service_test", "physics_ocean", "script_bundled_modules",
}

# These are the only M2 failure classifications in the pinned 75-key contract.
# A passing row is always accepted and becomes an un-defer candidate.
M2_DEFERRALS = {
    "script_pyapi_mathutils": {"float32-ulp-mathutils"},
    "script_pyapi_bmesh": {"float32-ulp-mathutils"},
    "bl_constraints": {"float32-ulp-mathutils"},
    "bl_node_structure_type_inference": {"wasm32-64bit-blend-collision"},
    "bl_voxel_remesh": {"feature-off-openvdb"},
    "bl_voxel_remesh_compare": {"feature-off-openvdb"},
    "imbuf_py_api": {"feature-off-avif"},
}
M2_DETECTOR_ACTIVE_ID = "wasm32-64bit-blend-collision"
M2_DETECTOR_ACTIVE_SUITE = "bl_node_structure_type_inference"
M2_DETECTOR_ACTIVE_STATUS = "detector-active"
M2_DETECTOR_ACTIVE_MARKER = (
    "Cannot open this 64-bit .blend on 32-bit WebAssembly: block address 0xADDR "
    "collides with another block after truncation to 32 bits, so its data pointers "
    "cannot be resolved without corruption. This is a known wasm32 limitation "
    "(see ADR-004, wasm32-pointer-collision); a wasm64 build reads this file correctly."
)
_M2_DETECTOR_RAW_HEAD, _M2_DETECTOR_RAW_TAIL = M2_DETECTOR_ACTIVE_MARKER.split("0xADDR")
M2_DETECTOR_ACTIVE_RAW_RE = re.compile(
    re.escape(_M2_DETECTOR_RAW_HEAD.encode()) + rb"0x[0-9A-Fa-f]+" +
    re.escape(_M2_DETECTOR_RAW_TAIL.encode())
)
M2_ALLOCATOR_LINE = b"Switching to fully guarded memory allocator.\n"
M2_WASM_BANNER_LINE = b"Blender 5.2.0 LTS\n"
M2_NATIVE_BANNER_RE = re.compile(
    rb"Blender 5\.2\.0 LTS \(hash fbe6228777e7 built "
    rb"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}\)\n"
)
M2_VERBOSE_UNITTEST_PROGRESS_RE = re.compile(
    rb"(?P<method>test_[A-Za-z0-9_]+) "
    rb"\(__main__\.[A-Za-z_][A-Za-z0-9_.]*\.(?P=method)\) \.\.\. "
)
M2_WASM_LOCALE_RE = re.compile(
    rb"[0-9]{2}:[0-9]{2}\.[0-9]{3}  translation      \| WARNING "
    rb"'locale' data path for translations not found\n"
)
M2_NO_DENOISER_SUITE = "bl_rna_accessors"
M2_NO_DENOISER_NORMALIZED_LINE = (
    b"<LOG_TIME>  bpy.rna          | WARNING current value '4' matches no enum in "
    b"'CyclesRenderSettings', '', 'denoiser'\n"
)
M2_NATIVE_CUEW_NORMALIZED_LINE = (
    b"<LOG_TIME>  cycles           | WARNING CUEW initialization failed: "
    b"Error opening the library\n"
)
M2_RNA_ACCESSORS_COLORSPACE_WARNING = (
    b"<LOG_TIME>  bpy.rna          | WARNING current value '-1' matches no enum in "
    b"'ColorManagedInputColorspaceSettings', '(null)', 'name'\n"
)
M2_RNA_ACCESSORS_PROGRESS_CANONICAL = M2_RNA_ACCESSORS_COLORSPACE_WARNING + b".\n"
M2_RNA_ACCESSORS_RESULT_SEPARATOR = b"-" * 70 + b"\n"
M2_TEMPDIR_SUITE = "script_pyapi_bpy_app_tempdir"
M2_TEMPDIR_PROGRESS_FIXTURES = (
    b"\n\n..\n.\n.\n.\n",
    b"\n.\n.\n.\n.\n.\n",
)
M2_TEMPDIR_PROGRESS_DOTS = 5
M2_TEMPDIR_PROGRESS_NEWLINES = 6
M2_TEMPDIR_PROGRESS_CANONICAL = b"\n.....\n"
M2_TEMPDIR_RESULT_TAIL = b"-" * 70 + b"\nRan 5 tests in <T>s\n\nOK\n"
M2_PROP_ARRAY_SUITE = "script_pyapi_prop_array"
M2_PROP_ARRAY_DIAGNOSTICS = (
    b"<LOG_TIME>  reports          | ERROR Array length mismatch (got 7, expected more)\n",
    b"<LOG_TIME>  reports          | ERROR Array length mismatch (got 7, expected more)\n",
    b"<LOG_TIME>  reports          | ERROR Array length mismatch (got 23, expected more)\n",
    b"<LOG_TIME>  reports          | ERROR Array length mismatch (got 23, expected more)\n",
)
M2_PROP_ARRAY_PROGRESS_DOTS = 42
M2_PROP_ARRAY_RESULT_TAIL = b"-" * 70 + b"\nRan 42 tests in <T>s\n\nOK\n"
M2_PROP_ARRAY_PROGRESS_CANONICAL = b"<PROP_ARRAY_PROGRESS_42_AROUND_DIAGNOSTICS>\n"
M2_TEXT_SUITE = "script_pyapi_text"
M2_TEXT_PROGRESS_DOTS = 5
M2_TEXT_PROGRESS_NEWLINES = {1, 2}
M2_TEXT_RESULT_TAIL = b"-" * 70 + b"\nRan 5 tests in <T>s\n\nOK\n"
M2_TEXT_PROGRESS_CANONICAL = b"<TEXT_PROGRESS_5>\n"
M2_SEQUENCER_STRIP_NAMING_SUITE = "sequencer_strip_naming"
M2_SEQUENCER_STRIP_NAMING_PROGRESS_DOTS = 6
M2_SEQUENCER_STRIP_NAMING_PROGRESS_NEWLINES = {1, 2}
M2_SEQUENCER_STRIP_NAMING_RESULT_TAIL = b"-" * 70 + b"\nRan 6 tests in <T>s\n\nOK\n"
M2_SEQUENCER_STRIP_NAMING_PROGRESS_CANONICAL = b"<SEQUENCER_STRIP_NAMING_PROGRESS_6>\n"
M2_ANIMATION_ARMATURE_SUITE = "bl_animation_armature"
M2_ANIMATION_ARMATURE_HOMEFILE = b"\x1b[92mloading empty homefile\x1b[0m\n"
M2_ANIMATION_ARMATURE_READ = (
    b'<LOG_TIME>  blend            | Read blend: "<REPO>/upstream/tests/files/'
    b'animation/armature_join_with_action_constraints.blend"\n'
)
M2_ANIMATION_ARMATURE_RESULT_TAIL = (
    b"-" * 70 + b"\nRan 6 tests in <T>s\n\nOK\n\nBlender quit\n"
)
M2_ANIMATION_ARMATURE_CANONICAL = (
    M2_ANIMATION_ARMATURE_HOMEFILE + M2_ANIMATION_ARMATURE_READ + b"......\n"
    + M2_ANIMATION_ARMATURE_RESULT_TAIL
)
M2_SCULPT_BRUSH_CURVE_PRESETS_SUITE = "bl_sculpt_brush_curve_presets"
M2_SCULPT_BRUSH_CURVE_PRESETS_PROGRESS_DOTS = 9
M2_SCULPT_BRUSH_CURVE_PRESETS_PROGRESS_NEWLINES = {1, 2}
M2_SCULPT_BRUSH_CURVE_PRESETS_RESULT_TAIL = b"-" * 70 + b"\nRan 9 tests in <T>s\n\nOK\n"
M2_SCULPT_BRUSH_CURVE_PRESETS_PROGRESS_CANONICAL = b"<SCULPT_BRUSH_CURVE_PRESETS_PROGRESS_9>\n"
M2_OPERATOR_FUNCTION_PY_API_SUITE = "operator_function_py_api"
M2_OPERATOR_FUNCTION_PY_API_PROGRESS_DOTS = 33
M2_OPERATOR_FUNCTION_PY_API_PROGRESS_NEWLINES = {1, 2}
M2_OPERATOR_FUNCTION_PY_API_RESULT_TAIL = b"-" * 70 + b"\nRan 33 tests in <T>s\n\nOK\n"
M2_OPERATOR_FUNCTION_PY_API_PROGRESS_CANONICAL = b"<OPERATOR_FUNCTION_PY_API_PROGRESS_33>\n"
M2_GEOMETRY_ATTRIBUTES_SUITE = "geometry_attributes"
M2_GEOMETRY_ATTRIBUTES_PROGRESS_DOTS = 16
M2_GEOMETRY_ATTRIBUTES_PROGRESS_NEWLINES = {1, 2}
M2_GEOMETRY_ATTRIBUTES_RESULT_TAIL = b"-" * 70 + b"\nRan 16 tests in <T>s\n\nOK\n"
M2_GEOMETRY_ATTRIBUTES_PROGRESS_CANONICAL = b"<GEOMETRY_ATTRIBUTES_PROGRESS_16>\n"
M2_NODE_GROUP_COMPAT_SUITE = "bl_node_group_compat"
M2_NODE_GROUP_COMPAT_COMPOSITOR_READ = (
    b'<LOG_TIME>  blend            | Read blend: "<REPO>/upstream/tests/files/'
    b'node_group/node_group_socket_interface_compositor.blend"\n'
)
M2_NODE_GROUP_COMPAT_DOVERSION_WARNING = (
    b'<LOG_TIME>  blend.doversion  | WARNING Region type 4 missing in space type '
    b'"Info" (id: 7) - removing region\n'
)
M2_NODE_GROUP_COMPAT_PROGRESS_CANONICAL = (
    b"." + M2_NODE_GROUP_COMPAT_COMPOSITOR_READ
    + M2_NODE_GROUP_COMPAT_DOVERSION_WARNING
)
M2_NODE_GROUP_COMPAT_NODEGROUP36_READ = (
    b'.<LOG_TIME>  blend            | Read blend: "<REPO>/upstream/tests/files/'
    b'node_group/nodegroup36.blend"\n'
)
M2_NODE_GROUP_COMPAT_OUTPUT_WARNING = (
    b'<LOG_TIME>  object.modifier  | WARNING Object: "Cube", Modifier: '
    b'"GeometryNodes", Node group must have a group output node\n'
)
M2_NODE_GROUP_COMPAT_NODEGROUP36_CANONICAL = b"".join(
    [M2_NODE_GROUP_COMPAT_NODEGROUP36_READ, M2_NODE_GROUP_COMPAT_OUTPUT_WARNING] * 3
)
M2_NODE_TOOLS_SUITE = "node_tools"
M2_NODE_TOOLS_PROGRESS_DOTS = 4
M2_NODE_TOOLS_PROGRESS_NEWLINES = {1, 2}
M2_NODE_TOOLS_RESULT_TAIL = b"-" * 70 + b"\nRan 4 tests in <T>s\n\nOK\n"
M2_NODE_TOOLS_PROGRESS_CANONICAL = b"<NODE_TOOLS_PROGRESS_4>\n"
M2_ANIMATION_KEYFRAMING_SUITE = "bl_animation_keyframing"
M2_ANIMATION_KEYFRAMING_CONTINUATION = b"                            | \n"
M2_ANIMATION_KEYFRAMING_FCURVE_CREATE_WARNING = (
    b"Warning: Could not create 1 F-Curve(s). This can happen when only inserting "
    b"to available F-Curves.\n"
)
M2_ANIMATION_KEYFRAMING_KEYING_SET_ERROR = (
    b"Error: No suitable context info for active keying set\n"
)


def m2_animation_keyframing_scale_warning(index: int, slot: str) -> bytes:
    return (
        f"<LOG_TIME>  anim.action      | WARNING FCurve scale[{index}] for slot {slot} "
        "was not created due to either the Only Insert Available setting or Replace "
        "keyframing mode.\n"
    ).encode()


M2_ANIMATION_KEYFRAMING_FIRST_WARNING = m2_animation_keyframing_scale_warning(
    0, "OBCube"
)
M2_ANIMATION_KEYFRAMING_PROGRESS_MIDDLE = [
    M2_ANIMATION_KEYFRAMING_CONTINUATION,
    m2_animation_keyframing_scale_warning(1, "OBCube"),
    M2_ANIMATION_KEYFRAMING_CONTINUATION,
    m2_animation_keyframing_scale_warning(2, "OBCube"),
    M2_ANIMATION_KEYFRAMING_CONTINUATION,
    m2_animation_keyframing_scale_warning(0, "OBanim_object"),
    M2_ANIMATION_KEYFRAMING_CONTINUATION,
    m2_animation_keyframing_scale_warning(1, "OBanim_object"),
    M2_ANIMATION_KEYFRAMING_CONTINUATION,
    m2_animation_keyframing_scale_warning(2, "OBanim_object"),
    M2_ANIMATION_KEYFRAMING_CONTINUATION,
]
M2_ANIMATION_KEYFRAMING_PROGRESS_CANONICAL = b"".join([
    M2_ANIMATION_KEYFRAMING_FIRST_WARNING,
    *M2_ANIMATION_KEYFRAMING_PROGRESS_MIDDLE,
    b"." + M2_ANIMATION_KEYFRAMING_FCURVE_CREATE_WARNING,
    b"." + M2_ANIMATION_KEYFRAMING_KEYING_SET_ERROR,
])
M2_VERTEX_GROUP_PAINTING_SUITE = "vertex_group_painting"
M2_VERTEX_GROUP_PAINTING_READ = (
    b'<LOG_TIME>  blend            | Read blend: "<REPO>/upstream/tests/files/'
    b'animation/vertex_groups.blend"\n'
)
M2_VERTEX_GROUP_PAINTING_ERROR = b"Error: All groups are locked\n"
M2_VERTEX_GROUP_PAINTING_RESULT_TAIL = b"-" * 70 + b"\nRan 2 tests in <T>s\n\nOK\n"
M2_VERTEX_GROUP_PAINTING_CANONICAL = (
    M2_VERTEX_GROUP_PAINTING_READ + b"." + M2_VERTEX_GROUP_PAINTING_READ
    + M2_VERTEX_GROUP_PAINTING_ERROR + b".\n"
    + M2_VERTEX_GROUP_PAINTING_RESULT_TAIL
)
M2_ANIMATION_FCURVES_SUITE = "bl_animation_fcurves"
M2_ANIMATION_FCURVES_EULER_READ = (
    b'<LOG_TIME>  blend            | Read blend: "<REPO>/upstream/tests/files/'
    b'animation/euler-filter.blend"\n'
)
M2_ANIMATION_FCURVES_EULER_MISSING = (
    b"Info: Missing Z component(s) of euler rotation for ID='OBOne-Channel-Jumps' "
    b"and RNA-Path='rotation_euler'\n"
)
M2_ANIMATION_FCURVES_EULER_FILTERED = b"Info: All 5 rotation channels were filtered\n"
M2_ANIMATION_FCURVES_EULER_CANONICAL = b"".join([
    M2_ANIMATION_FCURVES_EULER_READ,
    M2_ANIMATION_FCURVES_EULER_MISSING,
    M2_ANIMATION_FCURVES_EULER_FILTERED,
    b"." + M2_ANIMATION_FCURVES_EULER_READ,
    M2_ANIMATION_FCURVES_EULER_MISSING,
    M2_ANIMATION_FCURVES_EULER_FILTERED,
])
M2_ANIMATION_FCURVES_NO_KEYS_WARNING = (
    b"<LOG_TIME>  reports          | WARNING No keys have been inserted and no "
    b"errors have been reported.\n"
)
M2_ANIMATION_FCURVES_WARNING_ROWS = 300
M2_ANIMATION_FCURVES_NATIVE_DOT_OFFSETS = {0, 99, 200, 250}
M2_ANIMATION_FCURVES_WASM_DOT_OFFSETS = {0, 100, 200, 250}


def m2_animation_fcurves_warning_block(offsets: set[int]) -> list[bytes]:
    return [
        (b"." if index in offsets else b"") + M2_ANIMATION_FCURVES_NO_KEYS_WARNING
        for index in range(M2_ANIMATION_FCURVES_WARNING_ROWS)
    ]


M2_ANIMATION_FCURVES_WARNING_CANONICAL = b"".join(
    m2_animation_fcurves_warning_block(M2_ANIMATION_FCURVES_WASM_DOT_OFFSETS)
)
M2_MESH_VALIDATE_SUITE = "mesh_validate"
M2_MESH_VALIDATE_PROGRESS_ERRORS = [
    b"<LOG_TIME>  geom.mesh        | ERROR Face 1 is a duplicate of 0\n",
    b"<LOG_TIME>  geom.mesh        | ERROR Corner 2 has incorrect edge index 0\n",
    b"<LOG_TIME>  geom.mesh        | ERROR Face offsets must be monotonically "
    b"increasing. Considering all faces invalid\n",
    b"<LOG_TIME>  geom.mesh        | ERROR Edge 0 has out of range vertex (0, 99)\n",
    b"<LOG_TIME>  geom.mesh        | ERROR Attribute position has invalid values "
    b"at indices: 0\n",
]
M2_MESH_VALIDATE_PROGRESS_CANONICAL = b"".join(
    b"." + line for line in M2_MESH_VALIDATE_PROGRESS_ERRORS
)
M2_MESH_VALIDATE_MDISP_READ = (
    b'.<LOG_TIME>  blend            | Read blend: "<REPO>/upstream/tests/files/'
    b'sculpting/invalid_mdisp_cube.blend"\n'
)
M2_MESH_VALIDATE_MDISP_ERROR = (
    b"<LOG_TIME>  geom.mesh        | ERROR Multires displacement has invalid "
    b"values at indices: 1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23\n"
)
M2_MESH_VALIDATE_RESULT_TAIL = (
    b".\n" + b"-" * 70 + b"\nRan 15 tests in <T>s\n\nOK\n"
)
M2_MESH_VALIDATE_END_CANONICAL = (
    M2_MESH_VALIDATE_MDISP_READ
    + M2_MESH_VALIDATE_MDISP_ERROR
    + M2_MESH_VALIDATE_RESULT_TAIL
)
M2_SCULPT_FACE_SET_SUITE = "bl_sculpt_face_set"
M2_SCULPT_FACE_SET_READ = (
    b'<LOG_TIME>  blend            | Read blend: "<REPO>/upstream/tests/files/'
    b'sculpting/30k_monkey_mask_and_face_set.blend"\n'
)
M2_SCULPT_FACE_SET_RESULT_TAIL = b"-" * 70 + b"\nRan 3 tests in <T>s\n\nOK\n"
M2_SCULPT_FACE_SET_CANONICAL = (
    M2_SCULPT_FACE_SET_READ + b"." + M2_SCULPT_FACE_SET_READ
    + b"." + M2_SCULPT_FACE_SET_READ + b".\n"
    + M2_SCULPT_FACE_SET_RESULT_TAIL
)
M2_REPOSITORY_ROOT_TOKEN = b"<REPO>"
M2_CONTAINER_REPOSITORY_ROOT = b"/work"
M2_SCRATCH_ROOT_SUITE = "blendfile_io"
M2_SCRATCH_ROOT_TOKEN = b"<SUITE_SCRATCH>"
M2_SCRATCH_ROOT_OCCURRENCES = 6
M2_SCRATCH_ROOT_POLICIES = {
    M2_SCRATCH_ROOT_SUITE: M2_SCRATCH_ROOT_OCCURRENCES,
    "bl_animation_action": 1,
    "blendfile_liblink": 33,
    "blendfile_relationships": 4,
    "blendfile_library_overrides": 83,
}
M2_KEYMAP_ORDER_SUITE = "script_load_keymap"
M2_KEYMAP_FIRST_HEADER = b"Keymaps that are in 'bl_keymap_utils.keymap_hierarchy' but not blender\n"
M2_KEYMAP_SECOND_HEADER = b"Keymaps that are in blender but not in 'bl_keymap_utils.keymap_hierarchy'\n"
M2_KEYMAP_TAIL = [
    b"Comparing keymap space/region types...\n", b"done!\n", b"\n", b"Blender quit\n",
]
M2_PHYSICS_ORDER = {
    "physics_cloth": ("cloth_test.blend", (("ClothSimple", 15), ("ClothSpring", 10))),
    "physics_softbody": ("softbody_test.blend", (("SoftBodySimple", 45),)),
    "physics_dynamic_paint": (
        "dynamic_paint_test.blend", (("DynamicPaintSimple", 15),)
    ),
}
M2_PASS_DELTA_DEFERRALS = {
    "bl_rna_paths": "os-shell-affordances",
    "bl_animation_action": "wasm32-animation-action-objectdata",
    "blendfile_library_overrides": "wasm32-library-override-idname-allocation",
}
M2_PASS_DELTA_MARKERS = {
    "bl_rna_paths": "normalized-delta:v2:rna-paths:native-platform-menu_vs_wasm-sandbox-menu",
    "bl_animation_action": "normalized-delta:v5:animation-action:wasm-objectdata-and-native-stream-layouts",
    "blendfile_library_overrides": "normalized-delta:v4:library-overrides:six-idname-bijection-and-scratch-phase",
}
M2_PASS_DELTA_LEDGER = {
    "os-shell-affordances": {
        "status": "deferred-by-goal", "milestone": "GOAL", "evidence": "GOAL.md:19",
    },
    "wasm32-animation-action-objectdata": {
        "status": "deferred", "milestone": "M2",
        "evidence": "notes/m2-tierb-prep.md §8",
    },
    "wasm32-library-override-idname-allocation": {
        "status": "deferred", "milestone": "M2",
        "evidence": "notes/m2-tierb-prep.md §8",
    },
}
M2_PASS_DELTA_NOTE_PATH = "notes/m2-tierb-prep.md"
M2_PASS_DELTA_NOTE_REQUIRED = (
    b"## 8. Exact M2 pass-with-delta closeout (2026-08-17)\n",
    b"`os-shell-affordances` goal deferral",
    b"`wasm32-animation-action-objectdata`",
    b"`wasm32-library-override-idname-allocation`",
    b"The two M2-specific ledger rows must remain `status=deferred`, `milestone=M2`",
    b"`evidence=notes/m2-tierb-prep.md \xc2\xa78`",
    b"`status=deferred-by-goal`, `milestone=GOAL`, and `evidence=GOAL.md:19`",
)
M2_RNA_MENU_CONTEXT = (
    b' at 0xADDR> from ["bpy.data.screens[\'Shading\']", '
    b'"bpy.data.screens[\'Shading\'].areas[4]", '
    b'"bpy.data.screens[\'Shading\'].areas[4].spaces[0]"]\n'
)
M2_RNA_NATIVE_MENUS = (
    ("iCloud Drive", "Macintosh HD", "Desktop", "Documents", "Downloads", "Applications"),
    ("work", "hosts", "hostname", "resolv.conf", "Home", "Desktop", "Documents",
     "Downloads", "Videos", "Pictures", "Music"),
)
M2_RNA_WASM_MENU = ("/", "Home", "Desktop", "Documents", "Downloads", "Videos", "Pictures", "Music")
M2_ANIMATION_ASSIGNMENT_WARNING = (
    b"WARNING: ignoring assignment to target_id_type of Slot 'OBLegacy Slot' in "
    b"Action 'ACAction Without IDRoot'. A Slot's target_id_type can only be changed "
    b"when currently 'UNSPECIFIED'.\n"
)
M2_ANIMATION_SLOT_UNASSIGNED_ERROR = (
    b"<LOG_TIME>  reports          | ERROR Cannot set slot without an assigned Action.\n"
)
M2_ANIMATION_SLOT_XX_WARNING = (
    b'<LOG_TIME>  reports          | WARNING Attempted to set slot identifier to '
    b'"MAEvenCoolerSlot", but the type prefix does not match the slot\'s '
    b'\'target_id_type\' "XX". Setting to "XXEvenCoolerSlot" instead.\n'
)
M2_ANIMATION_SLOT_OB_WARNING = M2_ANIMATION_SLOT_XX_WARNING.replace(
    b'"XX". Setting to "XXEvenCoolerSlot"',
    b'"OB". Setting to "OBEvenCoolerSlot"',
)
M2_ANIMATION_REPORT_CONTINUATION = b"                            | \n"
M2_ANIMATION_FCURVE_ERROR = (
    b"ERROR: F-Curve (datapath: 'location') doesn't belong to the same channel bag "
    b"as channel group 'group1'\n"
)
M2_ANIMATION_REMAP_READ = (
    b'<LOG_TIME>  blend            | Read blend: "<REPO>/upstream/tests/files/'
    b'animation/remap_action.blend"\n'
)
M2_ANIMATION_SECOND_REMAP_READ = b"." + M2_ANIMATION_REMAP_READ
M2_ANIMATION_SAVED = b'.Info: Saved as "liboverride-action-slot.blend"\n'
M2_ANIMATION_OBJECTDATA_WARNING = (
    b"<LOG_TIME>  blend            | WARNING 1 local ObjectData are reported to be "
    b"missing, this should never happen\n"
)
M2_ANIMATION_TEMP_READ = (
    b'<LOG_TIME>  blend            | Read blend: "<SUITE_SCRATCH>/'
    b'bl_animation_action/liboverride-action-slot.blend"\n'
)
M2_ANIMATION_LAYERED_READ = (
    b'.<LOG_TIME>  blend            | Read blend: "<REPO>/upstream/tests/files/'
    b'animation/layered_action_versioning_42.blend"\n'
)
M2_ANIMATION_LAYERED_READ_BARE = M2_ANIMATION_LAYERED_READ[1:]
M2_ANIMATION_RELATIVE_LIBRARY = (
    b"//../../../../../../../../../upstream/tests/files/animation/"
    b"liboverride-action-slot-libfile.blend"
)
M2_ANIMATION_INFO_LIBRARY = (
    b"Info: Read library: '<REPO>/upstream/tests/files/animation/"
    b"liboverride-action-slot-libfile.blend', '" + M2_ANIMATION_RELATIVE_LIBRARY
    + b"', parent '<direct>'\n"
)
M2_ANIMATION_MISSING_DATA = (
    b"Info: Cannot find object data of Library Suzanne lib "
    + M2_ANIMATION_RELATIVE_LIBRARY + b"\n"
)


def m2_library_override_line(collection: str, reference: str, local: str) -> bytes:
    return (
        f'<bpy_struct, Collection("{collection}") at 0xADDR> '.encode()
        + b"{'IDPOINTER_ITEM_USE_ID', 'IDPOINTER_MATCH_REFERENCE'} "
        + f'{reference} <bpy_struct, Object("{reference}") at 0xADDR> '.encode()
        + f'{local} <bpy_struct, Object("{local}") at 0xADDR>\n'.encode()
    )


M2_LIBRARY_OVERRIDE_PHASE_BEFORE = (
    b"Info: Read library: '<TMP>', '<TMP>', parent '<direct>'\n"
)
M2_LIBRARY_OVERRIDE_PHASE_AFTER = (
    b'<LOG_TIME>  blend            | Read blend: "<TMP>"\n'
)
M2_LIBRARY_OVERRIDE_SCRATCH_LIB = (
    M2_SCRATCH_ROOT_TOKEN + b"/blendfile_io/blendlib_overrides_lib.blend"
)
M2_LIBRARY_OVERRIDE_SCRATCH_RECURSIVE = (
    M2_SCRATCH_ROOT_TOKEN + b"/blendfile_io/blendlib_overrides_test_recursive.blend"
)
M2_LIBRARY_OVERRIDE_SCRATCH_PHASE_BEFORE = (
    b"Info: Read library: '" + M2_LIBRARY_OVERRIDE_SCRATCH_LIB + b"', '"
    + M2_LIBRARY_OVERRIDE_SCRATCH_LIB + b"', parent '<direct>'\n"
)
M2_LIBRARY_OVERRIDE_SCRATCH_PHASE_AFTER = (
    b'<LOG_TIME>  blend            | Read blend: "'
    + M2_LIBRARY_OVERRIDE_SCRATCH_RECURSIVE + b'"\n'
)
M2_LIBRARY_OVERRIDE_CONTROLLER = m2_library_override_line(
    "LibController2", "LibController2", "LibController2"
)
M2_LIBRARY_OVERRIDE_CONTROLLER_001 = m2_library_override_line(
    "LibController2.001", "LibController2", "LibController2.001"
)
M2_LIBRARY_OVERRIDE_CONTROLLER_002 = m2_library_override_line(
    "LibController2.002", "LibController2", "LibController2.002"
)
M2_LIBRARY_OVERRIDE_NATIVE_PHASE = [
    M2_LIBRARY_OVERRIDE_CONTROLLER,
    m2_library_override_line("LibCube", "LibCube.002", "LibCube.002"),
    m2_library_override_line("LibCube", "LibCube.001", "LibCube.001"),
    M2_LIBRARY_OVERRIDE_CONTROLLER_001,
    m2_library_override_line("LibCube.001", "LibCube.002", "LibCube.004"),
    m2_library_override_line("LibCube.001", "LibCube.001", "LibCube.003"),
    M2_LIBRARY_OVERRIDE_CONTROLLER_002,
    m2_library_override_line("LibCube.002", "LibCube.002", "LibCube.007"),
    m2_library_override_line("LibCube.002", "LibCube.001", "LibCube.006"),
]
M2_LIBRARY_OVERRIDE_WASM_PHASE = [
    M2_LIBRARY_OVERRIDE_CONTROLLER,
    m2_library_override_line("LibCube", "LibCube.002", "LibCube.007"),
    m2_library_override_line("LibCube", "LibCube.001", "LibCube.006"),
    M2_LIBRARY_OVERRIDE_CONTROLLER_001,
    m2_library_override_line("LibCube.001", "LibCube.002", "LibCube.002"),
    m2_library_override_line("LibCube.001", "LibCube.001", "LibCube.001"),
    M2_LIBRARY_OVERRIDE_CONTROLLER_002,
    m2_library_override_line("LibCube.002", "LibCube.002", "LibCube.004"),
    m2_library_override_line("LibCube.002", "LibCube.001", "LibCube.003"),
]
M2_LIBRARY_OVERRIDE_RECORD_RE = re.compile(
    rb'^<bpy_struct, Collection\("(?P<collection>LibCube(?:\.00[12])?)"\) at 0xADDR> '
    rb"\{'IDPOINTER_ITEM_USE_ID', 'IDPOINTER_MATCH_REFERENCE'\} "
    rb'(?P<reference>LibCube\.(?:001|002)) <bpy_struct, Object\("(?P=reference)"\) at 0xADDR> '
    rb'(?P<local>LibCube\.(?:001|002|003|004|006|007)) '
    rb'<bpy_struct, Object\("(?P=local)"\) at 0xADDR>\n$'
)
M2_LIBRARY_OVERRIDE_PHASE_BEFORE_INDEX = 23
M2_LIBRARY_OVERRIDE_LOCAL_PAIRS = {
    (b"LibCube.002", b"LibCube.001"),
    (b"LibCube.004", b"LibCube.003"),
    (b"LibCube.007", b"LibCube.006"),
}
M2_LIBRARY_OVERRIDE_SET_CANONICAL = (
    b"{'IDPOINTER_ITEM_USE_ID', 'IDPOINTER_MATCH_REFERENCE'}"
)
M2_LIBRARY_OVERRIDE_SET_REVERSED = (
    b"{'IDPOINTER_MATCH_REFERENCE', 'IDPOINTER_ITEM_USE_ID'}"
)
M2_LIBRARY_OVERRIDE_SET_OCCURRENCES = 66
M2_NORMALIZATION_CACHE: dict[tuple[bool, str | None, bytes, bytes, bytes], bytes] = {}
M3_COMPILER_DEFERRALS = {"storage-texture-atomics", "vertex-stage-rw-storage"}
M3_GPU_TEST_COUNT = 197
M3_SHADER_COUNT = 1003
M3_GPU_CANONICAL_MANIFEST = "sandbox/final-m0-m3/gpu_webgpu_tests.txt"
M3_SHADER_CANONICAL_MANIFEST = "sandbox/final-m0-m3/static_shader_identities.txt"
M3_DRAW_WEBGPU_TESTS = (
    "DrawWebGPUTest.draw_curves_lib",
    "DrawWebGPUTest.draw_debug_lifetime_rebind",
)
M3_REQUIRED_SHADER_ID = "draw_debug_draw_compact"
M3_FORBIDDEN_SHADER_ID = "fullscreen_blit"
M3_WEBGPU_DEVICE_LIMIT_FIELDS = (
    "maxStorageTexturesPerShaderStage",
    "maxSampledTexturesPerShaderStage",
    "maxSamplersPerShaderStage",
    "maxStorageBuffersPerShaderStage",
    "maxBufferSize",
    "maxStorageBufferBindingSize",
    "maxColorAttachmentBytesPerSample",
    "maxComputeWorkgroupStorageSize",
    "maxComputeInvocationsPerWorkgroup",
    "maxComputeWorkgroupSizeX",
)
M3_WEBGPU_DEVICE_LIMIT_PATHS = {
    "native_context": "upstream/intern/ghost/intern/GHOST_ContextWGPU.cc",
    "web_fallback": "platform_web/ghost/GHOST_ContextWGPUWeb.cc",
    "worker_preinit": "platform_web/shell/wgpu-preinit-worker.js",
}
M3_CACHE_MARKER_SOURCE = "upstream/source/blender/gpu/webgpu/wgpu_shader_compiler.cc"
M3_OPENSUBDIV_VERSION = "v3_7_0"
M3_OPENSUBDIV_TARBALL_MD5 = "470d53c4d4335a601c33a052ce7c33b4"
M3_OPENSUBDIV_SOURCE_PATHS = {
    "recipe": "scripts/deps/opensubdiv.sh",
    "configure": "patches/blender_web.cmake",
    "upstream_cmake": "upstream/intern/opensubdiv/CMakeLists.txt",
    "evaluator": "upstream/intern/opensubdiv/internal/evaluator/evaluator_capi.cc",
}
M3_OPENSUBDIV_HEADER = "lib/wasm/include/opensubdiv/osd/glslPatchShaderSource.h"
M3_OPENSUBDIV_CPU_ARCHIVE = "lib/wasm/lib/libosdCPU.a"
M3_OPENSUBDIV_GPU_ARCHIVE = "lib/wasm/lib/libosdGPU.a"
M3_OPENSUBDIV_TOOLS = {
    "emar": "tools/emsdk/upstream/emscripten/emar",
    "emnm": "tools/emsdk/upstream/emscripten/emnm",
}
M3_SHADER_ROW_RE = re.compile(
    r"^BW_SHADER_RESULT (PASS|FAIL) ([A-Za-z0-9_.-]+)$", re.MULTILINE
)
M3_CACHE_ROW_RE = re.compile(
    r"^BW_SHADER_CACHE_RESULT (HIT|MISS) ([A-Za-z0-9_.-]+)$", re.MULTILINE
)
M3_CENSUS_BEGIN = "BW_SHADER_CENSUS_BEGIN"
M3_CENSUS_END = "BW_SHADER_CENSUS_END"
M3_UNCAPTURED_DEVICE_ERROR = "[WebGPU] uncaptured device error"
M3_MEMORY_LEAK_ERROR = "Error: Not freed memory blocks"
REQUIRED_DEPS = {"python", "tbb", "openexr", "openimageio", "opencolorio", "zlib"}


class VerificationError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise VerificationError(message)


def strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            fail(f"duplicate JSON field: {key!r}")
        value[key] = item
    return value


def strict_json(text: str, where: str) -> Any:
    try:
        return json.loads(text, object_pairs_hook=strict_pairs)
    except json.JSONDecodeError as error:
        fail(f"{where}: invalid JSON: {error}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def exact(value: Any, keys: set[str], where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(f"{where}: expected object")
    actual = set(value)
    if actual != keys:
        fail(f"{where}: fields mismatch; missing={sorted(keys-actual)} unknown={sorted(actual-keys)}")
    return value


def integer(value: Any, where: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        fail(f"{where}: expected integer >= {minimum}")
    return value


def parse_time(value: Any, where: str) -> dt.datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        fail(f"{where}: expected UTC RFC3339 ending in Z")
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        fail(f"{where}: invalid timestamp: {error}")
    if parsed.tzinfo != dt.timezone.utc:
        fail(f"{where}: timestamp is not UTC")
    return parsed


class Context:
    def __init__(self, root: Path, now: dt.datetime, max_age: int) -> None:
        self.root = root.resolve(strict=True)
        self.now = now
        self.max_age = max_age
        self.label = ""
        self.freeze_hash = ""
        self.freeze_time = now
        self.manifest_time = now

    def path(self, raw: Any, where: str) -> Path:
        if not isinstance(raw, str) or not raw or "\\" in raw:
            fail(f"{where}: path must be a nonempty POSIX relative path")
        pure = PurePosixPath(raw)
        if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
            fail(f"{where}: unsafe path {raw!r}")
        path = self.root.joinpath(*pure.parts)
        lexical = self.root
        for part in pure.parts:
            lexical /= part
            if lexical.is_symlink():
                fail(f"{where}: lexical path contains a symlink: {raw!r}")
        try:
            resolved = path.resolve(strict=True)
        except OSError as error:
            fail(f"{where}: missing path {raw!r}: {error}")
        try:
            resolved.relative_to(self.root)
        except ValueError:
            fail(f"{where}: path escapes root: {raw!r}")
        if not resolved.is_file():
            fail(f"{where}: expected regular file: {raw!r}")
        return resolved

    def file_ref(self, value: Any, where: str, expected_path: str | None = None) -> Path:
        ref = exact(value, {"path", "bytes", "sha256"}, where)
        if expected_path is not None and ref["path"] != expected_path:
            fail(f"{where}: expected path {expected_path!r}, got {ref['path']!r}")
        path = self.path(ref["path"], where + ".path")
        if integer(ref["bytes"], where + ".bytes") != path.stat().st_size:
            fail(f"{where}: byte count is stale")
        digest = ref["sha256"]
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            fail(f"{where}.sha256: expected lowercase SHA-256")
        if sha256(path) != digest:
            fail(f"{where}: SHA-256 is stale")
        return path

    def load_ref(self, value: Any, where: str, expected_path: str | None = None) -> tuple[dict[str, Any], str, Path]:
        path = self.file_ref(value, where, expected_path)
        try:
            loaded = strict_json(path.read_text(encoding="utf-8"), where)
        except (OSError, UnicodeError) as error:
            fail(f"{where}: invalid JSON: {error}")
        if not isinstance(loaded, dict):
            fail(f"{where}: JSON root is not an object")
        return loaded, sha256(path), path

    def common(self, receipt: dict[str, Any], where: str, extra: set[str]) -> dt.datetime:
        row = exact(receipt, {"schema", "verdict", "run_label", "created_utc", "source_freeze_sha256"} | extra, where)
        if row["schema"] != SCHEMA or row["verdict"] != "PASS":
            fail(f"{where}: schema/verdict must be 1/PASS")
        if row["run_label"] != self.label:
            fail(f"{where}: unbound alternate run label")
        if row["source_freeze_sha256"] != self.freeze_hash:
            fail(f"{where}: receipt is bound to another source freeze")
        when = parse_time(row["created_utc"], where + ".created_utc")
        if when < self.freeze_time or when > self.manifest_time or when > self.now:
            fail(f"{where}: receipt predates freeze or postdates the closeout manifest")
        if (self.now - when).total_seconds() > self.max_age:
            fail(f"{where}: stale receipt")
        return when


def manifest_rows(path: Path, where: str) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for number, line in enumerate(path.read_text(encoding="ascii").splitlines(), 1):
        row = exact(strict_json(line, f"{where}:{number}"), {"mode", "path", "sha256", "size"}, f"{where}:{number}")
        name = row["path"]
        if not isinstance(name, str) or name in rows:
            fail(f"{where}:{number}: invalid/duplicate path")
        if row["mode"] not in {"100644", "100755", "120000", "160000"}:
            fail(f"{where}:{number}: invalid mode")
        integer(row["size"], f"{where}:{number}.size")
        if not isinstance(row["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"]):
            fail(f"{where}:{number}: invalid digest")
        rows[name] = row
    if not rows:
        fail(f"{where}: empty source manifest")
    return rows


def git_index_blob_payloads(
    source: Path,
    staged: dict[str, tuple[str, str]],
    names: list[str],
) -> dict[str, bytes]:
    """Read canonical index blobs in one batch for clean-filtered worktree files."""
    ordered = sorted(names, key=os.fsencode)
    if not ordered:
        return {}
    queries = b"".join(staged[name][1].encode("ascii") + b"\n" for name in ordered)
    result = subprocess.run(
        ["git", "-C", os.fspath(source), "cat-file", "--batch"],
        input=queries,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        fail(f"could not read canonical upstream index blobs: {result.stderr.decode('utf-8', 'replace').strip()}")
    stream = io.BytesIO(result.stdout)
    payloads: dict[str, bytes] = {}
    for name in ordered:
        header = stream.readline().rstrip(b"\n").split()
        expected_oid = staged[name][1].encode("ascii")
        if len(header) != 3 or header[0] != expected_oid or header[1] != b"blob":
            fail(f"could not parse canonical upstream index blob header: {name}")
        try:
            size = int(header[2])
        except ValueError:
            fail(f"canonical upstream index blob has invalid size: {name}")
        payload = stream.read(size)
        if len(payload) != size or stream.read(1) != b"\n":
            fail(f"canonical upstream index blob is truncated: {name}")
        payloads[name] = payload
    if stream.read(1):
        fail("canonical upstream index blob stream has trailing data")
    return payloads


def verify_source_freeze(ctx: Context, section: dict[str, Any]) -> None:
    refs = exact(section, {"receipt", "patch", "live_manifest", "replay_manifest"}, "manifest.source_freeze")
    receipt, receipt_hash, receipt_path = ctx.load_ref(refs["receipt"], "manifest.source_freeze.receipt")
    ctx.freeze_hash = receipt_hash
    receipt = exact(receipt, {
        "schema", "verdict", "created_utc", "source", "expected_pin",
        "recorded_pin_file", "git_version", "patch", "live_manifest",
        "replay_manifest", "ignored_worktree_paths", "checks",
    }, "source-freeze receipt")
    if receipt["schema"] != 1 or receipt["verdict"] != "PASS" or receipt["expected_pin"] != BLENDER_COMMIT:
        fail("source-freeze receipt: wrong schema/verdict/pin")
    ctx.freeze_time = parse_time(receipt["created_utc"], "source-freeze receipt.created_utc")
    if ctx.freeze_time > ctx.now or (ctx.now - ctx.freeze_time).total_seconds() > ctx.max_age:
        fail("source-freeze receipt is future-dated or stale")
    source = (ctx.root / "upstream").resolve(strict=True)
    if not isinstance(receipt["source"], str) or Path(receipt["source"]).resolve() != source:
        fail("source-freeze receipt: source is not the current upstream tree")
    if not isinstance(receipt["git_version"], str) or not receipt["git_version"].startswith("git version "):
        fail("source-freeze receipt: invalid git version")
    pin = exact(receipt["recorded_pin_file"], {"path", "sha256"}, "source-freeze recorded_pin_file")
    if not isinstance(pin["path"], str):
        fail("source-freeze recorded_pin_file.path: expected string")
    pin_path = ctx.path(os.path.relpath(pin["path"], ctx.root), "source-freeze recorded_pin_file.path") if os.path.isabs(pin["path"]) else ctx.path(pin["path"], "source-freeze recorded_pin_file.path")
    if pin_path != ctx.path("oracle/PIN", "source-freeze canonical recorded pin"):
        fail("source-freeze receipt: recorded pin file is not exactly oracle/PIN")
    if sha256(pin_path) != pin["sha256"] or BLENDER_COMMIT[:12] not in pin_path.read_text(encoding="utf-8"):
        fail("source-freeze receipt: recorded pin file mismatch")
    checks = exact(receipt["checks"], {
        "source_head_exact_pin", "source_real_index_pristine",
        "source_repository_operation_idle", "initialized_submodules_clean",
        "replay_started_pristine", "patch_regenerated_byte_exact",
        "manifest_replay_byte_exact", "live_resnapshot_byte_exact",
        "pin_and_ignore_inputs_stable", "outputs_created_without_overwrite",
    }, "source-freeze checks")
    if any(value is not True for value in checks.values()):
        fail("source-freeze receipt: not every replay check passed")
    ignored = exact(receipt["ignored_worktree_paths"], {"policy", "count", "nul_list_sha256"}, "source-freeze ignored_worktree_paths")
    ignored_raw = subprocess.run(
        ["git", "-C", os.fspath(source), "ls-files", "--others", "--ignored", "--exclude-standard", "-z"],
        check=True,
        capture_output=True,
    ).stdout
    ignored_names = sorted(name for name in ignored_raw.split(b"\0") if name)
    canonical_ignored = b"\0".join(ignored_names) + (b"\0" if ignored_names else b"")
    if ignored != {
        "policy": "excluded by the repository's standard Git ignore rules",
        "count": len(ignored_names),
        "nul_list_sha256": hashlib.sha256(canonical_ignored).hexdigest(),
    }:
        fail("source-freeze receipt: current ignored-path set differs from the freeze")

    freeze_dir = receipt_path.parent
    for name, ref_name in (("patch", "patch"), ("live_manifest", "live_manifest"), ("replay_manifest", "replay_manifest")):
        embedded = exact(receipt[name], {"path", "bytes", "sha256"} | ({"entries"} if name != "patch" else set()), f"source-freeze {name}")
        outer_path = ctx.file_ref(refs[ref_name], f"manifest.source_freeze.{ref_name}")
        if outer_path != (freeze_dir / embedded["path"]).resolve() or embedded["bytes"] != outer_path.stat().st_size or embedded["sha256"] != sha256(outer_path):
            fail(f"source-freeze {name}: outer and embedded identities differ")
    patch_path = ctx.file_ref(refs["patch"], "manifest.source_freeze.patch")
    if patch_path.stat().st_size == 0:
        fail("source-freeze patch is empty")
    live_path = ctx.file_ref(refs["live_manifest"], "manifest.source_freeze.live_manifest")
    replay_path = ctx.file_ref(refs["replay_manifest"], "manifest.source_freeze.replay_manifest")
    if live_path.read_bytes() != replay_path.read_bytes():
        fail("source-freeze replay manifest is not byte-exact")
    live = manifest_rows(live_path, "live source manifest")
    if receipt["live_manifest"]["entries"] != len(live) or receipt["replay_manifest"]["entries"] != len(live):
        fail("source-freeze manifest counters are stale")

    listed = subprocess.run(
        ["git", "-C", os.fspath(source), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        check=True, capture_output=True,
    ).stdout.split(b"\0")
    current_names = {os.fsdecode(name) for name in listed if name}
    decoded_live: dict[str, dict[str, Any]] = {}
    for encoded_name, row in live.items():
        raw_name = unquote_to_bytes(encoded_name)
        if quote_from_bytes(raw_name, safe="/-._~") != encoded_name:
            fail(f"source-freeze manifest contains a noncanonical encoded path: {encoded_name}")
        name = os.fsdecode(raw_name)
        pure = PurePosixPath(name)
        if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts) or name in decoded_live:
            fail(f"source-freeze manifest contains an unsafe/duplicate decoded path: {encoded_name}")
        decoded_live[name] = row
    if current_names != set(decoded_live):
        fail("current upstream path set differs from frozen live manifest")
    stage_raw = subprocess.run(
        ["git", "-C", os.fspath(source), "ls-files", "--stage", "-z"],
        check=True, capture_output=True,
    ).stdout
    staged: dict[str, tuple[str, str]] = {}
    for item in stage_raw.split(b"\0"):
        if not item:
            continue
        header, raw_name = item.split(b"\t", 1)
        mode_raw, oid_raw, stage = header.split(b" ", 2)
        if stage != b"0":
            fail("current upstream index contains a non-stage-zero entry")
        staged[os.fsdecode(raw_name)] = (mode_raw.decode("ascii"), oid_raw.decode("ascii"))
    changed_raw = subprocess.run(
        ["git", "-C", os.fspath(source), "diff", "--name-only", "--no-renames", "-z", "--"],
        check=True,
        capture_output=True,
    ).stdout
    changed_names = {os.fsdecode(name) for name in changed_raw.split(b"\0") if name}
    index_fallback: list[str] = []
    for name, row in decoded_live.items():
        path = source / name
        if row["mode"] == "160000":
            metadata = staged.get(name)
            if metadata is None or metadata[0] != "160000":
                fail(f"current upstream gitlink mode differs from freeze: {name}")
            payload = metadata[1].encode("ascii")
            if len(payload) != row["size"] or hashlib.sha256(payload).hexdigest() != row["sha256"]:
                fail(f"current upstream gitlink identity differs from freeze: {name}")
            continue
        if row["mode"] == "120000":
            if not path.is_symlink():
                fail(f"current upstream symlink mode differs from freeze: {name}")
            payload = os.fsencode(os.readlink(path))
        else:
            if path.is_symlink() or not path.is_file():
                fail(f"current upstream file type differs from freeze: {name}")
            current_mode = "100755" if path.stat().st_mode & 0o111 else "100644"
            if current_mode != row["mode"]:
                fail(f"current upstream executable mode differs from freeze: {name}")
            if path.stat().st_size != row["size"]:
                payload = b""
            else:
                payload = path.read_bytes()
        if len(payload) != row["size"] or hashlib.sha256(payload).hexdigest() != row["sha256"]:
            metadata = staged.get(name)
            if row["mode"] != "120000" and metadata is not None and name not in changed_names:
                index_fallback.append(name)
                continue
            fail(f"current upstream bytes differ from freeze: {name}")
    for name, payload in git_index_blob_payloads(source, staged, index_fallback).items():
        row = decoded_live[name]
        if len(payload) != row["size"] or hashlib.sha256(payload).hexdigest() != row["sha256"]:
            fail(f"current upstream canonical index bytes differ from freeze: {name}")
    head = subprocess.run(["git", "-C", os.fspath(source), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    if head != BLENDER_COMMIT:
        fail("current upstream HEAD is not the exact Blender pin")
    if subprocess.run(["git", "-C", os.fspath(source), "diff", "--cached", "--quiet", BLENDER_COMMIT, "--"], check=False).returncode != 0:
        fail("current upstream real index is no longer pristine at the pin")
    if subprocess.run(["git", "-C", os.fspath(source), "ls-files", "--unmerged"], check=True, capture_output=True).stdout:
        fail("current upstream index contains unmerged entries")


def verify_m0(ctx: Context, receipt: dict[str, Any]) -> None:
    ctx.common(receipt, "m0", {"pins", "artifacts", "container", "ci", "reuse"})
    pins = exact(receipt["pins"], {"blender", "emsdk", "oracle"}, "m0.pins")
    if exact(pins["blender"], {"branch", "commit"}, "m0.pins.blender") != {"branch": BLENDER_BRANCH, "commit": BLENDER_COMMIT}:
        fail("m0: Blender branch/commit pin mismatch")
    expected_emsdk = {"version": EMSDK_VERSION, "release_commit": EMSDK_RELEASE_COMMIT, "repo_commit": EMSDK_REPO_COMMIT, "compiler_commit": EMCC_COMMIT}
    if exact(pins["emsdk"], set(expected_emsdk), "m0.pins.emsdk") != expected_emsdk:
        fail("m0: emsdk pin mismatch")
    if exact(pins["oracle"], {"version", "commit"}, "m0.pins.oracle") != {"version": "5.2.0", "commit": BLENDER_COMMIT}:
        fail("m0: oracle pin mismatch")
    artifacts = exact(receipt["artifacts"], set(M0_ARTIFACTS), "m0.artifacts")
    paths = {key: ctx.file_ref(artifacts[key], f"m0.artifacts.{key}", path) for key, path in M0_ARTIFACTS.items()}
    if any(not paths[name].stat().st_mode & 0o111 for name in (
        "buildwrap", "ninja_locked", "oracle_wrapper", "native_oracle"
    )):
        fail("m0: required wrappers are not executable")
    if BLENDER_COMMIT[:12] not in paths["oracle_pin"].read_text(encoding="utf-8"):
        fail("m0: oracle/PIN lacks exact source pin")
    toolchain = paths["oracle_toolchain"].read_text(encoding="utf-8")
    for token in (EMSDK_VERSION, EMSDK_RELEASE_COMMIT, EMCC_COMMIT):
        if token not in toolchain:
            fail(f"m0: oracle/TOOLCHAIN lacks {token}")
    workflow = paths["ci_workflow"].read_text(encoding="utf-8")
    for token in ("EM_CACHE", "CCACHE_DIR", "reuse-action", "actions/cache", EMSDK_VERSION, EMSDK_REPO_COMMIT):
        if token not in workflow:
            fail(f"m0: CI workflow lacks required control {token}")
    ci = exact(receipt["ci"], {"em_cache", "ccache", "reuse_lint", "pinned_actions", "static_selfcheck", "runtime_check"}, "m0.ci")
    if any(value is not True for value in ci.values()):
        fail("m0: every CI contract flag must be true")
    container = exact(receipt["container"], {"image_digest", "proof"}, "m0.container")
    if not isinstance(container["image_digest"], str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", container["image_digest"]):
        fail("m0: container image is not digest-pinned")
    proof, _, _ = ctx.load_ref(container["proof"], "m0.container.proof")
    exact(proof, {"schema", "verdict", "run_label", "image_digest", "blender_version", "blender_commit", "oiiotool_version", "exit_code"}, "m0 container proof")
    if proof != {"schema": 1, "verdict": "PASS", "run_label": ctx.label, "image_digest": container["image_digest"], "blender_version": "5.2.0", "blender_commit": BLENDER_COMMIT, "oiiotool_version": "2.4.17.0", "exit_code": 0}:
        fail("m0: container execution proof mismatch")
    reuse = exact(receipt["reuse"], {"proof", "exit_code", "violations"}, "m0.reuse")
    reuse_proof, _, _ = ctx.load_ref(reuse["proof"], "m0.reuse.proof")
    exact(reuse_proof, {"schema", "verdict", "run_label", "source_freeze_sha256", "reuse_config_sha256", "exit_code", "violations"}, "m0 REUSE proof")
    if reuse_proof != {"schema": 1, "verdict": "PASS", "run_label": ctx.label, "source_freeze_sha256": ctx.freeze_hash, "reuse_config_sha256": sha256(paths["reuse_config"]), "exit_code": 0, "violations": 0}:
        fail("m0: REUSE proof is stale, unbound, or red")
    if reuse["exit_code"] != 0 or reuse["violations"] != 0:
        fail("m0: REUSE lint is not green")


def cmake_config_from_cache(
    path: Path, where: str, *, wasm: bool, root: Path
) -> dict[str, Any]:
    wanted = {
        "CMAKE_BUILD_TYPE", "CMAKE_GENERATOR", "CMAKE_HOME_DIRECTORY",
        "CMAKE_TOOLCHAIN_FILE", "WITH_GMP",
        "WITH_TESTS_SINGLE_BINARY", "WITH_TESTS_BMESH_CORE_PARITY",
    }
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw or raw.startswith(("#", "//")) or "=" not in raw or ":" not in raw.split("=", 1)[0]:
            continue
        typed, value = raw.split("=", 1)
        key, _kind = typed.split(":", 1)
        if key in wanted:
            if key in values:
                fail(f"{where}: duplicate CMake cache key {key}")
            values[key] = value
    if not {
        "CMAKE_BUILD_TYPE", "CMAKE_GENERATOR", "CMAKE_HOME_DIRECTORY",
        "WITH_GMP", "WITH_TESTS_SINGLE_BINARY",
        "WITH_TESTS_BMESH_CORE_PARITY",
    } <= set(values):
        fail(f"{where}: missing required CMake cache keys")
    if values["CMAKE_BUILD_TYPE"] != "Release" or any(
        values[key] not in {"ON", "OFF"}
        for key in ("WITH_GMP", "WITH_TESTS_SINGLE_BINARY", "WITH_TESTS_BMESH_CORE_PARITY")
    ):
        fail(f"{where}: noncanonical M1 CMake configuration")
    if values["CMAKE_GENERATOR"] != "Ninja" or Path(values["CMAKE_HOME_DIRECTORY"]).resolve() != (root / "upstream").resolve():
        fail(f"{where}: wrong generator/source root")
    toolchain = values.get("CMAKE_TOOLCHAIN_FILE", "")
    expected_toolchain = (
        root / "tools/emsdk/upstream/emscripten/cmake/Modules/Platform/Emscripten.cmake"
    ).resolve()
    if (wasm and (not toolchain or Path(toolchain).resolve() != expected_toolchain)) or (
        not wasm and bool(toolchain)
    ):
        fail(f"{where}: wrong exact native/Wasm toolchain")
    return {
        "build_type": "Release", "generator": "Ninja", "source_root": "upstream",
        "toolchain": "emscripten" if wasm else "native",
        "with_gmp": values["WITH_GMP"] == "ON",
        "with_tests_single_binary": values["WITH_TESTS_SINGLE_BINARY"] == "ON",
        "with_tests_bmesh_core_parity": values["WITH_TESTS_BMESH_CORE_PARITY"] == "ON",
    }


def verify_ninja_output_rule(
    ninja: Path, artifact: Path, suite: str, *, wasm: bool, root: Path, where: str
) -> None:
    build_root = root / ("build-wasm-m1-parity" if wasm else "build-native-m1-parity")
    expected = build_root / "bin/tests" / {
        ("blenlib", False): "BLI_test",
        ("blenlib", True): "BLI_test.js",
        ("bmesh_core", False): "bmesh_core_test",
        ("bmesh_core", True): "bmesh_core_test.js",
    }[(suite, wasm)]
    if artifact.resolve() != expected.resolve() or ninja.resolve() != (build_root / "build.ninja").resolve():
        fail(f"{where}: artifact/build.ninja is outside the canonical parity root")
    output = expected.relative_to(build_root).as_posix()
    prefix = f"build {output}: "
    lines = ninja.read_text(encoding="utf-8").splitlines()
    indexes = [index for index, line in enumerate(lines) if line.startswith(prefix)]
    if len(indexes) != 1 or "EXECUTABLE_LINKER" not in lines[indexes[0]]:
        fail(f"{where}: no unique executable output rule")
    start = indexes[0]
    end = next((index for index in range(start + 1, len(lines))
                if lines[index].startswith("build ")), len(lines))
    rule = "\n".join(lines[start:end])
    object_side = lines[start].split(" | ", 1)[0]
    if suite == "blenlib":
        marker = "source/blender/blenlib/CMakeFiles/BLI_test.dir/tests/"
        if marker not in object_side or "blender_test.dir" in object_side:
            fail(f"{where}: BLI target provenance is not complete/dedicated")
    else:
        marker = "source/blender/bmesh/CMakeFiles/bmesh_core_test.dir/tests/bmesh_core_test.cc.o"
        if object_side.count(".cc.o") != 1 or marker not in object_side or "blender_test.dir" in object_side:
            fail(f"{where}: bmesh target provenance is not exact one-source")
    allocator_settings = emscripten_setting_values(rule, "MALLOC", where)
    expected_allocators: list[str] = []
    if wasm:
        expected_allocators = ["mimalloc"] if suite == "blenlib" else [
            "mimalloc", "dlmalloc"
        ]
    if allocator_settings != expected_allocators:
        fail(
            f"{where}: allocator settings differ: expected={expected_allocators!r} "
            f"actual={allocator_settings!r}"
        )
    initial_memory_settings = emscripten_setting_values(
        rule, "INITIAL_MEMORY", where
    )
    legacy_memory_settings = emscripten_setting_values(rule, "TOTAL_MEMORY", where)
    try:
        link_tokens = shlex.split(rule, posix=True)
    except ValueError as error:
        fail(f"{where}: invalid shell tokenization in Ninja link rule: {error}")
    direct_linker_memory = [
        token for token in link_tokens if "--initial-memory" in token
    ]
    expected_initial_memory = ["33554432"] if wasm and suite == "bmesh_core" else []
    if (
        initial_memory_settings != expected_initial_memory
        or legacy_memory_settings
        or direct_linker_memory
    ):
        fail(
            f"{where}: initial-memory settings differ: "
            f"expected={expected_initial_memory!r} actual={initial_memory_settings!r} "
            f"legacy={legacy_memory_settings!r} direct_linker={direct_linker_memory!r}"
        )


def emscripten_setting_values(command: str, setting: str, where: str) -> list[str]:
    """Parse every Emscripten-supported ``-s`` spelling for one setting."""
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError as error:
        fail(f"{where}: invalid shell tokenization in Ninja link rule: {error}")
    values: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        value: str | None = None
        consumed = 1
        if token == "-s" and index + 1 < len(tokens):
            following = tokens[index + 1]
            if following.startswith(setting + "="):
                value = following.split("=", 1)[1]
                consumed = 2
            elif following == setting:
                # Match the pinned cmdline.py parser: a bare setting is 1 and
                # the following token remains positional.
                value = "1"
                consumed = 2
        elif token == f"-s{setting}":
            value = "1"
        elif token.startswith(f"-s{setting}="):
            value = token.split("=", 1)[1]
        if value is not None:
            if re.fullmatch(r"[A-Za-z0-9_-]+", value) is None:
                fail(f"{where}: Emscripten {setting} has noncanonical value: {value!r}")
            values.append(value)
        index += consumed
    return values


def verify_gtest_occurrence_names(names: list[str], where: str) -> None:
    encoded: dict[str, list[int]] = {}
    plain: set[str] = set()
    for name in names:
        marker = "@occurrence="
        if marker not in name:
            plain.add(name)
            continue
        match = re.fullmatch(r"(.+)@occurrence=([1-9][0-9]*)", name)
        if match is None or marker in match.group(1):
            fail(f"{where}: noncanonical duplicate-registration occurrence name {name}")
        encoded.setdefault(match.group(1), []).append(int(match.group(2)))
    for base, occurrences in encoded.items():
        if base in plain or sorted(occurrences) != list(range(1, len(occurrences) + 1)) or len(occurrences) < 2:
            fail(f"{where}: invalid duplicate-registration occurrence encoding for {base}")


GTEST_ARGUMENT_PHASES = {"native_list", "wasm_list", "native_run", "wasm_run"}
NINJA_NO_WORK_STDOUT = b"ninja: no work to do.\n"


def reject_symlink_components(path: Path, where: str) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            fail(f"{where}: symlink path component is not accepted: {current}")


def expected_gtest_arguments(root: Path, suite: str, where: str) -> list[str]:
    if suite == "bmesh_core":
        return []
    if suite != "blenlib":
        fail(f"{where}: unknown gtest suite argument contract")
    try:
        canonical_root = root.resolve(strict=True)
    except OSError as error:
        fail(f"{where}: M1 root is missing: {error}")
    lexical = canonical_root / "upstream/tests/files"
    reject_symlink_components(lexical, where + ".test_assets")
    try:
        resolved = lexical.resolve(strict=True)
    except OSError as error:
        fail(f"{where}: BLI test-assets path is missing: {error}")
    if resolved != lexical or not lexical.is_dir():
        fail(f"{where}: BLI test-assets path is not a canonical directory")
    return ["--test-assets-dir", str(lexical)]


def verify_gtest_arguments(value: Any, root: Path, suite: str, where: str) -> dict[str, Any]:
    arguments = exact(value, GTEST_ARGUMENT_PHASES, where)
    expected = expected_gtest_arguments(root, suite, where)
    for phase in sorted(GTEST_ARGUMENT_PHASES):
        if arguments[phase] != expected:
            fail(
                f"{where}.{phase}: expected exact supplemental arguments "
                f"{expected!r}, got {arguments[phase]!r}"
            )
    return arguments


def ninja_locked_command(*arguments: str) -> list[str]:
    """Return the canonical repository-relative locked Ninja invocation."""
    return [NINJA_LOCKED_RELATIVE, *arguments]


def require_ninja_no_work_result(
    command: Any,
    cwd: Path,
    returncode: Any,
    stdout: bytes,
    stderr: bytes,
    *,
    expected_build_root: Path,
    expected_target: str,
    where: str,
) -> None:
    """Reject stale, failed, redirected, or noncanonical Ninja dry-runs."""
    if command != ninja_locked_command("-n", expected_target):
        fail(f"{where}: Ninja no-work command targets the wrong output")
    if cwd.resolve() != expected_build_root.resolve():
        fail(f"{where}: Ninja no-work command uses the wrong build root")
    if isinstance(returncode, bool) or returncode != 0:
        fail(f"{where}: Ninja no-work command did not exit zero")
    if stdout != NINJA_NO_WORK_STDOUT or stderr != b"":
        fail(f"{where}: Ninja dry-run reports work, diagnostics, or noncanonical output")


def verify_ninja_no_work(
    ctx: Context, value: Any, suite: str, *, wasm: bool, where: str
) -> dict[str, Any]:
    row = exact(
        value,
        {"command", "cwd", "target", "returncode", "stdout", "stderr"},
        where,
    )
    build_name = "build-wasm-m1-parity" if wasm else "build-native-m1-parity"
    build_root = ctx.root / build_name
    target = "bin/tests/" + {
        ("blenlib", False): "BLI_test",
        ("blenlib", True): "BLI_test.js",
        ("bmesh_core", False): "bmesh_core_test",
        ("bmesh_core", True): "bmesh_core_test.js",
    }[(suite, wasm)]
    if row["cwd"] != build_name or row["target"] != target:
        fail(f"{where}: Ninja no-work build root/target is not canonical")
    stdout_path = ctx.file_ref(row["stdout"], where + ".stdout")
    stderr_path = ctx.file_ref(row["stderr"], where + ".stderr")
    require_ninja_no_work_result(
        row["command"],
        build_root,
        row["returncode"],
        stdout_path.read_bytes(),
        stderr_path.read_bytes(),
        expected_build_root=build_root,
        expected_target=target,
        where=where + ".recorded",
    )
    try:
        command = ninja_locked_command("-n", target)
        live = subprocess.run(
            command,
            cwd=build_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        fail(f"{where}: could not independently repeat Ninja dry-run: {error}")
    require_ninja_no_work_result(
        command,
        build_root,
        live.returncode,
        live.stdout,
        live.stderr,
        expected_build_root=build_root,
        expected_target=target,
        where=where + ".live",
    )
    return row


def verify_gtest(
    ctx: Context, value: Any, where: str, expected_suite: str, minimum_total: int
) -> None:
    row = exact(
        value,
        {
            "native_executable",
            "javascript",
            "wasm",
            "native_cmake_cache",
            "wasm_cmake_cache",
            "native_build_ninja",
            "wasm_build_ninja",
            "no_work",
            "test_arguments",
            "configuration",
            "raw_result",
            "native_manifest",
            "wasm_manifest",
            "total",
            "passed",
            "failed",
            "crashed",
            "native_keyset_sha256",
            "wasm_keyset_sha256",
        },
        where,
    )
    native_executable = ctx.file_ref(row["native_executable"], where + ".native_executable")
    javascript = ctx.file_ref(row["javascript"], where + ".javascript")
    ctx.file_ref(row["wasm"], where + ".wasm")
    native_cache = ctx.file_ref(row["native_cmake_cache"], where + ".native_cmake_cache")
    wasm_cache = ctx.file_ref(row["wasm_cmake_cache"], where + ".wasm_cmake_cache")
    native_ninja = ctx.file_ref(row["native_build_ninja"], where + ".native_build_ninja")
    wasm_ninja = ctx.file_ref(row["wasm_build_ninja"], where + ".wasm_build_ninja")
    no_work_value = exact(row["no_work"], {"native", "wasm"}, where + ".no_work")
    no_work = {
        "native": verify_ninja_no_work(
            ctx, no_work_value["native"], expected_suite, wasm=False,
            where=where + ".no_work.native",
        ),
        "wasm": verify_ninja_no_work(
            ctx, no_work_value["wasm"], expected_suite, wasm=True,
            where=where + ".no_work.wasm",
        ),
    }
    test_arguments = verify_gtest_arguments(
        row["test_arguments"], ctx.root, expected_suite, where + ".test_arguments"
    )
    if native_cache.resolve() != (ctx.root / "build-native-m1-parity/CMakeCache.txt").resolve() or \
            wasm_cache.resolve() != (ctx.root / "build-wasm-m1-parity/CMakeCache.txt").resolve():
        fail(f"{where}: CMake caches are outside the canonical parity roots")
    configuration = exact(row["configuration"], {"native", "wasm"}, where + ".configuration")
    expected_configs: dict[str, dict[str, Any]] = {}
    for platform, toolchain in (("native", "native"), ("wasm", "emscripten")):
        config = exact(
            configuration[platform],
            {
                "build_type", "generator", "source_root", "toolchain", "with_gmp", "with_tests_single_binary",
                "with_tests_bmesh_core_parity",
            },
            f"{where}.configuration.{platform}",
        )
        if config["build_type"] != "Release" or config["generator"] != "Ninja" or config["source_root"] != "upstream" or config["toolchain"] != toolchain:
            fail(f"{where}: wrong {platform} build type/toolchain")
        if not all(isinstance(config[key], bool) for key in (
            "with_gmp", "with_tests_single_binary", "with_tests_bmesh_core_parity"
        )):
            fail(f"{where}: implicit/non-boolean CMake configuration")
        expected_configs[platform] = config
    if expected_configs["native"] != cmake_config_from_cache(native_cache, where + ".native_cmake_cache", wasm=False, root=ctx.root) or expected_configs["wasm"] != cmake_config_from_cache(wasm_cache, where + ".wasm_cmake_cache", wasm=True, root=ctx.root):
        fail(f"{where}: embedded configuration does not match bound CMake cache")
    verify_ninja_output_rule(native_ninja, native_executable, expected_suite, wasm=False, root=ctx.root, where=where + ".native")
    verify_ninja_output_rule(wasm_ninja, javascript, expected_suite, wasm=True, root=ctx.root, where=where + ".wasm")
    for platform in ("native", "wasm"):
        config = expected_configs[platform]
        if config["with_gmp"] or not config["with_tests_single_binary"] or not config["with_tests_bmesh_core_parity"]:
            fail(
                f"{where}: {platform} parity requires WITH_GMP=OFF, "
                "WITH_TESTS_SINGLE_BINARY=ON, and WITH_TESTS_BMESH_CORE_PARITY=ON"
            )
    if expected_suite == "blenlib":
        if native_executable.name != "BLI_test" or javascript.name != "BLI_test.js":
            fail(f"{where}: blenlib evidence is not from complete BLI_test executables")
    if expected_suite == "bmesh_core":
        if native_executable.name != "bmesh_core_test" or javascript.name != "bmesh_core_test.js":
            fail(f"{where}: bmesh evidence is not from dedicated executables")
    native_manifest = ctx.file_ref(row["native_manifest"], where + ".native_manifest")
    wasm_manifest = ctx.file_ref(row["wasm_manifest"], where + ".wasm_manifest")
    native_names = native_manifest.read_text(encoding="utf-8").splitlines()
    wasm_names = wasm_manifest.read_text(encoding="utf-8").splitlines()
    total = integer(row["total"], where + ".total", minimum_total)
    expected_total = 1667 if expected_suite == "blenlib" else 1
    if total != expected_total:
        fail(f"{where}: suite census must be exactly {expected_total}")
    for names, label in ((native_names, "native"), (wasm_names, "wasm")):
        if len(names) != total or len(set(names)) != total or any(
            not name or name.strip() != name for name in names
        ):
            fail(f"{where}: {label} manifest is not {total} unique canonical test names")
        verify_gtest_occurrence_names(names, f"{where}.{label}_manifest")
    if native_names != wasm_names:
        fail(f"{where}: native/wasm test manifests differ")
    if expected_suite == "bmesh_core" and native_names != ["BMeshCoreTest.BMVertCreate"]:
        fail(f"{where}: bmesh executable does not enumerate the exact one-test suite")
    raw, _, _ = ctx.load_ref(row["raw_result"], where + ".raw_result")
    exact(raw, {"schema", "verdict", "run_label", "source_freeze_sha256", "suite", "total", "passed", "failed", "crashed", "test_names_sha256", "native_executable_sha256", "javascript_sha256", "wasm_sha256", "native_cmake_cache_sha256", "wasm_cmake_cache_sha256", "native_build_ninja_sha256", "wasm_build_ninja_sha256", "no_work", "test_arguments"}, where + ".raw")
    if (row["total"], row["passed"], row["failed"], row["crashed"]) != (total, total, 0, 0):
        fail(f"{where}: enumerated suite is not {total}/{total} all-pass")
    if (raw["total"], raw["passed"], raw["failed"], raw["crashed"]) != (total, total, 0, 0):
        fail(f"{where}: raw result is not all-pass")
    if raw["schema"] != 1 or raw["verdict"] != "PASS" or raw["run_label"] != ctx.label or raw["source_freeze_sha256"] != ctx.freeze_hash or raw["suite"] != expected_suite or raw["native_executable_sha256"] != row["native_executable"]["sha256"] or raw["javascript_sha256"] != row["javascript"]["sha256"] or raw["wasm_sha256"] != row["wasm"]["sha256"] or raw["native_cmake_cache_sha256"] != row["native_cmake_cache"]["sha256"] or raw["wasm_cmake_cache_sha256"] != row["wasm_cmake_cache"]["sha256"] or raw["native_build_ninja_sha256"] != row["native_build_ninja"]["sha256"] or raw["wasm_build_ninja_sha256"] != row["wasm_build_ninja"]["sha256"] or raw["no_work"] != no_work or raw["test_arguments"] != test_arguments:
        fail(f"{where}: raw result is not bound to this run/artifact pair")
    native_manifest_sha256 = sha256(native_manifest)
    wasm_manifest_sha256 = sha256(wasm_manifest)
    if (
        row["native_keyset_sha256"] != native_manifest_sha256
        or row["wasm_keyset_sha256"] != wasm_manifest_sha256
        or native_manifest_sha256 != wasm_manifest_sha256
        or raw["test_names_sha256"] != wasm_manifest_sha256
    ):
        fail(f"{where}: native/wasm test keysets differ")


def canonical_runtime_ref(
    ctx: Context, value: Any, expected_path: str, where: str
) -> Path:
    lexical = ctx.root / expected_path
    reject_symlink_components(lexical, where)
    path = ctx.file_ref(value, where, expected_path)
    if lexical.is_symlink() or path != lexical.resolve(strict=True):
        fail(f"{where}: runtime path is not the exact non-symlink canonical file")
    return path


def verify_m1_runtime_no_work(ctx: Context, value: Any) -> dict[str, Any]:
    where = "m1.runtime.no_work"
    row = exact(
        value, {"command", "cwd", "target", "returncode", "stdout", "stderr"}, where
    )
    build_root = ctx.root / "build-wasm-m1-parity"
    target = "blender"
    if row["cwd"] != "build-wasm-m1-parity" or row["target"] != target:
        fail(f"{where}: build root/target is not canonical")
    stdout_path = ctx.file_ref(row["stdout"], where + ".stdout")
    stderr_path = ctx.file_ref(row["stderr"], where + ".stderr")
    require_ninja_no_work_result(
        row["command"], build_root, row["returncode"],
        stdout_path.read_bytes(), stderr_path.read_bytes(),
        expected_build_root=build_root, expected_target=target, where=where + ".recorded",
    )
    try:
        command = ninja_locked_command("-n", target)
        live = subprocess.run(
            command, cwd=build_root, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=120, check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        fail(f"{where}: could not independently repeat Ninja dry-run: {error}")
    require_ninja_no_work_result(
        command, build_root, live.returncode, live.stdout, live.stderr,
        expected_build_root=build_root, expected_target=target, where=where + ".live",
    )
    return row


def verify_m1(ctx: Context, receipt: dict[str, Any]) -> None:
    ctx.common(receipt, "m1", {"gtests", "runtime", "main_corpus", "versioning"})
    runtime = exact(receipt["runtime"], {
        "native_oracle", "node", "javascript", "wasm", "cmake_cache", "build_ninja",
        "node_version", "worker_boot", "no_work", "raw_provenance",
    }, "m1.runtime")
    native_oracle = canonical_runtime_ref(
        ctx, runtime["native_oracle"], "oracle/bpy.sh", "m1.runtime.native_oracle"
    )
    node = canonical_runtime_ref(
        ctx, runtime["node"], "tools/emsdk/node/22.16.0_64bit/bin/node", "m1.runtime.node"
    )
    javascript = canonical_runtime_ref(
        ctx, runtime["javascript"], "build-wasm-m1-parity/bin/blender.js",
        "m1.runtime.javascript",
    )
    wasm = canonical_runtime_ref(
        ctx, runtime["wasm"], "build-wasm-m1-parity/bin/blender.wasm", "m1.runtime.wasm"
    )
    cmake_cache = canonical_runtime_ref(
        ctx, runtime["cmake_cache"], "build-wasm-m1-parity/CMakeCache.txt",
        "m1.runtime.cmake_cache",
    )
    build_ninja = canonical_runtime_ref(
        ctx, runtime["build_ninja"], "build-wasm-m1-parity/build.ninja",
        "m1.runtime.build_ninja",
    )
    if runtime["node_version"] != "v22.16.0" or runtime["worker_boot"] is not True:
        fail("m1: wrong Node runtime or worker did not boot")
    live_node_version = subprocess.run(
        [os.fspath(node), "--version"], capture_output=True, text=True,
        timeout=30, check=True,
    ).stdout.strip()
    if live_node_version != runtime["node_version"]:
        fail("m1: current canonical Node version differs from receipt")
    cmake_config_from_cache(cmake_cache, "m1.runtime.cmake_cache", wasm=True, root=ctx.root)
    no_work = verify_m1_runtime_no_work(ctx, runtime["no_work"])
    raw, _, _ = ctx.load_ref(runtime["raw_provenance"], "m1.runtime.raw_provenance")
    expected_raw = {
        "schema": 1, "verdict": "PASS", "run_label": ctx.label,
        "created_utc": receipt["created_utc"], "source_freeze_sha256": ctx.freeze_hash,
        "native_oracle_sha256": sha256(native_oracle), "node_sha256": sha256(node),
        "node_version": runtime["node_version"], "javascript_sha256": sha256(javascript),
        "wasm_sha256": sha256(wasm), "cmake_cache_sha256": sha256(cmake_cache),
        "build_ninja_sha256": sha256(build_ninja), "no_work": no_work,
    }
    exact(raw, set(expected_raw), "m1.runtime raw provenance")
    if raw != expected_raw:
        fail("m1: runtime raw provenance is not bound to current canonical inputs")
    gtests = exact(receipt["gtests"], {"blenlib", "bmesh_core"}, "m1.gtests")
    for key in (
        "native_cmake_cache", "wasm_cmake_cache",
        "native_build_ninja", "wasm_build_ninja",
    ):
        if gtests["blenlib"].get(key) != gtests["bmesh_core"].get(key):
            fail(f"m1: BLI and bmesh must share the exact {key} parity build input")
    verify_gtest(ctx, gtests["blenlib"], "m1.gtests.blenlib", "blenlib", 1667)
    verify_gtest(ctx, gtests["bmesh_core"], "m1.gtests.bmesh_core", "bmesh_core", 1)
    main = exact(receipt["main_corpus"], {"manifest", "total", "equal", "rows"}, "m1.main_corpus")
    ctx.file_ref(main["manifest"], "m1.main_corpus.manifest")
    if main["total"] != 9 or main["equal"] != 9:
        fail("m1: main corpus counters must be exactly 9/9")
    rows = exact(main["rows"], MAIN_CORPUS, "m1.main_corpus.rows")
    for name, value in rows.items():
        row = exact(value, {"blend", "native_dump", "wasm_dump", "native_state_sha256", "wasm_state_sha256", "equal"}, f"m1.main_corpus.rows.{name}")
        for key in ("blend", "native_dump", "wasm_dump"):
            ctx.file_ref(row[key], f"m1.main_corpus.rows.{name}.{key}")
        if row["equal"] is not True or row["native_state_sha256"] != row["wasm_state_sha256"]:
            fail(f"m1: non-exact native state parity for {name}")
        if sha256(ctx.file_ref(row["native_dump"], f"m1.main_corpus.rows.{name}.native_dump.recheck")) != row["native_state_sha256"] or sha256(ctx.file_ref(row["wasm_dump"], f"m1.main_corpus.rows.{name}.wasm_dump.recheck")) != row["wasm_state_sha256"]:
            fail(f"m1: state digest is not bound to dump bytes for {name}")
    versioning = exact(receipt["versioning"], {"manifest", "total", "pass", "oracle_refuse", "equal", "rows"}, "m1.versioning")
    ctx.file_ref(versioning["manifest"], "m1.versioning.manifest")
    if (versioning["total"], versioning["pass"], versioning["oracle_refuse"], versioning["equal"]) != (12, 10, 2, 12):
        fail("m1: versioning counters must be exactly total=12 pass=10 refuse=2 equal=12")
    vrows = exact(versioning["rows"], VERSIONING_PASS | VERSIONING_REFUSE, "m1.versioning.rows")
    for name, value in vrows.items():
        row = exact(value, {"blend", "native_result", "wasm_result", "native_outcome", "wasm_outcome", "native_state_sha256", "wasm_state_sha256", "equal"}, f"m1.versioning.rows.{name}")
        ctx.file_ref(row["blend"], f"m1.versioning.rows.{name}.blend")
        native_result = ctx.file_ref(row["native_result"], f"m1.versioning.rows.{name}.native_result")
        wasm_result = ctx.file_ref(row["wasm_result"], f"m1.versioning.rows.{name}.wasm_result")
        expected = "PASS" if name in VERSIONING_PASS else "ORACLE_REFUSE"
        if row["native_outcome"] != expected or row["wasm_outcome"] != expected or row["equal"] is not True or row["native_state_sha256"] != row["wasm_state_sha256"] or sha256(native_result) != row["native_state_sha256"] or sha256(wasm_result) != row["wasm_state_sha256"]:
            fail(f"m1: versioning native parity mismatch for {name}")


def active_deferrals(path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    try:
        ledger = strict_json(path.read_text(encoding="utf-8"), "deferral registry")
    except OSError as error:
        fail(f"deferral registry: invalid JSON: {error}")
    if not isinstance(ledger, dict) or not isinstance(ledger.get("deferred"), list):
        fail("deferral registry: missing deferred array")
    found: dict[str, dict[str, Any]] = {}
    for number, row in enumerate(ledger["deferred"]):
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or row["id"] in found:
            fail(f"deferral registry: invalid/duplicate row {number}")
        found[row["id"]] = row
    detector = found.get(M2_DETECTOR_ACTIVE_ID)
    if detector is None or detector.get("status") != M2_DETECTOR_ACTIVE_STATUS:
        fail(
            f"deferral registry: {M2_DETECTOR_ACTIVE_ID} must retain exact "
            f"{M2_DETECTOR_ACTIVE_STATUS} status"
        )
    if not isinstance(detector.get("evidence"), str) or not detector["evidence"]:
        fail(f"deferral registry: {M2_DETECTOR_ACTIVE_ID} lacks exact evidence")
    for name, row in found.items():
        if row.get("status") == M2_DETECTOR_ACTIVE_STATUS and name != M2_DETECTOR_ACTIVE_ID:
            fail(f"deferral registry: unexpected {M2_DETECTOR_ACTIVE_STATUS} row {name}")
    active = {
        name: row for name, row in found.items()
        if row.get("status") in {"deferred", "partial"}
        or (name == M2_DETECTOR_ACTIVE_ID
            and row.get("status") == M2_DETECTOR_ACTIVE_STATUS)
    }
    return active, ledger


def m2_strip_platform_envelope(payload: bytes, *, wasm: bool) -> bytes:
    """Independently replay the producer's byte-splice envelope policy."""
    lines = payload.splitlines(keepends=True)
    allocator_rows = [
        (index, line[:-len(M2_ALLOCATOR_LINE)])
        for index, line in enumerate(lines[:-1])
        if line.endswith(M2_ALLOCATOR_LINE)
        and (
            not (set(line[:-len(M2_ALLOCATOR_LINE)]) - {ord(".")})
            or M2_VERBOSE_UNITTEST_PROGRESS_RE.fullmatch(
                line[:-len(M2_ALLOCATOR_LINE)]
            ) is not None
        )
    ]
    if wasm:
        pair_indexes = [
            (index, prefix) for index, prefix in allocator_rows
            if lines[index + 1] == M2_WASM_BANNER_LINE
        ]
        if len(pair_indexes) != 1:
            fail("m2: Wasm log lacks one exact adjacent allocator/banner envelope")
        pair_index, progress_prefix = pair_indexes[0]
        locale_indexes = [
            index for index, line in enumerate(lines)
            if M2_WASM_LOCALE_RE.fullmatch(line)
        ]
        if locale_indexes:
            if locale_indexes != [pair_index + 2]:
                fail("m2: Wasm locale warning is duplicated or outside its envelope")
        consumed = 3 if locale_indexes else 2
        lines[pair_index:pair_index + consumed] = (
            [progress_prefix] if progress_prefix else []
        )
    else:
        pair_indexes = [
            (index, prefix) for index, prefix in allocator_rows
            if M2_NATIVE_BANNER_RE.fullmatch(lines[index + 1]) is not None
        ]
        if len(pair_indexes) != 1:
            fail("m2: native log lacks one exact adjacent allocator/banner envelope")
        pair_index, progress_prefix = pair_indexes[0]
        lines[pair_index:pair_index + 2] = (
            [progress_prefix] if progress_prefix else []
        )
    return b"".join(lines)


def m2_canonicalize_keymap_inventory(payload: bytes) -> bytes:
    lines = payload.splitlines(keepends=True)
    if not lines or lines[0] != M2_KEYMAP_FIRST_HEADER:
        fail("m2: script_load_keymap lacks its exact first inventory header")
    try:
        second = lines.index(M2_KEYMAP_SECOND_HEADER, 1)
    except ValueError:
        fail("m2: script_load_keymap lacks its exact second inventory header")
    first_items = lines[1:second]
    second_end = second + 1 + 28
    second_items = lines[second + 1:second_end]
    if (len(first_items) != 159 or len(set(first_items)) != 159
            or any(re.fullmatch(rb"\t[ -~]+\n", line) is None for line in first_items)):
        fail("m2: script_load_keymap first inventory grammar/cardinality differs")
    if (len(second_items) != 28 or len(set(second_items)) != 28
            or any(re.fullmatch(
                rb"    \('[^'\n]+', '[A-Z0-9_]+', '[A-Z0-9_]+', \[\]\),\n", line
            ) is None for line in second_items)):
        fail("m2: script_load_keymap second inventory grammar/cardinality differs")
    if lines[second_end:] != M2_KEYMAP_TAIL:
        fail("m2: script_load_keymap output outside its inventories differs")
    return b"".join([
        M2_KEYMAP_FIRST_HEADER, *sorted(first_items), M2_KEYMAP_SECOND_HEADER,
        *sorted(second_items), *M2_KEYMAP_TAIL,
    ])


def m2_canonicalize_physics_records(payload: bytes, suite: str) -> bytes:
    blend_file, tests = M2_PHYSICS_ORDER[suite]
    canonical = [
        f'<LOG_TIME>  blend            | Read blend: "<REPO>/upstream/tests/files/physics/{blend_file}"\n'.encode(),
        b"\n",
    ]
    for name, frames in tests:
        canonical.append(f"START {name} test.\n".encode())
        canonical.extend(
            f"bake: frame {frame} :: {frames}\n".encode()
            for frame in range(1, frames + 1)
        )
        canonical.extend([
            f"PASSED {name} test successfully.\n".encode(),
            b"Results:\n", b"Mesh Comparison : Same\n",
            b"Mesh Validation : Valid\n", b"\n", b"\n",
        ])
    canonical.append(b"Blender quit\n")
    lines = payload.splitlines(keepends=True)
    if Counter(lines) != Counter(canonical):
        fail(f"m2: {suite} result/bake grammar or cardinality differs")
    return b"".join(canonical)


def m2_canonicalize_library_override_sets(payload: bytes) -> bytes:
    """Independently replay the exact two-token set inventory policy."""
    canonical = payload.count(M2_LIBRARY_OVERRIDE_SET_CANONICAL)
    reversed_count = payload.count(M2_LIBRARY_OVERRIDE_SET_REVERSED)
    if (canonical, reversed_count) not in {
        (M2_LIBRARY_OVERRIDE_SET_OCCURRENCES, 0),
        (0, M2_LIBRARY_OVERRIDE_SET_OCCURRENCES),
    }:
        fail(
            "m2: blendfile_library_overrides ID-pointer set "
            "order/cardinality differs"
        )
    return payload.replace(
        M2_LIBRARY_OVERRIDE_SET_REVERSED, M2_LIBRARY_OVERRIDE_SET_CANONICAL
    )


def m2_canonicalize_tempdir_progress(payload: bytes) -> bytes:
    """Independently replay bounded five-dot progress fragmentation."""
    if not payload.endswith(M2_TEMPDIR_RESULT_TAIL):
        fail("m2: script_pyapi_bpy_app_tempdir progress/result grammar differs")
    prefix = payload[:-len(M2_TEMPDIR_RESULT_TAIL)]
    if (
        not prefix.startswith(b"\n")
        or not prefix.endswith(b"\n")
        or set(prefix) - {ord("."), ord("\n")}
        or prefix.count(b".") != M2_TEMPDIR_PROGRESS_DOTS
        or prefix.count(b"\n") != M2_TEMPDIR_PROGRESS_NEWLINES
    ):
        fail("m2: script_pyapi_bpy_app_tempdir progress/result grammar differs")
    return M2_TEMPDIR_PROGRESS_CANONICAL + M2_TEMPDIR_RESULT_TAIL


def m2_canonicalize_prop_array_progress(payload: bytes) -> bytes:
    """Independently bind diagnostics and replay progress interleaving."""
    if not payload.endswith(M2_PROP_ARRAY_RESULT_TAIL):
        fail("m2: script_pyapi_prop_array progress/result grammar differs")
    body = payload[:-len(M2_PROP_ARRAY_RESULT_TAIL)]
    diagnostics = b"".join(M2_PROP_ARRAY_DIAGNOSTICS)
    if body.count(diagnostics) != 1:
        fail("m2: script_pyapi_prop_array diagnostic block differs")
    before, after = body.split(diagnostics)
    punctuation = before + after
    if (
        set(punctuation) - {ord("."), ord("\n")}
        or punctuation.count(b".") != M2_PROP_ARRAY_PROGRESS_DOTS
        or punctuation.count(b"\n") not in {1, 2}
    ):
        fail("m2: script_pyapi_prop_array progress cardinality differs")
    return (
        M2_PROP_ARRAY_PROGRESS_CANONICAL + diagnostics + M2_PROP_ARRAY_RESULT_TAIL
    )


def m2_canonicalize_text_progress(payload: bytes) -> bytes:
    """Independently replay bounded five-test progress fragmentation."""
    if not payload.endswith(M2_TEXT_RESULT_TAIL):
        fail("m2: script_pyapi_text progress/result grammar differs")
    progress = payload[:-len(M2_TEXT_RESULT_TAIL)]
    if (
        set(progress) - {ord("."), ord("\n")}
        or progress.count(b".") != M2_TEXT_PROGRESS_DOTS
        or progress.count(b"\n") not in M2_TEXT_PROGRESS_NEWLINES
    ):
        fail("m2: script_pyapi_text progress cardinality differs")
    return M2_TEXT_PROGRESS_CANONICAL + M2_TEXT_RESULT_TAIL


def m2_canonicalize_sequencer_strip_naming_progress(payload: bytes) -> bytes:
    """Independently replay bounded six-test progress fragmentation."""
    if not payload.endswith(M2_SEQUENCER_STRIP_NAMING_RESULT_TAIL):
        fail("m2: sequencer_strip_naming progress/result grammar differs")
    progress = payload[:-len(M2_SEQUENCER_STRIP_NAMING_RESULT_TAIL)]
    if (
        set(progress) - {ord("."), ord("\n")}
        or progress.count(b".") != M2_SEQUENCER_STRIP_NAMING_PROGRESS_DOTS
        or progress.count(b"\n") not in M2_SEQUENCER_STRIP_NAMING_PROGRESS_NEWLINES
    ):
        fail("m2: sequencer_strip_naming progress cardinality differs")
    return (
        M2_SEQUENCER_STRIP_NAMING_PROGRESS_CANONICAL
        + M2_SEQUENCER_STRIP_NAMING_RESULT_TAIL
    )


def m2_canonicalize_animation_armature_progress(payload: bytes) -> bytes:
    """Independently bind and replay the exact armature output layouts."""
    layouts = (
        M2_ANIMATION_ARMATURE_CANONICAL,
        M2_ANIMATION_ARMATURE_HOMEFILE + b"." + M2_ANIMATION_ARMATURE_READ + b".....\n"
        + M2_ANIMATION_ARMATURE_RESULT_TAIL,
    )
    if payload not in layouts:
        fail("m2: bl_animation_armature output/progress grammar differs")
    return M2_ANIMATION_ARMATURE_CANONICAL


def m2_canonicalize_sculpt_brush_curve_presets_progress(payload: bytes) -> bytes:
    """Independently replay bounded nine-test progress fragmentation."""
    if not payload.endswith(M2_SCULPT_BRUSH_CURVE_PRESETS_RESULT_TAIL):
        fail("m2: bl_sculpt_brush_curve_presets progress/result grammar differs")
    progress = payload[:-len(M2_SCULPT_BRUSH_CURVE_PRESETS_RESULT_TAIL)]
    if (
        set(progress) - {ord("."), ord("\n")}
        or progress.count(b".") != M2_SCULPT_BRUSH_CURVE_PRESETS_PROGRESS_DOTS
        or progress.count(b"\n") not in M2_SCULPT_BRUSH_CURVE_PRESETS_PROGRESS_NEWLINES
    ):
        fail("m2: bl_sculpt_brush_curve_presets progress cardinality differs")
    return (
        M2_SCULPT_BRUSH_CURVE_PRESETS_PROGRESS_CANONICAL
        + M2_SCULPT_BRUSH_CURVE_PRESETS_RESULT_TAIL
    )


def m2_canonicalize_operator_function_py_api_progress(payload: bytes) -> bytes:
    """Independently replay bounded 33-test progress fragmentation."""
    if not payload.endswith(M2_OPERATOR_FUNCTION_PY_API_RESULT_TAIL):
        fail("m2: operator_function_py_api progress/result grammar differs")
    progress = payload[:-len(M2_OPERATOR_FUNCTION_PY_API_RESULT_TAIL)]
    if (
        set(progress) - {ord("."), ord("\n")}
        or progress.count(b".") != M2_OPERATOR_FUNCTION_PY_API_PROGRESS_DOTS
        or progress.count(b"\n") not in M2_OPERATOR_FUNCTION_PY_API_PROGRESS_NEWLINES
    ):
        fail("m2: operator_function_py_api progress cardinality differs")
    return (
        M2_OPERATOR_FUNCTION_PY_API_PROGRESS_CANONICAL
        + M2_OPERATOR_FUNCTION_PY_API_RESULT_TAIL
    )


def m2_canonicalize_geometry_attributes_progress(payload: bytes) -> bytes:
    """Independently replay bounded 16-test progress fragmentation."""
    if not payload.endswith(M2_GEOMETRY_ATTRIBUTES_RESULT_TAIL):
        fail("m2: geometry_attributes progress/result grammar differs")
    progress = payload[:-len(M2_GEOMETRY_ATTRIBUTES_RESULT_TAIL)]
    if (
        set(progress) - {ord("."), ord("\n")}
        or progress.count(b".") != M2_GEOMETRY_ATTRIBUTES_PROGRESS_DOTS
        or progress.count(b"\n") not in M2_GEOMETRY_ATTRIBUTES_PROGRESS_NEWLINES
    ):
        fail("m2: geometry_attributes progress cardinality differs")
    return (
        M2_GEOMETRY_ATTRIBUTES_PROGRESS_CANONICAL
        + M2_GEOMETRY_ATTRIBUTES_RESULT_TAIL
    )


def m2_canonicalize_rna_accessors_progress(payload: bytes) -> bytes:
    """Independently restore one dot around the exact colorspace warning."""
    lines = payload.splitlines(keepends=True)
    layouts = (
        [b"." + M2_RNA_ACCESSORS_COLORSPACE_WARNING, b"\n",
         M2_RNA_ACCESSORS_RESULT_SEPARATOR],
        [M2_RNA_ACCESSORS_COLORSPACE_WARNING, b".\n",
         M2_RNA_ACCESSORS_RESULT_SEPARATOR],
        [M2_RNA_ACCESSORS_COLORSPACE_WARNING, b".\n", b"\n",
         M2_RNA_ACCESSORS_RESULT_SEPARATOR],
    )
    matches: list[tuple[int, int]] = []
    for layout in layouts:
        matches.extend(
            (index, len(layout))
            for index in range(len(lines) - len(layout) + 1)
            if lines[index:index + len(layout)] == layout
        )
    if not matches:
        return payload
    if len(matches) != 1:
        fail("m2: bl_rna_accessors has ambiguous progress/warning layouts")
    index, length = matches[0]
    lines[index:index + length] = [
        M2_RNA_ACCESSORS_PROGRESS_CANONICAL, M2_RNA_ACCESSORS_RESULT_SEPARATOR,
    ]
    return b"".join(lines)


def m2_canonicalize_node_group_compat_progress(payload: bytes) -> bytes:
    """Independently restore the compositor-read/doversion dot."""
    lines = payload.splitlines(keepends=True)
    nodegroup36_bare = M2_NODE_GROUP_COMPAT_NODEGROUP36_READ[1:]
    nodegroup36_layouts = (
        [M2_NODE_GROUP_COMPAT_NODEGROUP36_READ,
         M2_NODE_GROUP_COMPAT_OUTPUT_WARNING,
         nodegroup36_bare, b"." + M2_NODE_GROUP_COMPAT_OUTPUT_WARNING,
         M2_NODE_GROUP_COMPAT_NODEGROUP36_READ,
         M2_NODE_GROUP_COMPAT_OUTPUT_WARNING],
        M2_NODE_GROUP_COMPAT_NODEGROUP36_CANONICAL.splitlines(keepends=True),
    )
    nodegroup36_matches: list[tuple[int, int]] = []
    for layout in nodegroup36_layouts:
        nodegroup36_matches.extend(
            (index, len(layout))
            for index in range(len(lines) - len(layout) + 1)
            if lines[index:index + len(layout)] == layout
        )
    if len(nodegroup36_matches) != 1:
        fail("m2: bl_node_group_compat lacks exact nodegroup36 progress layout")
    index, length = nodegroup36_matches[0]
    lines[index:index + length] = [M2_NODE_GROUP_COMPAT_NODEGROUP36_CANONICAL]
    layouts = (
        [M2_NODE_GROUP_COMPAT_COMPOSITOR_READ,
         b"." + M2_NODE_GROUP_COMPAT_DOVERSION_WARNING],
        [b"." + M2_NODE_GROUP_COMPAT_COMPOSITOR_READ,
         M2_NODE_GROUP_COMPAT_DOVERSION_WARNING],
    )
    matches: list[tuple[int, int]] = []
    for layout in layouts:
        matches.extend(
            (index, len(layout))
            for index in range(len(lines) - len(layout) + 1)
            if lines[index:index + len(layout)] == layout
        )
    if len(matches) != 1:
        fail("m2: bl_node_group_compat lacks one exact progress/read layout")
    index, length = matches[0]
    lines[index:index + length] = [M2_NODE_GROUP_COMPAT_PROGRESS_CANONICAL]
    return b"".join(lines)


def m2_canonicalize_node_tools_progress(payload: bytes) -> bytes:
    """Independently replay bounded four-test progress fragmentation."""
    if not payload.endswith(M2_NODE_TOOLS_RESULT_TAIL):
        fail("m2: node_tools progress/result grammar differs")
    progress = payload[:-len(M2_NODE_TOOLS_RESULT_TAIL)]
    if (
        set(progress) - {ord("."), ord("\n")}
        or progress.count(b".") != M2_NODE_TOOLS_PROGRESS_DOTS
        or progress.count(b"\n") not in M2_NODE_TOOLS_PROGRESS_NEWLINES
    ):
        fail("m2: node_tools progress cardinality differs")
    return M2_NODE_TOOLS_PROGRESS_CANONICAL + M2_NODE_TOOLS_RESULT_TAIL


def m2_canonicalize_animation_keyframing_progress(payload: bytes) -> bytes:
    """Independently restore the exact keyframing diagnostic-phase dot."""
    lines = payload.splitlines(keepends=True)
    layouts = (
        [b"." + M2_ANIMATION_KEYFRAMING_FIRST_WARNING,
         *M2_ANIMATION_KEYFRAMING_PROGRESS_MIDDLE,
         M2_ANIMATION_KEYFRAMING_FCURVE_CREATE_WARNING,
         b"." + M2_ANIMATION_KEYFRAMING_KEYING_SET_ERROR],
        [M2_ANIMATION_KEYFRAMING_FIRST_WARNING,
         *M2_ANIMATION_KEYFRAMING_PROGRESS_MIDDLE,
         b"." + M2_ANIMATION_KEYFRAMING_FCURVE_CREATE_WARNING,
         b"." + M2_ANIMATION_KEYFRAMING_KEYING_SET_ERROR],
        [M2_ANIMATION_KEYFRAMING_FIRST_WARNING,
         *M2_ANIMATION_KEYFRAMING_PROGRESS_MIDDLE,
         b".." + M2_ANIMATION_KEYFRAMING_FCURVE_CREATE_WARNING,
         M2_ANIMATION_KEYFRAMING_KEYING_SET_ERROR],
    )
    matches: list[tuple[int, int]] = []
    for layout in layouts:
        matches.extend(
            (index, len(layout))
            for index in range(len(lines) - len(layout) + 1)
            if lines[index:index + len(layout)] == layout
        )
    if len(matches) != 1:
        fail("m2: bl_animation_keyframing lacks one exact diagnostic layout")
    index, length = matches[0]
    lines[index:index + length] = [M2_ANIMATION_KEYFRAMING_PROGRESS_CANONICAL]
    return b"".join(lines)


def m2_canonicalize_vertex_group_painting_output(payload: bytes) -> bytes:
    """Independently bind the complete vertex-group output layouts."""
    native_layout = (
        M2_VERTEX_GROUP_PAINTING_READ + b"." + M2_VERTEX_GROUP_PAINTING_READ
        + b".\n" + M2_VERTEX_GROUP_PAINTING_RESULT_TAIL
        + M2_VERTEX_GROUP_PAINTING_ERROR
    )
    if payload not in (native_layout, M2_VERTEX_GROUP_PAINTING_CANONICAL):
        fail("m2: vertex_group_painting output/error-order grammar differs")
    return M2_VERTEX_GROUP_PAINTING_CANONICAL


def m2_canonicalize_animation_fcurves_output(payload: bytes) -> bytes:
    """Independently bind the Euler and exact 300-warning phases."""
    lines = payload.splitlines(keepends=True)
    euler_records = [
        M2_ANIMATION_FCURVES_EULER_READ,
        M2_ANIMATION_FCURVES_EULER_MISSING,
        M2_ANIMATION_FCURVES_EULER_FILTERED,
        M2_ANIMATION_FCURVES_EULER_READ,
        M2_ANIMATION_FCURVES_EULER_MISSING,
        M2_ANIMATION_FCURVES_EULER_FILTERED,
    ]
    euler_matches: list[tuple[int, int]] = []
    for index in range(len(lines) - len(euler_records) + 1):
        block = lines[index:index + len(euler_records)]
        if (
            sum(
                line == b"." + record
                for line, record in zip(block, euler_records)
            ) == 1
            and all(line in (record, b"." + record)
                    for line, record in zip(block, euler_records))
        ):
            euler_matches.append((index, len(euler_records)))
    if len(euler_matches) != 1:
        fail("m2: bl_animation_fcurves lacks one exact Euler progress layout")
    index, length = euler_matches[0]
    lines[index:index + length] = [M2_ANIMATION_FCURVES_EULER_CANONICAL]
    warning_layouts = (
        m2_animation_fcurves_warning_block(M2_ANIMATION_FCURVES_NATIVE_DOT_OFFSETS),
        m2_animation_fcurves_warning_block(M2_ANIMATION_FCURVES_WASM_DOT_OFFSETS),
    )
    warning_matches: list[tuple[int, int]] = []
    for layout in warning_layouts:
        warning_matches.extend(
            (index, len(layout))
            for index in range(len(lines) - len(layout) + 1)
            if lines[index:index + len(layout)] == layout
        )
    if len(warning_matches) != 1:
        fail("m2: bl_animation_fcurves lacks exact 300-warning progress layout")
    index, length = warning_matches[0]
    lines[index:index + length] = [M2_ANIMATION_FCURVES_WARNING_CANONICAL]
    return b"".join(lines)


def m2_canonicalize_mesh_validate_progress(payload: bytes) -> bytes:
    """Independently restore progress and final diagnostic ordering."""
    lines = payload.splitlines(keepends=True)
    layouts = (
        [*M2_MESH_VALIDATE_PROGRESS_ERRORS[:-1],
         b"....." + M2_MESH_VALIDATE_PROGRESS_ERRORS[-1]],
        [b"." + line for line in M2_MESH_VALIDATE_PROGRESS_ERRORS],
    )
    matches: list[tuple[int, int]] = []
    for layout in layouts:
        matches.extend(
            (index, len(layout))
            for index in range(len(lines) - len(layout) + 1)
            if lines[index:index + len(layout)] == layout
        )
    if len(matches) != 1:
        fail("m2: mesh_validate lacks one exact five-error progress layout")
    index, length = matches[0]
    lines[index:index + length] = [M2_MESH_VALIDATE_PROGRESS_CANONICAL]
    payload = b"".join(lines)
    end_layouts = (
        M2_MESH_VALIDATE_MDISP_READ + M2_MESH_VALIDATE_RESULT_TAIL
        + M2_MESH_VALIDATE_MDISP_ERROR,
        M2_MESH_VALIDATE_END_CANONICAL,
    )
    end_matches = [layout for layout in end_layouts if payload.count(layout) == 1]
    if len(end_matches) != 1:
        fail("m2: mesh_validate lacks one exact final diagnostic/result layout")
    return payload.replace(
        end_matches[0], M2_MESH_VALIDATE_END_CANONICAL, 1
    )


def m2_canonicalize_sculpt_face_set_output(payload: bytes) -> bytes:
    """Independently bind the complete sculpt face-set output layouts."""
    native_layout = (
        M2_SCULPT_FACE_SET_READ + M2_SCULPT_FACE_SET_READ
        + b".." + M2_SCULPT_FACE_SET_READ + b".\n"
        + M2_SCULPT_FACE_SET_RESULT_TAIL
    )
    if payload not in (native_layout, M2_SCULPT_FACE_SET_CANONICAL):
        fail("m2: bl_sculpt_face_set output/progress grammar differs")
    return M2_SCULPT_FACE_SET_CANONICAL


def m2_canonicalize_suite_records(payload: bytes, suite: str | None) -> bytes:
    if suite == M2_TEMPDIR_SUITE:
        return m2_canonicalize_tempdir_progress(payload)
    if suite == M2_PROP_ARRAY_SUITE:
        return m2_canonicalize_prop_array_progress(payload)
    if suite == M2_TEXT_SUITE:
        return m2_canonicalize_text_progress(payload)
    if suite == M2_SEQUENCER_STRIP_NAMING_SUITE:
        return m2_canonicalize_sequencer_strip_naming_progress(payload)
    if suite == M2_ANIMATION_ARMATURE_SUITE:
        return m2_canonicalize_animation_armature_progress(payload)
    if suite == M2_SCULPT_BRUSH_CURVE_PRESETS_SUITE:
        return m2_canonicalize_sculpt_brush_curve_presets_progress(payload)
    if suite == M2_OPERATOR_FUNCTION_PY_API_SUITE:
        return m2_canonicalize_operator_function_py_api_progress(payload)
    if suite == M2_GEOMETRY_ATTRIBUTES_SUITE:
        return m2_canonicalize_geometry_attributes_progress(payload)
    if suite == M2_NO_DENOISER_SUITE:
        return m2_canonicalize_rna_accessors_progress(payload)
    if suite == M2_NODE_GROUP_COMPAT_SUITE:
        return m2_canonicalize_node_group_compat_progress(payload)
    if suite == M2_NODE_TOOLS_SUITE:
        return m2_canonicalize_node_tools_progress(payload)
    if suite == M2_ANIMATION_KEYFRAMING_SUITE:
        return m2_canonicalize_animation_keyframing_progress(payload)
    if suite == M2_VERTEX_GROUP_PAINTING_SUITE:
        return m2_canonicalize_vertex_group_painting_output(payload)
    if suite == M2_ANIMATION_FCURVES_SUITE:
        return m2_canonicalize_animation_fcurves_output(payload)
    if suite == M2_MESH_VALIDATE_SUITE:
        return m2_canonicalize_mesh_validate_progress(payload)
    if suite == M2_SCULPT_FACE_SET_SUITE:
        return m2_canonicalize_sculpt_face_set_output(payload)
    if suite == M2_KEYMAP_ORDER_SUITE:
        return m2_canonicalize_keymap_inventory(payload)
    if suite in M2_PHYSICS_ORDER:
        return m2_canonicalize_physics_records(payload, suite)
    if suite == "blendfile_library_overrides":
        return m2_canonicalize_library_override_sets(payload)
    return payload


def m2_canonicalize_suite_scratch_root(
    payload: bytes, *, suite: str | None, scratch_root: Path | None, root: Path
) -> bytes:
    """Independently replay the exact runner-owned scratch-root policy."""
    expected_occurrences = M2_SCRATCH_ROOT_POLICIES.get(suite)
    if expected_occurrences is None:
        return payload
    if scratch_root is None or not scratch_root.is_absolute():
        fail(f"m2: {suite} lacks its exact absolute scratch root")
    if M2_SCRATCH_ROOT_TOKEN in payload:
        fail(
            f"m2: {suite} raw log contains the reserved scratch token"
        )
    candidates = [os.fsencode(os.fspath(scratch_root))]
    try:
        relative = scratch_root.relative_to(root)
    except ValueError:
        pass
    else:
        candidates.append(
            M2_CONTAINER_REPOSITORY_ROOT + b"/" + os.fsencode(os.fspath(relative))
        )
    patterns = [re.compile(re.escape(value) + rb"(?=/)") for value in candidates]
    counts = [len(pattern.findall(payload)) for pattern in patterns]
    if sum(counts) != expected_occurrences or sum(count > 0 for count in counts) != 1:
        fail(
            f"m2: {suite} scratch root occurrence count differs: "
            f"expected={expected_occurrences}"
        )
    for pattern in patterns:
        payload = pattern.sub(M2_SCRATCH_ROOT_TOKEN, payload)
    return payload


def m2_canonicalize_repository_roots(payload: bytes, *, root: Path) -> bytes:
    """Independently replay exact host/container repository-root mapping."""
    if M2_REPOSITORY_ROOT_TOKEN in payload:
        fail("m2: raw log contains the reserved repository-root token")
    candidates = tuple(dict.fromkeys((os.fsencode(root), M2_CONTAINER_REPOSITORY_ROOT)))
    patterns = [re.compile(re.escape(value) + rb"(?=/)") for value in candidates]
    counts = [len(pattern.findall(payload)) for pattern in patterns]
    if sum(count > 0 for count in counts) > 1:
        fail("m2: raw log mixes host and container repository roots")
    for pattern in patterns:
        payload = pattern.sub(M2_REPOSITORY_ROOT_TOKEN, payload)
    return payload


def m2_normalized_bytes(
    payload: bytes, *, wasm: bool, root: Path, suite: str | None = None,
    scratch_root: Path | None = None,
) -> bytes:
    payload = m2_canonicalize_suite_scratch_root(
        payload, suite=suite, scratch_root=scratch_root, root=root
    )
    payload = m2_canonicalize_repository_roots(payload, root=root)
    payload = m2_strip_platform_envelope(payload, wasm=wasm)
    shared = root / "sandbox/tierb-prep/normalize.sed"
    denoise = root / "sandbox/tierb-prep/wasm-denoise.pl"
    key = (
        wasm,
        suite,
        os.fsencode(os.fspath(scratch_root)) if scratch_root is not None else b"",
        hashlib.sha256(payload).digest(),
        hashlib.sha256(shared.read_bytes()).digest(),
        hashlib.sha256(denoise.read_bytes()).digest() if wasm else b"",
    )
    cached = M2_NORMALIZATION_CACHE.get(key)
    if cached is not None:
        return cached
    commands = [["sed", "-f", os.fspath(shared)]]
    if wasm:
        commands.append(["perl", os.fspath(denoise)])
    for argv in commands:
        result = subprocess.run(
            argv, input=payload, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            fail(
                f"m2: normalizer replay failed rc={result.returncode}: "
                f"{argv}: {result.stderr[-500:]!r}"
            )
        payload = result.stdout
    if wasm and suite == M2_NO_DENOISER_SUITE:
        lines = payload.splitlines(keepends=True)
        indexes = [
            index for index, line in enumerate(lines)
            if line == M2_NO_DENOISER_NORMALIZED_LINE
        ]
        if len(indexes) != 1:
            fail(
                "m2: bl_rna_accessors must carry exactly one "
                "compiled-out-denoiser warning"
            )
        lines.pop(indexes[0])
        payload = b"".join(lines)
    elif not wasm and suite == M2_NO_DENOISER_SUITE:
        lines = payload.splitlines(keepends=True)
        indexes = [
            index for index, line in enumerate(lines)
            if line == M2_NATIVE_CUEW_NORMALIZED_LINE
        ]
        if len(indexes) > 1:
            fail("m2: bl_rna_accessors carries duplicate native CUEW warnings")
        if indexes:
            lines.pop(indexes[0])
            payload = b"".join(lines)
    payload = m2_canonicalize_suite_records(payload, suite)
    M2_NORMALIZATION_CACHE[key] = payload
    return payload


def m2_rna_menu_lines(names: tuple[str, ...]) -> list[bytes]:
    return [
        b'<bpy_struct, FileBrowserFSMenuEntry("' + name.encode() + b'")'
        + M2_RNA_MENU_CONTEXT
        for name in names
    ]


def m2_replace_exact_block(
    payload: bytes, block: list[bytes], marker: bytes, where: str
) -> bytes:
    lines = payload.splitlines(keepends=True)
    indexes = [
        index for index in range(len(lines) - len(block) + 1)
        if lines[index:index + len(block)] == block
    ]
    if len(indexes) != 1:
        fail(f"m2: {where} lacks one exact contiguous platform delta block")
    index = indexes[0]
    return b"".join(lines[:index] + [marker] + lines[index + len(block):])


def m2_replace_exact_alternative_block(
    payload: bytes, blocks: tuple[list[bytes], ...], marker: bytes, where: str
) -> bytes:
    lines = payload.splitlines(keepends=True)
    matches: list[tuple[int, int]] = []
    for block in blocks:
        matches.extend(
            (index, len(block))
            for index in range(len(lines) - len(block) + 1)
            if lines[index:index + len(block)] == block
        )
    if len(matches) != 1:
        fail(f"m2: {where} lacks one exact native platform delta block")
    index, length = matches[0]
    return b"".join(lines[:index] + [marker] + lines[index + length:])


def m2_canonicalize_animation_native_progress(payload: bytes) -> bytes:
    lines = payload.splitlines(keepends=True)
    classic = [b"." * 23 + M2_ANIMATION_REMAP_READ]
    linux_variants = (
        [
            b"." + M2_ANIMATION_SLOT_UNASSIGNED_ERROR,
            b".." + M2_ANIMATION_SLOT_XX_WARNING,
            M2_ANIMATION_REPORT_CONTINUATION,
            M2_ANIMATION_SLOT_OB_WARNING,
            M2_ANIMATION_REPORT_CONTINUATION,
            b"." * 22 + M2_ANIMATION_REMAP_READ,
        ],
        [
            b".." + M2_ANIMATION_SLOT_UNASSIGNED_ERROR,
            M2_ANIMATION_SLOT_XX_WARNING,
            M2_ANIMATION_REPORT_CONTINUATION,
            M2_ANIMATION_SLOT_OB_WARNING,
            M2_ANIMATION_REPORT_CONTINUATION,
            b"." * 23 + M2_ANIMATION_REMAP_READ,
        ],
        [
            b".." + M2_ANIMATION_SLOT_UNASSIGNED_ERROR,
            b"." + M2_ANIMATION_SLOT_XX_WARNING,
            M2_ANIMATION_REPORT_CONTINUATION,
            M2_ANIMATION_SLOT_OB_WARNING,
            M2_ANIMATION_REPORT_CONTINUATION,
            b"." * 22 + M2_ANIMATION_REMAP_READ,
        ],
    )
    variant_matches: list[tuple[int, int]] = []
    for block in linux_variants:
        variant_matches.extend(
            (index, len(block))
            for index in range(len(lines) - len(block) + 1)
            if lines[index:index + len(block)] == block
        )
    if len(variant_matches) > 1:
        fail("m2: bl_animation_action has ambiguous native progress layouts")
    if variant_matches:
        index, length = variant_matches[0]
        lines[index:index + length] = [
            b"." + M2_ANIMATION_SLOT_UNASSIGNED_ERROR,
            b"." + M2_ANIMATION_SLOT_XX_WARNING,
            M2_ANIMATION_REPORT_CONTINUATION,
            M2_ANIMATION_SLOT_OB_WARNING,
            M2_ANIMATION_REPORT_CONTINUATION,
            classic[0],
        ]
    classic_matches = [
        index
        for index in range(len(lines) - len(classic) + 1)
        if lines[index:index + len(classic)] == classic
    ]
    if len(classic_matches) != 1:
        fail("m2: bl_animation_action lacks one exact native progress layout")
    return b"".join(lines)


def m2_animation_delta_projection(payload: bytes, *, wasm: bool) -> bytes:
    if not wasm:
        payload = m2_canonicalize_animation_native_progress(payload)
    lines = payload.splitlines(keepends=True)
    group_prefix = b"ERROR: one of the ID's for the groups to assign to is invalid "
    wasm_group_error = group_prefix + b"(ptr=0xADDR, val=0)\n"
    native_group_errors = (
        group_prefix + b"(ptr=0xADDR, val=0x0)\n",
        group_prefix + b"(ptr=0xADDR, val=(nil))\n",
    )
    native_progress = [b"." * 23 + M2_ANIMATION_REMAP_READ]
    wasm_progress = [
        b"." * 4 + M2_ANIMATION_ASSIGNMENT_WARNING,
        b"." * 6 + wasm_group_error,
        M2_ANIMATION_FCURVE_ERROR,
        b"." * 13 + M2_ANIMATION_REMAP_READ,
    ]
    progress = wasm_progress if wasm else native_progress
    projected = m2_replace_exact_block(
        b"".join(lines), progress, b"<ANIMATION_PROGRESS_AND_DIAGNOSTICS>\n",
        "bl_animation_action progress",
    )
    lines = projected.splitlines(keepends=True)
    phase_anchor = [
        b"<ANIMATION_PROGRESS_AND_DIAGNOSTICS>\n",
        M2_ANIMATION_SECOND_REMAP_READ, M2_ANIMATION_SAVED,
        M2_ANIMATION_TEMP_READ,
    ]
    phase_indexes = [
        index for index in range(len(lines) - len(phase_anchor) + 1)
        if lines[index:index + len(phase_anchor)] == phase_anchor
    ]
    if phase_indexes != [lines.index(phase_anchor[0])]:
        fail("m2: bl_animation_action library phase moved relative to progress/remap")
    if wasm:
        indexes = [index for index, line in enumerate(lines) if line == M2_ANIMATION_TEMP_READ]
        if len(indexes) != 1 or indexes[0] + 4 >= len(lines):
            fail("m2: bl_animation_action lacks its exact temp-read delta context")
        index = indexes[0]
        if (lines[index + 1] != M2_ANIMATION_OBJECTDATA_WARNING
                or lines[index + 2] != M2_ANIMATION_INFO_LIBRARY
                or lines[index + 3] != M2_ANIMATION_MISSING_DATA
                or lines[index + 4] != M2_ANIMATION_LAYERED_READ):
            fail("m2: bl_animation_action Wasm ObjectData delta sequence differs")
        lines[index:index + 5] = [
            M2_ANIMATION_TEMP_READ, b"<ANIMATION_LIBRARY_READ>\n",
            M2_ANIMATION_LAYERED_READ,
        ]
        if not lines or lines[-1] != b"OK\n":
            fail("m2: bl_animation_action Wasm diagnostics moved outside the test sequence")
    else:
        matching_group_errors = [
            line for line in native_group_errors if len(lines) >= 2 and lines[-2] == line
        ]
        if len(matching_group_errors) != 1:
            fail("m2: bl_animation_action native group-error null format differs")
        post_ok = [
            b"OK\n", M2_ANIMATION_ASSIGNMENT_WARNING, matching_group_errors[0],
            M2_ANIMATION_FCURVE_ERROR,
        ]
        if lines[-4:] != post_ok:
            fail("m2: bl_animation_action native post-OK diagnostics moved")
        lines[-4:] = [b"OK\n"]
        indexes = [index for index, line in enumerate(lines) if line == M2_ANIMATION_TEMP_READ]
        if len(indexes) != 1 or indexes[0] + 2 >= len(lines):
            fail("m2: bl_animation_action native library-read context differs")
        index = indexes[0]
        library_layout = lines[index:index + 3]
        if library_layout not in (
            [M2_ANIMATION_TEMP_READ, M2_ANIMATION_INFO_LIBRARY,
             M2_ANIMATION_LAYERED_READ],
            [M2_ANIMATION_TEMP_READ, b"." + M2_ANIMATION_INFO_LIBRARY,
             M2_ANIMATION_LAYERED_READ_BARE],
        ):
            fail("m2: bl_animation_action native library-read sequence differs")
        lines[index:index + 3] = [
            M2_ANIMATION_TEMP_READ, b"<ANIMATION_LIBRARY_READ>\n",
            M2_ANIMATION_LAYERED_READ,
        ]
    return b"".join(lines)


def m2_library_override_delta_projection(payload: bytes, *, wasm: bool) -> bytes:
    del wasm
    lines = payload.splitlines(keepends=True)
    index = M2_LIBRARY_OVERRIDE_PHASE_BEFORE_INDEX
    anchor_pair = (
        (lines[index], lines[index + 10]) if len(lines) > index + 10 else None
    )
    if anchor_pair not in (
        (M2_LIBRARY_OVERRIDE_PHASE_BEFORE, M2_LIBRARY_OVERRIDE_PHASE_AFTER),
        (M2_LIBRARY_OVERRIDE_SCRATCH_PHASE_BEFORE,
         M2_LIBRARY_OVERRIDE_SCRATCH_PHASE_AFTER),
    ):
        fail("m2: blendfile_library_overrides hierarchy phase moved")
    phase = lines[index + 1:index + 10]
    controllers = (
        M2_LIBRARY_OVERRIDE_CONTROLLER,
        M2_LIBRARY_OVERRIDE_CONTROLLER_001,
        M2_LIBRARY_OVERRIDE_CONTROLLER_002,
    )
    collections = (b"LibCube", b"LibCube.001", b"LibCube.002")
    found_pairs: set[tuple[bytes, bytes]] = set()
    for number, (controller, collection) in enumerate(zip(controllers, collections)):
        offset = number * 3
        if phase[offset] != controller:
            fail("m2: blendfile_library_overrides controller row/order differs")
        records = []
        for line in phase[offset + 1:offset + 3]:
            match = M2_LIBRARY_OVERRIDE_RECORD_RE.fullmatch(line)
            if match is None or match.group("collection") != collection:
                fail("m2: blendfile_library_overrides collection association differs")
            records.append((match.group("reference"), match.group("local")))
        if [reference for reference, _ in records] != [b"LibCube.002", b"LibCube.001"]:
            fail("m2: blendfile_library_overrides reference row/order differs")
        pair = (records[0][1], records[1][1])
        if pair not in M2_LIBRARY_OVERRIDE_LOCAL_PAIRS:
            fail("m2: blendfile_library_overrides local suffix pair differs")
        found_pairs.add(pair)
    if found_pairs != M2_LIBRARY_OVERRIDE_LOCAL_PAIRS:
        fail("m2: blendfile_library_overrides local suffix pairs are not a bijection")
    lines[index + 1:index + 10] = [
        b"<LIBRARY_OVERRIDE_IDNAME_HIERARCHY_PHASE>\n"
    ]
    return b"".join(lines)


def m2_validate_pass_delta(suite: str, native_output: bytes, wasm_output: bytes) -> None:
    if suite == "bl_rna_paths":
        marker = b"<OS_FILE_BROWSER_MENU>\n"
        native_projection = m2_replace_exact_alternative_block(
            native_output,
            tuple(m2_rna_menu_lines(names) for names in M2_RNA_NATIVE_MENUS),
            marker,
            suite,
        )
        wasm_projection = m2_replace_exact_block(
            wasm_output, m2_rna_menu_lines(M2_RNA_WASM_MENU), marker, suite
        )
    elif suite == "bl_animation_action":
        native_projection = m2_animation_delta_projection(native_output, wasm=False)
        wasm_projection = m2_animation_delta_projection(wasm_output, wasm=True)
    elif suite == "blendfile_library_overrides":
        native_projection = m2_library_override_delta_projection(native_output, wasm=False)
        wasm_projection = m2_library_override_delta_projection(wasm_output, wasm=True)
    else:
        fail(f"m2: unimplemented pass-with-delta suite: {suite}")
    if native_projection != wasm_projection:
        fail(f"m2: {suite} differs outside its exact pass-with-delta schema")


def m2_verify_staged_inventory(
    ctx: Context, rows: Any, *, source_root: str, staged_root: str, where: str
) -> tuple[set[str], str]:
    root = ctx.root / source_root
    if not root.is_dir() or root.is_symlink():
        fail(f"m2: {where} source root is missing or symlinked")
    if any(path.is_symlink() for path in root.rglob("*")):
        fail(f"m2: {where} source inventory contains a symlink")
    expected = {
        path.relative_to(ctx.root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.relative_to(root).parts
        and path.suffix != ".pyc"
    }
    if not expected or not isinstance(rows, list) or len(rows) != len(expected):
        fail(f"m2: {where} staged inventory cardinality differs")
    found: set[str] = set()
    staged_paths: set[str] = set()
    prefixes: set[str] = set()
    for number, asset in enumerate(rows):
        row = exact(asset, {"source", "staged"}, f"m2.runtime.{where}[{number}]")
        source_ref = row["source"]
        staged_ref = row["staged"]
        if (not isinstance(source_ref, dict) or not isinstance(source_ref.get("path"), str)
                or not isinstance(staged_ref, dict) or not isinstance(staged_ref.get("path"), str)):
            fail(f"m2: {where} reference is malformed")
        source_path = source_ref["path"]
        if source_path in found or source_path not in expected:
            fail(f"m2: {where} inventory has an unknown/duplicate source")
        relative = Path(source_path).relative_to(source_root).as_posix()
        staged_path = staged_ref["path"]
        expected_suffix = f"/{staged_root}/{relative}"
        if not staged_path.endswith(expected_suffix):
            fail(f"m2: {where} staged lexical path differs")
        prefixes.add(staged_path[:-len(expected_suffix)])
        source = ctx.file_ref(source_ref, f"m2.runtime.{where}[{number}].source", source_path)
        staged = ctx.file_ref(staged_ref, f"m2.runtime.{where}[{number}].staged", staged_path)
        if staged.is_symlink() or not staged.as_posix().endswith(expected_suffix):
            fail(f"m2: {where} staged path resolves through a symlink")
        if staged.read_bytes() != source.read_bytes():
            fail(f"m2: {where} staged bytes differ")
        found.add(source_path)
        staged_paths.add(staged_path)
    if found != expected:
        fail(f"m2: {where} staged inventory is incomplete")
    if len(prefixes) != 1:
        fail(f"m2: {where} staged files do not share one composed root")
    return staged_paths, prefixes.pop()


def m2_require_exact_staged_tree(
    ctx: Context, *, prefix: str, tree_root: str, expected_files: set[str], where: str
) -> None:
    relative_root = f"{prefix}/{tree_root}" if prefix else tree_root
    pure = PurePosixPath(relative_root)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        fail(f"m2: {where} composed root is unsafe")
    path = ctx.root.joinpath(*pure.parts)
    lexical = ctx.root
    for part in pure.parts:
        lexical /= part
        if lexical.is_symlink():
            fail(f"m2: {where} composed root contains a symlink")
    if not path.is_dir() or path.is_symlink():
        fail(f"m2: {where} composed root is missing or symlinked")
    actual: set[str] = set()
    for item in path.rglob("*"):
        if item.is_symlink():
            fail(f"m2: {where} composed tree contains a symlink")
        if item.is_file():
            actual.add(item.relative_to(ctx.root).as_posix())
    if actual != expected_files:
        fail(f"m2: {where} composed destination inventory differs")


def verify_m2(ctx: Context, receipt: dict[str, Any]) -> None:
    ctx.common(receipt, "m2", {"runtime", "suite_manifest", "normalization_policy", "deferral_registry", "total", "rows"})
    runtime = exact(receipt["runtime"], {
        "native_oracle", "node", "javascript", "wasm", "cmake_cache", "node_version",
        "python_stdlib_manifest", "python_version", "import_bpy", "cycles_engine",
        "language_count", "python_probe_result", "python_probe_stdout",
        "python_probe_stderr", "openimagedenoise", "runtime_assets", "factory_startup",
    }, "m2.runtime")
    canonical_runtime_ref(
        ctx, runtime["native_oracle"], "oracle/bpy.sh", "m2.runtime.native_oracle"
    )
    node = canonical_runtime_ref(
        ctx, runtime["node"], "tools/emsdk/node/22.16.0_64bit/bin/node", "m2.runtime.node"
    )
    canonical_runtime_ref(
        ctx, runtime["javascript"], "build-wasm-m1-parity/bin/blender.js",
        "m2.runtime.javascript",
    )
    canonical_runtime_ref(
        ctx, runtime["wasm"], "build-wasm-m1-parity/bin/blender.wasm", "m2.runtime.wasm"
    )
    cmake_cache = canonical_runtime_ref(
        ctx, runtime["cmake_cache"], "build-wasm-m1-parity/CMakeCache.txt",
        "m2.runtime.cmake_cache",
    )
    oidn_rows = [
        line for line in cmake_cache.read_text(encoding="utf-8").splitlines()
        if line.startswith("WITH_OPENIMAGEDENOISE:")
    ]
    if oidn_rows != ["WITH_OPENIMAGEDENOISE:BOOL=OFF"]:
        fail("m2: canonical runtime is not exactly WITH_OPENIMAGEDENOISE:BOOL=OFF")
    ctx.file_ref(runtime["python_stdlib_manifest"], "m2.runtime.python_stdlib_manifest")
    if (runtime["node_version"] != "v22.16.0"
            or subprocess.run(
                [os.fspath(node), "--version"], capture_output=True, text=True,
                timeout=30, check=True,
            ).stdout.strip() != runtime["node_version"]
            or runtime["python_version"] != "3.13.13"
            or runtime["import_bpy"] is not True
            or runtime["cycles_engine"] is not True
            or runtime["openimagedenoise"] is not False
            or runtime["factory_startup"] is not True):
        fail("m2: Python/bpy boot contract did not pass")
    assets, _, _ = ctx.load_ref(runtime["runtime_assets"], "m2.runtime.runtime_assets")
    exact(assets, {
        "schema", "system_resources", "system_scripts", "base_scripts", "cycles_addon",
        "datafiles", "assets", "locale_languages", "python_environment",
        "pass_delta_note",
    }, "m2.runtime.runtime_assets.value")
    if (assets["schema"] != 1 or assets["system_resources"] != "."
            or assets["system_scripts"] != "scripts"):
        fail("m2: composed runtime asset roots differ")
    if assets["python_environment"] != {
        "PYTHONHASHSEED": "0", "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }:
        fail("m2: deterministic Python environment differs")
    pass_delta_note = ctx.file_ref(
        assets["pass_delta_note"], "m2.runtime.runtime_assets.pass_delta_note",
        M2_PASS_DELTA_NOTE_PATH,
    )
    note_payload = pass_delta_note.read_bytes()
    if any(note_payload.count(snippet) != 1 for snippet in M2_PASS_DELTA_NOTE_REQUIRED):
        fail("m2: exact pass-with-delta evidence note contract differs")
    datafile_paths, datafile_prefix = m2_verify_staged_inventory(
        ctx, assets["datafiles"], source_root="upstream/release/datafiles",
        staged_root="datafiles", where="datafiles",
    )
    asset_paths, asset_prefix = m2_verify_staged_inventory(
        ctx, assets["assets"], source_root="upstream/assets",
        staged_root="datafiles/assets", where="assets",
    )
    if asset_prefix != datafile_prefix:
        fail("m2: datafiles/assets do not share one composed root")
    locale_row = exact(
        assets["locale_languages"], {"source", "staged"},
        "m2.runtime.runtime_assets.locale_languages",
    )
    locale_source = ctx.file_ref(
        locale_row["source"], "m2.runtime.runtime_assets.locale.source",
        "upstream/locale/languages",
    )
    locale_staged = ctx.file_ref(
        locale_row["staged"], "m2.runtime.runtime_assets.locale.staged"
    )
    if (locale_source.is_symlink() or locale_staged.is_symlink()
            or locale_staged.as_posix().endswith("/datafiles/locale/languages") is False
            or locale_staged.read_bytes() != locale_source.read_bytes()):
        fail("m2: staged locale languages index differs")
    locale_staged_path = locale_row["staged"].get("path")
    locale_suffix = "/datafiles/locale/languages"
    if (not isinstance(locale_staged_path, str)
            or not locale_staged_path.endswith(locale_suffix)
            or locale_staged_path[:-len(locale_suffix)] != datafile_prefix):
        fail("m2: staged locale languages lexical root differs")
    m2_require_exact_staged_tree(
        ctx, prefix=datafile_prefix, tree_root="datafiles",
        expected_files=datafile_paths | asset_paths | {locale_staged_path},
        where="datafiles/assets/locale",
    )
    language_count = 0
    for number, raw in enumerate(locale_source.read_text(encoding="utf-8").splitlines(), 1):
        if not raw or raw.startswith("#"):
            continue
        fields = raw.split(":")
        if (len(fields) != 4 or not fields[0].isdigit() or not fields[1]
                or not fields[2] or not fields[3].endswith("%")
                or not fields[3][:-1].isdigit()):
            fail(f"m2: malformed locale languages row {number}")
        language_count += 1
    if language_count < 2 or runtime["language_count"] != language_count:
        fail("m2: runtime language count does not match the staged source index")
    probe_result_path = ctx.file_ref(
        runtime["python_probe_result"], "m2.runtime.python_probe_result"
    )
    probe_stdout = ctx.file_ref(
        runtime["python_probe_stdout"], "m2.runtime.python_probe_stdout"
    )
    probe_stderr = ctx.file_ref(
        runtime["python_probe_stderr"], "m2.runtime.python_probe_stderr"
    )
    probe_result = strict_json(
        probe_result_path.read_text(encoding="utf-8"), "m2.runtime.python_probe_result"
    )
    if probe_result != {
        "version": runtime["python_version"],
        "import_bpy": runtime["import_bpy"],
        "cycles_engine": runtime["cycles_engine"],
        "language_count": runtime["language_count"],
    }:
        fail("m2: Python probe result does not match runtime receipt fields")
    if (probe_stdout.read_bytes() != b"Blender 5.2.0 LTS\n\nBlender quit\n"
            or probe_stderr.read_bytes() != b""):
        fail("m2: Python probe emitted unexpected stdout/stderr")
    base_source_root = ctx.root / "upstream/scripts"
    if any(path.is_symlink() for path in base_source_root.rglob("*")):
        fail("m2: base scripts source inventory contains a symlink")
    expected_base_sources = {
        path.relative_to(ctx.root).as_posix()
        for path in (ctx.root / "upstream/scripts").rglob("*")
        if path.is_file() and not path.is_symlink()
        and "__pycache__" not in path.relative_to(ctx.root / "upstream/scripts").parts
        and path.suffix != ".pyc"
    }
    base_rows = assets["base_scripts"]
    if not isinstance(base_rows, list) or len(base_rows) != len(expected_base_sources):
        fail("m2: composed base scripts inventory differs")
    found_base_sources: set[str] = set()
    script_staged_paths: set[str] = set()
    script_prefixes: set[str] = set()
    for number, asset in enumerate(base_rows):
        row = exact(asset, {"source", "staged"}, f"m2.runtime.base_scripts[{number}]")
        source_ref = row["source"]
        if not isinstance(source_ref, dict) or not isinstance(source_ref.get("path"), str):
            fail("m2: base script source reference is malformed")
        source_path = source_ref["path"]
        if source_path in found_base_sources or source_path not in expected_base_sources:
            fail("m2: base script inventory has unknown/duplicate paths")
        source = ctx.file_ref(source_ref, f"m2.runtime.base_scripts[{number}].source", source_path)
        staged_ref = row["staged"]
        if not isinstance(staged_ref, dict) or not isinstance(staged_ref.get("path"), str):
            fail("m2: base script staged reference is malformed")
        staged_path = staged_ref["path"]
        staged = ctx.file_ref(staged_ref, f"m2.runtime.base_scripts[{number}].staged")
        relative = Path(source_path).relative_to("upstream/scripts")
        suffix = f"/scripts/{relative.as_posix()}"
        if not staged_path.endswith(suffix) or not staged.as_posix().endswith(suffix):
            fail("m2: staged base script path differs")
        if staged.read_bytes() != source.read_bytes():
            fail("m2: staged base script bytes differ")
        found_base_sources.add(source_path)
        script_staged_paths.add(staged_path)
        script_prefixes.add(staged_path[:-len(suffix)])
    if found_base_sources != expected_base_sources:
        fail("m2: composed base scripts inventory is incomplete")
    addon_names = {
        "__init__.py", "camera.py", "engine.py", "maketx.py", "operators.py",
        "osl.py", "presets.py", "properties.py", "ui.py", "version_update.py",
    }
    addon_rows = assets["cycles_addon"]
    if not isinstance(addon_rows, list) or len(addon_rows) != len(addon_names):
        fail("m2: composed Cycles add-on inventory differs")
    found_addon_names: set[str] = set()
    for number, asset in enumerate(addon_rows):
        row = exact(asset, {"source", "staged"}, f"m2.runtime.cycles_addon[{number}]")
        source_ref = row["source"]
        if not isinstance(source_ref, dict) or not isinstance(source_ref.get("path"), str):
            fail("m2: Cycles source reference is malformed")
        name = Path(source_ref["path"]).name
        if name in found_addon_names or name not in addon_names:
            fail("m2: Cycles source inventory has unknown/duplicate names")
        source = ctx.file_ref(
            source_ref, f"m2.runtime.cycles_addon[{number}].source",
            f"upstream/intern/cycles/blender/addon/{name}",
        )
        staged_ref = row["staged"]
        if not isinstance(staged_ref, dict) or not isinstance(staged_ref.get("path"), str):
            fail("m2: Cycles staged reference is malformed")
        staged_path = staged_ref["path"]
        suffix = f"/scripts/addons_core/cycles/{name}"
        staged = ctx.file_ref(staged_ref, f"m2.runtime.cycles_addon[{number}].staged")
        if (not staged_path.endswith(suffix) or not staged.as_posix().endswith(suffix)
                or staged.read_bytes() != source.read_bytes()):
            fail("m2: staged Cycles add-on source differs")
        found_addon_names.add(name)
        script_staged_paths.add(staged_path)
        script_prefixes.add(staged_path[:-len(suffix)])
    if found_addon_names != addon_names:
        fail("m2: composed Cycles add-on inventory is incomplete")
    if len(script_prefixes) != 1:
        fail("m2: base/Cycles scripts do not share one composed root")
    m2_require_exact_staged_tree(
        ctx, prefix=script_prefixes.pop(), tree_root="scripts",
        expected_files=script_staged_paths, where="scripts/base/cycles",
    )
    suite_path = ctx.file_ref(receipt["suite_manifest"], "m2.suite_manifest", "sandbox/tierb-prep/suites.tsv")
    suite_names: list[str] = []
    for line in suite_path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        name = line.split("\t", 1)[0]
        if name not in M2_SKIP:
            suite_names.append(name)
    if len(suite_names) != 75 or len(set(suite_names)) != 75 or set(suite_names) != set(M2_KEYS):
        fail("m2: live suites.tsv does not produce the literal 75-key set")
    normalization, _, _ = ctx.load_ref(
        receipt["normalization_policy"], "m2.normalization_policy"
    )
    exact(normalization, {
        "schema", "pipeline", "platform_envelope", "exit_code_primary",
        "suite_envelope", "scratch_root", "repository_root",
        "normalized_bytes_exact_for_pass",
        "exact_replay_by_verifier",
    }, "m2.normalization_policy")
    if (normalization["schema"] != 1 or normalization["exit_code_primary"] is not True
            or normalization["normalized_bytes_exact_for_pass"] is not True
            or normalization["exact_replay_by_verifier"] is not True):
        fail("m2: normalization policy controls are not exact")
    envelope = exact(
        normalization["platform_envelope"], {"native", "wasm", "wasm_optional"},
        "m2.normalization_policy.platform_envelope",
    )
    if envelope != {
        "native": (
            "one exact adjacent bounded-progress-prefix allocator + pinned "
            "native banner, byte-spliced"
        ),
        "wasm": (
            "one exact adjacent bounded-progress-prefix allocator + pinned "
            "Wasm banner, byte-spliced"
        ),
        "wasm_optional": [
            "exact immediately-following locale startup warning",
        ],
    }:
        fail("m2: platform-envelope policy differs")
    suite_envelope = exact(
        normalization["suite_envelope"], {M2_NO_DENOISER_SUITE},
        "m2.normalization_policy.suite_envelope",
    )
    if suite_envelope != {
        M2_NO_DENOISER_SUITE: {
            "wasm": {
                "exact_count": 1,
                "exact_normalized_line": M2_NO_DENOISER_NORMALIZED_LINE.decode().rstrip("\n"),
            },
            "native_optional": {
                "max_count": 1,
                "exact_normalized_line": M2_NATIVE_CUEW_NORMALIZED_LINE.decode().rstrip("\n"),
            },
            "required_cache_flag": "WITH_OPENIMAGEDENOISE:BOOL=OFF",
        },
    }:
        fail("m2: suite-scoped normalization policy differs")
    scratch_root_policy = exact(
        normalization["scratch_root"],
        {"suites", "platforms", "replacement"},
        "m2.normalization_policy.scratch_root",
    )
    if scratch_root_policy != {
        "suites": dict(sorted(M2_SCRATCH_ROOT_POLICIES.items())),
        "platforms": ["native", "wasm"],
        "replacement": M2_SCRATCH_ROOT_TOKEN.decode(),
    }:
        fail("m2: scratch-root normalization policy differs")
    repository_root_policy = exact(
        normalization["repository_root"],
        {"accepted", "replacement", "mixed_roots"},
        "m2.normalization_policy.repository_root",
    )
    if repository_root_policy != {
        "accepted": ["producer host root", "/work container root"],
        "replacement": M2_REPOSITORY_ROOT_TOKEN.decode(),
        "mixed_roots": "reject",
    }:
        fail("m2: repository-root normalization policy differs")
    pipeline = exact(
        normalization["pipeline"], {"native", "wasm"},
        "m2.normalization_policy.pipeline",
    )
    expected_pipeline = {
        "native": [
            "sandbox/final-m0-m3/run_m2.py", "sandbox/tierb-prep/normalize.sed",
        ],
        "wasm": [
            "sandbox/final-m0-m3/run_m2.py", "sandbox/tierb-prep/normalize.sed",
            "sandbox/tierb-prep/wasm-denoise.pl",
        ],
    }
    for platform, expected_paths in expected_pipeline.items():
        refs = pipeline[platform]
        if not isinstance(refs, list) or len(refs) != len(expected_paths):
            fail(f"m2: normalization pipeline differs for {platform}")
        for number, expected_path in enumerate(expected_paths):
            ctx.file_ref(
                refs[number], f"m2.normalization_policy.pipeline.{platform}[{number}]",
                expected_path,
            )
    deferral_path = ctx.file_ref(receipt["deferral_registry"], "m2.deferral_registry", "ledger/deferred.json")
    active, ledger = active_deferrals(deferral_path)
    registry = {row["id"]: row for row in ledger["deferred"]}
    for deferral_id, contract in M2_PASS_DELTA_LEDGER.items():
        registry_row = registry.get(deferral_id)
        if registry_row is None or any(
            registry_row.get(key) != expected for key, expected in contract.items()
        ):
            fail(f"m2: pass-with-delta ledger contract differs: {deferral_id}")
    if receipt["total"] != 75:
        fail("m2: total must be exactly 75")
    rows = exact(receipt["rows"], set(M2_KEYS), "m2.rows")
    for name, value in rows.items():
        row = exact(value, {
            "native_exit", "wasm_exit", "native_raw_log", "wasm_raw_log",
            "native_log", "wasm_log",
            "native_normalized_sha256", "wasm_normalized_sha256", "result",
            "deferral_ids", "deferral_records",
        }, f"m2.rows.{name}")
        native_raw_log = ctx.file_ref(
            row["native_raw_log"], f"m2.rows.{name}.native_raw_log"
        )
        wasm_raw_log = ctx.file_ref(row["wasm_raw_log"], f"m2.rows.{name}.wasm_raw_log")
        native_log = ctx.file_ref(row["native_log"], f"m2.rows.{name}.native_log")
        wasm_log = ctx.file_ref(row["wasm_log"], f"m2.rows.{name}.wasm_log")
        if sha256(native_log) != row["native_normalized_sha256"] or sha256(wasm_log) != row["wasm_normalized_sha256"]:
            fail(f"m2: normalized digest is not bound to result bytes: {name}")
        m2_output = (
            ctx.root / "sandbox/final-m0-m3/evidence" /
            receipt["run_label"] / "m2"
        )
        native_scratch = m2_output / "scratch" / name / "native"
        wasm_scratch = m2_output / "scratch" / name / "wasm"
        if (m2_normalized_bytes(
                native_raw_log.read_bytes(), wasm=False, root=ctx.root, suite=name,
                scratch_root=native_scratch)
                != native_log.read_bytes()
                or m2_normalized_bytes(
                    wasm_raw_log.read_bytes(), wasm=True, root=ctx.root, suite=name,
                    scratch_root=wasm_scratch)
                != wasm_log.read_bytes()):
            fail(f"m2: normalized bytes do not replay exactly from raw evidence: {name}")
        integer(row["native_exit"], f"m2.rows.{name}.native_exit")
        integer(row["wasm_exit"], f"m2.rows.{name}.wasm_exit")
        if row["native_exit"] != 0:
            fail(f"m2: native oracle is not green for {name}")
        pass_delta_id = M2_PASS_DELTA_DEFERRALS.get(name)
        failure_allowed = set(M2_DEFERRALS.get(name, set()))
        allowed = set(failure_allowed)
        if pass_delta_id is not None:
            allowed.add(pass_delta_id)
        declared = row["deferral_ids"]
        if not isinstance(declared, list) or len(declared) != len(set(declared)) or set(declared) - allowed:
            fail(f"m2: unknown or duplicate deferral classification for {name}")
        records = row["deferral_records"]
        if not isinstance(records, list) or len(records) != len(declared):
            fail(f"m2: deferral status/evidence record count differs for {name}")
        recorded: dict[str, dict[str, Any]] = {}
        for number, value in enumerate(records):
            record = exact(value, {"id", "status", "evidence", "marker"},
                           f"m2.rows.{name}.deferral_records[{number}]")
            if not isinstance(record["id"], str) or record["id"] in recorded:
                fail(f"m2: duplicate/non-string deferral status record for {name}")
            recorded[record["id"]] = record
        if set(recorded) != set(declared):
            fail(f"m2: deferral IDs and status/evidence records differ for {name}")
        live_allowed = {item for item in failure_allowed if item in active}
        expected_records = {}
        for item in declared:
            if item not in registry:
                fail(f"m2: declared deferral is absent from the registry: {item}")
            expected_records[item] = {
                "id": item,
                "status": registry[item].get("status"),
                "evidence": registry[item].get("evidence"),
                "marker": (
                    M2_DETECTOR_ACTIVE_MARKER
                    if item == M2_DETECTOR_ACTIVE_ID else
                    M2_PASS_DELTA_MARKERS[name]
                    if item == pass_delta_id else None
                ),
            }
        if recorded != expected_records:
            fail(f"m2: deferral status/evidence is not byte-current for {name}")
        if M2_DETECTOR_ACTIVE_ID in declared and name != M2_DETECTOR_ACTIVE_SUITE:
            fail(f"m2: detector-active classification is scoped to the wrong suite: {name}")
        if M2_DETECTOR_ACTIVE_ID in declared and (
            M2_DETECTOR_ACTIVE_MARKER.encode("utf-8") not in wasm_log.read_bytes()
            or M2_DETECTOR_ACTIVE_RAW_RE.search(wasm_raw_log.read_bytes()) is None
        ):
            fail(f"m2: detector-active row lacks the exact canonical ADR-004 marker: {name}")
        if row["wasm_exit"] == 0:
            if row["native_normalized_sha256"] == row["wasm_normalized_sha256"]:
                if row["result"] != "PASS" or declared or records:
                    fail(f"m2: parity row is not an undeferred PASS: {name}")
            else:
                if (row["result"] != "PASS_WITH_DEFERRAL" or pass_delta_id is None
                        or declared != [pass_delta_id]):
                    fail(f"m2: passing delta lacks its exact declared deferral: {name}")
                m2_validate_pass_delta(name, native_log.read_bytes(), wasm_log.read_bytes())
        else:
            if row["result"] != "DEFERRED" or not declared or set(declared) != live_allowed:
                fail(f"m2: failing row has no exact active deferral: {name}")
        if not live_allowed and row["wasm_exit"] != 0:
            fail(f"m2: non-active-deferral row failed: {name}")


def verify_m2_deps(ctx: Context, receipt: dict[str, Any]) -> None:
    ctx.common(receipt, "m2_deps", {
        "deps_ledger", "inventory_spec", "inventory_manifest", "compliance_proof", "unlisted_artifacts",
        "missing_artifacts", "dependencies", "unresolved_external_policy",
        "external_policy_pass",
    })
    deps_path = ctx.file_ref(receipt["deps_ledger"], "m2_deps.deps_ledger", "ledger/deps.json")
    spec_path = ctx.file_ref(
        receipt["inventory_spec"], "m2_deps.inventory_spec",
        "sandbox/final-m0-m3/m2_dependency_inventory.json",
    )
    spec = strict_json(spec_path.read_text(encoding="utf-8"), "m2 dependency inventory spec")
    if not isinstance(spec, dict) or set(spec) != {"schema", "dependencies"} or spec["schema"] != 1 or not isinstance(spec["dependencies"], dict):
        fail("m2: canonical dependency inventory spec is malformed")
    mapped = spec["dependencies"]
    inventory_path = ctx.file_ref(receipt["inventory_manifest"], "m2_deps.inventory_manifest")
    proof, _, _ = ctx.load_ref(receipt["compliance_proof"], "m2_deps.compliance_proof")
    exact(proof, {"schema", "verdict", "run_label", "source_freeze_sha256", "reuse_exit_code", "violations", "deps_ledger_sha256", "inventory_sha256", "inventory_spec_sha256"}, "m2 compliance proof")
    if proof["schema"] != 1 or proof["verdict"] != "PASS" or proof["run_label"] != ctx.label or proof["source_freeze_sha256"] != ctx.freeze_hash or proof["reuse_exit_code"] != 0 or proof["violations"] != 0 or proof["deps_ledger_sha256"] != sha256(deps_path) or proof["inventory_sha256"] != sha256(inventory_path) or proof["inventory_spec_sha256"] != sha256(spec_path):
        fail("m2: dependency compliance proof is stale or red")
    if receipt["unlisted_artifacts"] != 0 or receipt["missing_artifacts"] != 0:
        fail("m2: dependency inventory is incomplete")
    ledger = strict_json(deps_path.read_text(encoding="utf-8"), "m2 deps ledger")
    built = ledger.get("wasm_built") if isinstance(ledger, dict) else None
    if not isinstance(built, dict):
        fail("m2: deps ledger lacks wasm_built")
    if set(mapped) != set(built):
        fail("m2: canonical dependency inventory keyset differs from wasm_built")
    dependencies = receipt["dependencies"]
    if not isinstance(dependencies, list) or not dependencies:
        fail("m2: dependency receipt has no rows")
    names: set[str] = set()
    artifact_paths: set[str] = set()
    unresolved_expected: dict[str, dict[str, Any]] = {}
    for number, value in enumerate(dependencies):
        row = exact(value, {
            "name", "version", "license", "gpl_compatible", "runtime_linked", "artifacts",
            "notice", "source", "license_payloads",
        }, f"m2_deps.dependencies[{number}]")
        name = row["name"]
        if not isinstance(name, str) or name in names or name not in built:
            fail(f"m2: unknown/duplicate dependency {name!r}")
        names.add(name)
        ledger_row = built[name]
        spec_row = mapped[name]
        if not isinstance(spec_row, dict) or set(spec_row) != {
            "runtime_linked", "artifacts", "license_payloads"
        } or not isinstance(spec_row["runtime_linked"], bool) or not isinstance(spec_row["artifacts"], list) or not isinstance(spec_row["license_payloads"], list):
            fail(f"m2: canonical dependency spec row malformed: {name}")
        if (not isinstance(ledger_row, dict) or ledger_row.get("version") != row["version"]
                or ledger_row.get("license") != row["license"]
                or not isinstance(ledger_row.get("gpl_compatible"), bool)
                or row["gpl_compatible"] is not ledger_row["gpl_compatible"]):
            fail(f"m2: dependency metadata mismatch or implicit compatibility: {name}")
        if not all(isinstance(ledger_row.get(field), str) and ledger_row[field] for field in ("rationale", "source")):
            fail(f"m2: dependency lacks rationale/source: {name}")
        expected_notice = ledger_row.get("license_note", ledger_row.get("notes"))
        if (not isinstance(expected_notice, str) or not expected_notice
                or row["notice"] != expected_notice or row["source"] != ledger_row["source"]):
            fail(f"m2: dependency notice/source mismatch: {name}")
        payloads = row["license_payloads"]
        if not isinstance(payloads, list) or not payloads:
            fail(f"m2: dependency has no exact license payload: {name}")
        payload_paths: list[str] = []
        for index, payload in enumerate(payloads):
            license_path = ctx.file_ref(
                payload, f"m2_deps.dependencies[{number}].license_payloads[{index}]"
            )
            relative = license_path.relative_to(ctx.root).as_posix()
            if (not relative.startswith("LICENSES/")
                    and "/share/licenses/" not in relative
                    and not relative.startswith("THIRD_PARTY_NOTICES/")
                    and not relative.startswith("upstream/release/license/")
                    and not relative.startswith("lib/wasm/share/doc/")
                    and not relative.startswith("lib/wasm/lib/python3.13/")):
                fail(f"m2: dependency license payload uses an unapproved path: {name}")
            payload_paths.append(relative)
        if len(payload_paths) != len(set(payload_paths)):
            fail(f"m2: dependency license payloads contain duplicates: {name}")
        if payload_paths != spec_row["license_payloads"]:
            fail(f"m2: dependency license payloads differ from canonical spec: {name}")
        if row["gpl_compatible"] is False:
            reason = ledger_row.get("gpl_compatible_note")
            if not isinstance(reason, str) or not reason:
                fail(f"m2: unresolved dependency lacks exact external-policy reason: {name}")
            unresolved_expected[name] = {
                "name": name, "license": row["license"], "reason": reason,
                "license_payloads": payloads,
            }
        if not isinstance(row["runtime_linked"], bool):
            fail(f"m2: dependency runtime_linked is not boolean: {name}")
        if row["runtime_linked"] is not spec_row["runtime_linked"]:
            fail(f"m2: dependency runtime classification differs from canonical spec: {name}")
        if not isinstance(row["artifacts"], list):
            fail(f"m2: dependency artifacts is not an array: {name}")
        if row["runtime_linked"] is True and not row["artifacts"]:
            fail(f"m2: runtime-linked dependency has no artifacts: {name}")
        row_artifact_paths: list[str] = []
        for index, ref in enumerate(row["artifacts"]):
            path = ctx.file_ref(ref, f"m2_deps.dependencies[{number}].artifacts[{index}]")
            rel = path.relative_to(ctx.root).as_posix()
            row_artifact_paths.append(rel)
            if rel in artifact_paths:
                fail(f"m2: duplicate dependency artifact: {rel}")
            artifact_paths.add(rel)
        if row_artifact_paths != spec_row["artifacts"]:
            fail(f"m2: dependency artifacts differ from canonical spec: {name}")
    if not REQUIRED_DEPS <= names:
        fail(f"m2: missing mandatory dependency rows: {sorted(REQUIRED_DEPS-names)}")
    if names != set(built):
        fail(f"m2: dependency receipt and wasm_built ledger keysets differ; missing={sorted(set(built)-names)} extra={sorted(names-set(built))}")
    manifest_lines = [line for line in inventory_path.read_text(encoding="utf-8").splitlines() if line]
    manifest_names = set(manifest_lines)
    if len(manifest_names) != len(manifest_lines):
        fail("m2: dependency inventory contains duplicate paths")
    if manifest_names != artifact_paths:
        fail("m2: inventory manifest and dependency artifact set differ")
    current_archives = {
        path.relative_to(ctx.root).as_posix()
        for relative in ("lib/wasm/lib", "lib/wasm/shaderc/lib", "lib/wasm/tint/lib")
        for path in (ctx.root / relative).glob("*.a")
        if path.is_file() and not path.is_symlink()
    }
    mapped_archives = {name for name in artifact_paths if name.endswith(".a")}
    if mapped_archives != current_archives:
        fail("m2: canonical inventory does not exactly enumerate current static archives")
    unresolved = receipt["unresolved_external_policy"]
    if not isinstance(unresolved, list):
        fail("m2: unresolved_external_policy is not an array")
    unresolved_actual: dict[str, dict[str, Any]] = {}
    for number, value in enumerate(unresolved):
        row = exact(value, {"name", "license", "reason", "license_payloads"},
                    f"m2_deps.unresolved_external_policy[{number}]")
        if not isinstance(row["name"], str) or row["name"] in unresolved_actual:
            fail("m2: duplicate/invalid unresolved external-policy row")
        # Re-hash the separately enumerated payloads; equality below also
        # requires the same exact file-ref records as the dependency row.
        for index, payload in enumerate(row["license_payloads"] if isinstance(row["license_payloads"], list) else []):
            ctx.file_ref(payload, f"m2_deps.unresolved_external_policy[{number}].license_payloads[{index}]")
        unresolved_actual[row["name"]] = row
    if unresolved_actual != unresolved_expected:
        fail("m2: unresolved external-policy rows do not exactly enumerate false compatibility rows")
    if receipt["external_policy_pass"] is not (not unresolved_expected):
        fail("m2: external_policy_pass is not the honest unresolved-policy disposition")


def line_manifest(path: Path, where: str, expected_count: int) -> set[str]:
    values = path.read_text(encoding="utf-8").splitlines()
    if len(values) != expected_count or len(set(values)) != expected_count or any(not item or item.strip() != item for item in values):
        fail(f"{where}: expected {expected_count} unique canonical lines")
    return set(values)


def exact_name_manifest(path: Path, where: str, expected_count: int) -> list[str]:
    payload = path.read_bytes()
    try:
        values = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        fail(f"{where}: not UTF-8: {error}")
    if payload != ("\n".join(values) + "\n").encode("utf-8"):
        fail(f"{where}: not canonical LF-terminated text")
    if (len(values) != expected_count or len(set(values)) != expected_count or
            any(re.fullmatch(r"[A-Za-z0-9_.-]+", value) is None for value in values)):
        fail(f"{where}: expected {expected_count} unique canonical identities")
    return values


def verify_m3_device_limit_contract(paths: dict[str, Path]) -> None:
    if set(paths) != set(M3_WEBGPU_DEVICE_LIMIT_PATHS):
        fail("m3: WebGPU device-limit source keyset is not canonical")
    expected = set(M3_WEBGPU_DEVICE_LIMIT_FIELDS)
    for key in ("native_context", "web_fallback"):
        text = paths[key].read_text(encoding="utf-8")
        assignments = re.findall(
            r"\brequired_limits\.([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^;]+);",
            text,
        )
        names = [name for name, _ in assignments]
        if len(assignments) != len(expected) or set(names) != expected:
            fail(f"m3: {key} required limits are not the exact 10-field keyset")
        for name, value in assignments:
            if re.sub(r"\s+", "", value) != f"supported_limits.{name}":
                fail(f"m3: {key} required limit {name} is not sourced from adapter support")
        descriptor = "device_desc" if key == "native_context" else "desc"
        if len(re.findall(
            rf"\b{descriptor}\.requiredLimits\s*=\s*&required_limits\s*;", text
        )) != 1:
            fail(f"m3: {key} required-limit structure is not bound exactly once")

    worker_text = paths["worker_preinit"].read_text(encoding="utf-8")
    objects = re.findall(
        r"\bvar requiredLimits\s*=\s*\{(.*?)\n\s*\};",
        worker_text,
        re.DOTALL,
    )
    if len(objects) != 1:
        fail("m3: worker requiredLimits object is missing or duplicated")
    assignments = re.findall(
        r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([^,]+),\s*$",
        objects[0],
        re.MULTILINE,
    )
    names = [name for name, _ in assignments]
    if len(assignments) != len(expected) or set(names) != expected:
        fail("m3: worker required limits are not the exact 10-field keyset")
    for name, value in assignments:
        if re.sub(r"\s+", "", value) != f"adapter.limits.{name}":
            fail(f"m3: worker required limit {name} is not sourced from its adapter value")
    if len(re.findall(r"\brequiredLimits\s*:\s*requiredLimits\s*,", worker_text)) != 1:
        fail("m3: worker requiredLimits object is not bound exactly once")


def verify_m3_device_limit_sources(ctx: Context, value: Any) -> None:
    rows = exact(value, set(M3_WEBGPU_DEVICE_LIMIT_PATHS), "m3.device_limit_sources")
    paths = {
        key: ctx.file_ref(
            rows[key],
            f"m3.device_limit_sources.{key}",
            expected_path,
        )
        for key, expected_path in M3_WEBGPU_DEVICE_LIMIT_PATHS.items()
    }
    verify_m3_device_limit_contract(paths)


def verify_m3_cache_marker_contract(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for token in (
        'std::getenv("BW_SHADER_CACHE_CENSUS_DIR")',
        'std::getenv("BW_SHADER_CACHE_DIR")',
        "emit_cache_result(sources.name)",
    ):
        if text.count(token) != 1:
            fail(f"m3: cache-marker source lacks one exact activation token: {token}")
    activation = re.compile(
        r'const\s+char\s+\*census_dir\s*=\s*std::getenv\('
        r'"BW_SHADER_CACHE_CENSUS_DIR"\)\s*;\s*'
        r'if\s*\(census_dir\s*==\s*nullptr\)\s*\{\s*return\s+true\s*;\s*\}\s*'
        r'const\s+char\s+\*active_dir\s*=\s*std::getenv\('
        r'"BW_SHADER_CACHE_DIR"\)\s*;\s*'
        r"if\s*\(active_dir\s*==\s*nullptr\s*\|\|\s*active_dir\[0\]\s*==\s*'\\0'\s*"
        r'\|\|\s*std::strcmp\(active_dir,\s*census_dir\)\s*!=\s*0\)\s*'
        r'\{\s*return\s+false\s*;\s*\}',
        re.DOTALL,
    )
    if activation.search(text) is None:
        fail(
            "m3: census cache markers are not suppressed until the exact "
            "census cache directory is active"
        )


def verify_m3_cache_marker_source(ctx: Context, value: Any) -> None:
    path = ctx.file_ref(value, "m3.cache_marker_source", M3_CACHE_MARKER_SOURCE)
    verify_m3_cache_marker_contract(path)


def m3_critical_input_paths() -> dict[str, str]:
    return {
        "binary": "build-native-gpu/bin/tests/blender_test",
        "cmake_cache": "build-native-gpu/CMakeCache.txt",
        "build_ninja": "build-native-gpu/build.ninja",
        "gpu_canonical_manifest": M3_GPU_CANONICAL_MANIFEST,
        "static_shader_canonical_manifest": M3_SHADER_CANONICAL_MANIFEST,
        "cache_marker_source": M3_CACHE_MARKER_SOURCE,
        **{f"device_limit_{key}": path for key, path in M3_WEBGPU_DEVICE_LIMIT_PATHS.items()},
        **{f"opensubdiv_source_{key}": path for key, path in M3_OPENSUBDIV_SOURCE_PATHS.items()},
        "opensubdiv_header": M3_OPENSUBDIV_HEADER,
        "opensubdiv_cpu_archive": M3_OPENSUBDIV_CPU_ARCHIVE,
        "opensubdiv_gpu_archive": M3_OPENSUBDIV_GPU_ARCHIVE,
        "opensubdiv_tool_emar": M3_OPENSUBDIV_TOOLS["emar"],
        "opensubdiv_tool_emnm": M3_OPENSUBDIV_TOOLS["emnm"],
    }


def verify_m3_critical_inputs(ctx: Context, value: Any) -> None:
    row = exact(value, {"before", "after"}, "m3.critical_inputs")
    before = ctx.file_ref(row["before"], "m3.critical_inputs.before")
    after = ctx.file_ref(row["after"], "m3.critical_inputs.after")
    if before.read_bytes() != after.read_bytes():
        fail("m3: critical input pre/post snapshots differ")
    expected = m3_critical_input_paths()
    actual: dict[str, tuple[str, int, str]] = {}
    for line in before.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 4:
            fail("m3: malformed critical input snapshot row")
        key, relative, byte_text, digest = fields
        if key in actual or re.fullmatch(r"[a-z0-9_]+", key) is None:
            fail("m3: duplicate or noncanonical critical input snapshot key")
        try:
            size = int(byte_text)
        except ValueError:
            fail("m3: non-integer critical input snapshot size")
        if size < 0 or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            fail("m3: invalid critical input snapshot size/digest")
        actual[key] = (relative, size, digest)
    if set(actual) != set(expected):
        fail("m3: critical input snapshot keyset is not exact")
    for key, relative in expected.items():
        path = (ctx.root / relative)
        if path.is_symlink() or not path.is_file():
            fail(f"m3: critical input is missing, non-regular, or a symlink: {relative}")
        if actual[key] != (relative, path.stat().st_size, sha256(path)):
            fail(f"m3: critical input snapshot is stale: {key}")


def verify_m3_opensubdiv(ctx: Context, value: Any) -> None:
    row = exact(
        value,
        {
            "version", "tarball_md5", "sources", "header", "cpu_archive",
            "gpu_archive", "tools", "members", "defined_symbols",
            "undefined_symbols", "wasm_smoke",
        },
        "m3.opensubdiv",
    )
    if (row["version"], row["tarball_md5"]) != (
        M3_OPENSUBDIV_VERSION, M3_OPENSUBDIV_TARBALL_MD5
    ):
        fail("m3: OpenSubdiv version/tarball MD5 binding drift")
    sources = exact(row["sources"], set(M3_OPENSUBDIV_SOURCE_PATHS), "m3.opensubdiv.sources")
    source_paths = {
        key: ctx.file_ref(sources[key], f"m3.opensubdiv.sources.{key}", path)
        for key, path in M3_OPENSUBDIV_SOURCE_PATHS.items()
    }
    header = ctx.file_ref(row["header"], "m3.opensubdiv.header", M3_OPENSUBDIV_HEADER)
    cpu_archive = ctx.file_ref(
        row["cpu_archive"], "m3.opensubdiv.cpu_archive", M3_OPENSUBDIV_CPU_ARCHIVE
    )
    gpu_archive = ctx.file_ref(
        row["gpu_archive"], "m3.opensubdiv.gpu_archive", M3_OPENSUBDIV_GPU_ARCHIVE
    )
    tools = exact(row["tools"], set(M3_OPENSUBDIV_TOOLS), "m3.opensubdiv.tools")
    for key, path in M3_OPENSUBDIV_TOOLS.items():
        ctx.file_ref(tools[key], f"m3.opensubdiv.tools.{key}", path)
    recipe = source_paths["recipe"].read_text(encoding="utf-8")
    if (recipe.count(f'OSD_VERSION="{M3_OPENSUBDIV_VERSION}"') != 1 or
            recipe.count(f'OSD_MD5="{M3_OPENSUBDIV_TARBALL_MD5}"') != 1):
        fail("m3: OpenSubdiv recipe lacks the exact version/MD5 pin")
    configure = source_paths["configure"].read_text(encoding="utf-8")
    if "libosdCPU.a" not in configure or "libosdGPU.a" not in configure:
        fail("m3: WebAssembly configure does not bind both OpenSubdiv archives")
    cmake = source_paths["upstream_cmake"].read_text(encoding="utf-8")
    if ("if(WITH_WEBGPU_BACKEND)" not in cmake or
            "add_definitions(-DWITH_WEBGPU_BACKEND)" not in cmake):
        fail("m3: OpenSubdiv CMake lacks WebGPU define propagation")
    evaluator = source_paths["evaluator"].read_text(encoding="utf-8")
    for marker in (
        "defined(WITH_WEBGPU_BACKEND)", "GPU_BACKEND_WEBGPU",
        "GLSLPatchShaderSource::GetPatchBasisShaderSource()",
    ):
        if marker not in evaluator:
            fail(f"m3: OpenSubdiv evaluator lacks WebGPU GLSL selection: {marker}")
    header_text = header.read_text(encoding="utf-8")
    if ("class GLSLPatchShaderSource" not in header_text or
            "static std::string GetPatchBasisShaderSource();" not in header_text):
        fail("m3: harvested OpenSubdiv header lacks its GLSL patch-source API")
    if cpu_archive.stat().st_size <= 8 or gpu_archive.stat().st_size <= 8:
        fail("m3: harvested OpenSubdiv archive is empty")

    members_path = ctx.file_ref(row["members"], "m3.opensubdiv.members")
    defined_path = ctx.file_ref(row["defined_symbols"], "m3.opensubdiv.defined_symbols")
    undefined_path = ctx.file_ref(
        row["undefined_symbols"], "m3.opensubdiv.undefined_symbols"
    )
    smoke_path = ctx.file_ref(row["wasm_smoke"], "m3.opensubdiv.wasm_smoke")
    commands = {
        "members": ([os.fspath(ctx.root / M3_OPENSUBDIV_TOOLS["emar"]), "t",
                     os.fspath(gpu_archive)], members_path, 300),
        "defined_symbols": (
            [os.fspath(ctx.root / M3_OPENSUBDIV_TOOLS["emnm"]), "-C", "--defined-only",
             os.fspath(gpu_archive)],
            defined_path,
            300,
        ),
        "undefined_symbols": (
            [os.fspath(ctx.root / M3_OPENSUBDIV_TOOLS["emnm"]), "--undefined-only",
             os.fspath(gpu_archive)],
            undefined_path,
            300,
        ),
        "wasm_smoke": (
            [os.fspath(source_paths["recipe"]), "--test"], smoke_path, 900
        ),
    }
    for proof_name, (command, recorded_path, timeout) in commands.items():
        try:
            result = subprocess.run(
                command,
                cwd=ctx.root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            fail(f"m3: could not independently repeat OpenSubdiv {proof_name}: {error}")
        if result.returncode != 0 or result.stdout != recorded_path.read_bytes():
            fail(
                f"m3: repeated OpenSubdiv {proof_name} proof differs from recorded bytes"
            )
    member_names = [
        line.strip()
        for line in members_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip()
    ]
    if not any("glslPatchShaderSource" in name for name in member_names):
        fail("m3: OpenSubdiv GPU archive proof lacks the GLSL source object")
    forbidden = ("glComputeEvaluator", "glVertexBuffer", "glPatchTable", "glMesh")
    if any(any(token in name for token in forbidden) for name in member_names):
        fail("m3: OpenSubdiv GPU archive proof contains OpenGL objects")
    defined = defined_path.read_text(encoding="utf-8", errors="replace")
    symbol = (
        "OpenSubdiv::v3_7_0::Osd::GLSLPatchShaderSource::"
        "GetPatchBasisShaderSource()"
    )
    if re.search(rf"(?m)^\S+\s+[TtWw]\s+{re.escape(symbol)}$", defined) is None:
        fail("m3: OpenSubdiv GPU archive proof lacks its defined GLSL source symbol")
    undefined = undefined_path.read_text(encoding="utf-8", errors="replace")
    if re.search(r"(?:^|\s)_?gl[A-Z]", undefined, re.MULTILINE) is not None:
        fail("m3: OpenSubdiv GPU archive proof imports an OpenGL API symbol")
    smoke = smoke_path.read_text(encoding="utf-8", errors="replace")
    if re.search(
        r"OSD_WASM_REFINE nverts_level1=26 glsl_bytes=[1-9][0-9]* "
        r"param=1 evaluate=1",
        smoke,
    ) is None:
        fail("m3: OpenSubdiv Wasm smoke lacks Far=26 and both GLSL source markers")


def verify_m3_draw_webgpu_list(stdout_path: Path, stderr_path: Path) -> list[str]:
    if stderr_path.read_bytes() != b"":
        fail("m3: supplemental DrawWebGPUTest list wrote stderr")
    text = stdout_path.read_text(encoding="utf-8", errors="replace")
    names: list[str] = []
    saw_suite = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line:
            continue
        if raw[:1].isspace():
            if not saw_suite:
                fail("m3: supplemental DrawWebGPUTest list contains an orphan test")
            names.append(f"DrawWebGPUTest.{line.strip()}")
        else:
            if line != "DrawWebGPUTest." or saw_suite:
                fail(f"m3: supplemental DrawWebGPUTest list has unexpected text: {line}")
            saw_suite = True
    if tuple(names) != M3_DRAW_WEBGPU_TESTS:
        fail(f"m3: supplemental DrawWebGPUTest list is not exact: {names!r}")
    return names


def verify_m3_gpu_webgpu_list(stdout_path: Path, stderr_path: Path) -> list[str]:
    if stderr_path.read_bytes() != b"":
        fail("m3: primary GPUWebGPUTest list wrote stderr")
    text = stdout_path.read_text(encoding="utf-8", errors="replace")
    names: list[str] = []
    saw_suite = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line:
            continue
        if raw[:1].isspace():
            if not saw_suite:
                fail("m3: primary GPUWebGPUTest list contains an orphan test")
            names.append(line.strip())
        else:
            if line != "GPUWebGPUTest." or saw_suite:
                fail(f"m3: primary GPUWebGPUTest list has unexpected text: {line}")
            saw_suite = True
    if len(names) != M3_GPU_TEST_COUNT or len(set(names)) != M3_GPU_TEST_COUNT:
        fail(f"m3: primary GPUWebGPUTest list is not exact: {len(names)}")
    return names


def verify_m3_draw_webgpu_run(path: Path, expected_name: str) -> None:
    if expected_name not in M3_DRAW_WEBGPU_TESTS:
        fail(f"m3: unexpected supplemental DrawWebGPUTest identity: {expected_name}")
    text = path.read_text(encoding="utf-8", errors="replace")
    if text.count(M3_UNCAPTURED_DEVICE_ERROR) != 0:
        fail(f"m3: supplemental DrawWebGPUTest has an uncaptured device error: {expected_name}")
    if text.count(M3_MEMORY_LEAK_ERROR) != 0:
        fail(f"m3: supplemental DrawWebGPUTest reports leaked memory: {expected_name}")
    run_rows = re.findall(r"(?m)^\[ RUN      \] (.+)$", text)
    ok_rows = re.findall(r"(?m)^\[       OK \] (.+)$", text)
    ok_pattern = re.compile(
        rf"^{re.escape(expected_name)}(?: \((?:[0-9]+|<1) ms\))?$"
    )
    if run_rows != [expected_name] or len(ok_rows) != 1 or ok_pattern.fullmatch(ok_rows[0]) is None:
        fail(f"m3: supplemental DrawWebGPUTest lacks one exact RUN/OK pair: {expected_name}")
    if "[  FAILED  ]" in text or "[  SKIPPED ]" in text:
        fail(f"m3: supplemental DrawWebGPUTest contains a failed/skipped row: {expected_name}")


def verify_m3_gpu_webgpu_run(path: Path, expected_name: str) -> None:
    if not expected_name.startswith("GPUWebGPUTest."):
        fail(f"m3: unexpected primary GPUWebGPUTest identity: {expected_name}")
    text = path.read_text(encoding="utf-8", errors="replace")
    if text.count(M3_UNCAPTURED_DEVICE_ERROR) != 0:
        fail(f"m3: GPUWebGPUTest has an uncaptured device error: {expected_name}")
    if text.count(M3_MEMORY_LEAK_ERROR) != 0:
        fail(f"m3: GPUWebGPUTest reports leaked memory: {expected_name}")
    run_rows = re.findall(r"(?m)^\[ RUN      \] (.+)$", text)
    ok_rows = re.findall(r"(?m)^\[       OK \] (.+)$", text)
    ok_pattern = re.compile(
        rf"^{re.escape(expected_name)}(?: \((?:[0-9]+|<1) ms\))?$"
    )
    if run_rows != [expected_name] or len(ok_rows) != 1 or ok_pattern.fullmatch(ok_rows[0]) is None:
        fail(f"m3: GPUWebGPUTest lacks one exact RUN/OK pair: {expected_name}")
    if "[  FAILED  ]" in text or "[  SKIPPED ]" in text:
        fail(f"m3: GPUWebGPUTest contains a failed/skipped row: {expected_name}")


def verify_m3_static_log(path: Path, expected_cache: str, where: str) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    begin_rows = [index for index, line in enumerate(lines) if line == M3_CENSUS_BEGIN]
    end_rows = [index for index, line in enumerate(lines) if line == M3_CENSUS_END]
    if len(begin_rows) != 1 or len(end_rows) != 1 or begin_rows[0] >= end_rows[0]:
        fail(f"{where}: lacks one ordered shader census boundary pair")
    before = "\n".join(lines[:begin_rows[0]])
    after = "\n".join(lines[end_rows[0] + 1:])
    if (M3_SHADER_ROW_RE.search(before) or M3_SHADER_ROW_RE.search(after) or
            M3_CACHE_ROW_RE.search(before) or M3_CACHE_ROW_RE.search(after)):
        fail(f"{where}: shader/cache row escaped the census boundaries")
    census = "\n".join(lines[begin_rows[0] + 1:end_rows[0]]) + "\n"
    # Dawn validation callbacks are asynchronous and may be delivered outside
    # the marker interval. Keep rows boundary-scoped, but make every native
    # uncaptured-error marker in the complete invocation release-fatal.
    device_errors = text.count(M3_UNCAPTURED_DEVICE_ERROR)
    if device_errors != 0:
        fail(f"{where}: contains {device_errors} uncaptured WebGPU device errors")
    memory_leaks = text.count(M3_MEMORY_LEAK_ERROR)
    if memory_leaks != 0:
        fail(f"{where}: contains {memory_leaks} leaked-memory reports")
    shader_rows = M3_SHADER_ROW_RE.findall(census)
    cache_rows = M3_CACHE_ROW_RE.findall(census)
    if (len(shader_rows) != M3_SHADER_COUNT or
            len({name for _, name in shader_rows}) != M3_SHADER_COUNT):
        fail(f"{where}: shader census is not {M3_SHADER_COUNT} unique rows")
    if any(status != "PASS" for status, _ in shader_rows):
        fail(f"{where}: shader census contains a non-PASS result")
    if (len(cache_rows) != M3_SHADER_COUNT or
            len({name for _, name in cache_rows}) != M3_SHADER_COUNT):
        fail(f"{where}: cache census is not {M3_SHADER_COUNT} unique rows")
    if any(status != expected_cache for status, _ in cache_rows):
        fail(f"{where}: cache census is not uniformly {expected_cache}")
    shader_names = [name for _, name in shader_rows]
    if set(shader_names) != {name for _, name in cache_rows}:
        fail(f"{where}: shader/cache identity sets differ")
    if (M3_REQUIRED_SHADER_ID not in shader_names or
            M3_FORBIDDEN_SHADER_ID in shader_names):
        fail(
            f"{where}: lacks exact fullscreen_blit -> "
            "draw_debug_draw_compact substitution"
        )
    return shader_names


def verify_m3_cmake_cache(cache: Path, root: Path) -> None:
    required = {
        "CMAKE_BUILD_TYPE": "Release",
        "CMAKE_GENERATOR": "Ninja",
        "CMAKE_HOME_DIRECTORY": os.fspath((root / "upstream").resolve()),
        "WITH_GTESTS": "ON",
        "WITH_GPU_BACKEND_TESTS": "ON",
        "WITH_GPU_DRAW_TESTS": "ON",
        "WITH_OPENSUBDIV": "ON",
        "WITH_WEBGPU_BACKEND": "ON",
    }
    values: dict[str, str] = {}
    for raw in cache.read_text(encoding="utf-8").splitlines():
        if not raw or raw.startswith(("#", "//")) or "=" not in raw:
            continue
        typed, value = raw.split("=", 1)
        if ":" not in typed:
            continue
        key, _kind = typed.split(":", 1)
        if key in required:
            if key in values:
                fail(f"m3: duplicate CMake cache key {key}")
            values[key] = value
    if values != required:
        fail("m3: CMake cache is not the canonical native WebGPU test configuration")


def verify_m3_build_graph(ninja: Path) -> None:
    lines = ninja.read_text(encoding="utf-8").splitlines()
    link_prefix = "build bin/tests/blender_test: "
    links = [line for line in lines if line.startswith(link_prefix)]
    aliases = [line for line in lines if line.startswith("build blender_test: ")]
    if (len(links) != 1 or "CXX_EXECUTABLE_LINKER" not in links[0]
            or aliases != ["build blender_test: phony bin/tests/blender_test"]):
        fail("m3: build.ninja lacks the unique canonical blender_test link and target alias")


def verify_m3_ninja_no_work(
    ctx: Context, value: Any, where: str = "m3.no_work"
) -> dict[str, Any]:
    row = exact(
        value,
        {"command", "cwd", "target", "returncode", "stdout", "stderr"},
        where,
    )
    build_name = "build-native-gpu"
    build_root = ctx.root / build_name
    target = "blender_test"
    if row["cwd"] != build_name or row["target"] != target:
        fail("m3: Ninja no-work build root/target is not canonical")
    stdout_path = ctx.file_ref(row["stdout"], where + ".stdout")
    stderr_path = ctx.file_ref(row["stderr"], where + ".stderr")
    recorded_stdout = stdout_path.read_bytes()
    recorded_stderr = stderr_path.read_bytes()
    require_ninja_no_work_result(
        row["command"], build_root, row["returncode"],
        recorded_stdout, recorded_stderr,
        expected_build_root=build_root, expected_target=target,
        where=where + ".recorded",
    )
    try:
        command = ninja_locked_command("-n", target)
        live = subprocess.run(
            command, cwd=build_root,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=120, check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        fail(f"m3: could not independently repeat Ninja dry-run: {error}")
    require_ninja_no_work_result(
        command, build_root, live.returncode,
        live.stdout, live.stderr,
        expected_build_root=build_root, expected_target=target,
        where=where + ".live",
    )
    if (live.returncode, live.stdout, live.stderr) != (
        row["returncode"], recorded_stdout, recorded_stderr
    ):
        fail("m3: repeated Ninja dry-run differs from the recorded no-work attestation")
    return row


def verify_m3(ctx: Context, receipt: dict[str, Any], m0_receipt_hash: str) -> None:
    ctx.common(receipt, "m3", {
        "binary", "cmake_cache", "build_ninja", "no_work", "final_no_work",
        "critical_inputs",
        "device_limit_sources", "cache_marker_source", "opensubdiv",
        "toolchain_binding_sha256", "gpu_tests",
        "draw_webgpu_tests", "static_shaders", "shader_cache",
    })
    verify_m3_device_limit_sources(ctx, receipt["device_limit_sources"])
    verify_m3_cache_marker_source(ctx, receipt["cache_marker_source"])
    verify_m3_opensubdiv(ctx, receipt["opensubdiv"])
    verify_m3_critical_inputs(ctx, receipt["critical_inputs"])
    binary = ctx.file_ref(
        receipt["binary"], "m3.binary",
        "build-native-gpu/bin/tests/blender_test",
    )
    cmake_cache = ctx.file_ref(
        receipt["cmake_cache"], "m3.cmake_cache",
        "build-native-gpu/CMakeCache.txt",
    )
    build_ninja = ctx.file_ref(
        receipt["build_ninja"], "m3.build_ninja",
        "build-native-gpu/build.ninja",
    )
    build_root = ctx.root / "build-native-gpu"
    if build_root.is_symlink() or not build_root.is_dir() or any(path.is_symlink() for path in (
        build_root / "bin/tests/blender_test",
        build_root / "CMakeCache.txt",
        build_root / "build.ninja",
    )):
        fail("m3: canonical binary/cache/build graph is missing, invalid, or symlinked")
    verify_m3_cmake_cache(cmake_cache, ctx.root)
    verify_m3_build_graph(build_ninja)
    no_work = verify_m3_ninja_no_work(ctx, receipt["no_work"])
    final_no_work = verify_m3_ninja_no_work(
        ctx, receipt["final_no_work"], "m3.final_no_work"
    )
    if receipt["toolchain_binding_sha256"] != m0_receipt_hash:
        fail("m3: toolchain binding is not the exact M0 receipt")
    gpu = exact(
        receipt["gpu_tests"],
        {"canonical_manifest", "manifest", "raw_result", "list_stdout", "list_stderr",
         "total", "passed", "failed", "crashed", "rows"},
        "m3.gpu_tests",
    )
    canonical_gpu_path = ctx.file_ref(
        gpu["canonical_manifest"], "m3.gpu_tests.canonical_manifest",
        M3_GPU_CANONICAL_MANIFEST,
    )
    canonical_gpu_names = exact_name_manifest(
        canonical_gpu_path, "m3 canonical GPUWebGPUTest manifest", M3_GPU_TEST_COUNT
    )
    if canonical_gpu_names != sorted(canonical_gpu_names):
        fail("m3: canonical GPUWebGPUTest manifest is not sorted")
    gpu_list_stdout = ctx.file_ref(gpu["list_stdout"], "m3.gpu_tests.list_stdout")
    gpu_list_stderr = ctx.file_ref(gpu["list_stderr"], "m3.gpu_tests.list_stderr")
    listed_gpu_names = verify_m3_gpu_webgpu_list(gpu_list_stdout, gpu_list_stderr)
    if sorted(f"GPUWebGPUTest.{name}" for name in listed_gpu_names) != canonical_gpu_names:
        fail("m3: raw GPUWebGPUTest list differs from the checked-in exact manifest")
    manifest_path = ctx.file_ref(gpu["manifest"], "m3.gpu_tests.manifest")
    generated_gpu_names = exact_name_manifest(
        manifest_path, "m3 generated GPU manifest", M3_GPU_TEST_COUNT
    )
    if generated_gpu_names != canonical_gpu_names:
        fail("m3: generated GPU manifest differs from raw/canonical identities")
    names = set(generated_gpu_names)
    gpu_raw, _, _ = ctx.load_ref(gpu["raw_result"], "m3.gpu_tests.raw_result")
    exact(gpu_raw, {"schema", "verdict", "run_label", "source_freeze_sha256", "binary_sha256", "cmake_cache_sha256", "build_ninja_sha256", "no_work", "final_no_work", "manifest_sha256", "canonical_manifest_sha256", "list_stdout_sha256", "list_stderr_sha256", "total", "passed", "failed", "crashed"}, "m3 GPU raw result")
    if (gpu["total"], gpu["passed"], gpu["failed"], gpu["crashed"]) != (
        M3_GPU_TEST_COUNT, M3_GPU_TEST_COUNT, 0, 0
    ):
        fail(
            f"m3: GPU suite must be exactly {M3_GPU_TEST_COUNT}/{M3_GPU_TEST_COUNT} "
            "PASS with zero fail/crash"
        )
    if gpu_raw != {"schema": 1, "verdict": "PASS", "run_label": ctx.label, "source_freeze_sha256": ctx.freeze_hash, "binary_sha256": receipt["binary"]["sha256"], "cmake_cache_sha256": receipt["cmake_cache"]["sha256"], "build_ninja_sha256": receipt["build_ninja"]["sha256"], "no_work": no_work, "final_no_work": final_no_work, "manifest_sha256": gpu["manifest"]["sha256"], "canonical_manifest_sha256": gpu["canonical_manifest"]["sha256"], "list_stdout_sha256": gpu["list_stdout"]["sha256"], "list_stderr_sha256": gpu["list_stderr"]["sha256"], "total": M3_GPU_TEST_COUNT, "passed": M3_GPU_TEST_COUNT, "failed": 0, "crashed": 0}:
        fail("m3: raw GPU result is stale, red, or bound to another binary/manifest")
    rows = exact(gpu["rows"], names, "m3.gpu_tests.rows")
    for name, value in rows.items():
        row = exact(value, {"status", "exit_code", "raw_log"}, f"m3.gpu_tests.rows.{name}")
        if row["status"] != "PASS" or row["exit_code"] != 0:
            fail(f"m3: GPU test did not pass: {name}")
        verify_m3_gpu_webgpu_run(
            ctx.file_ref(row["raw_log"], f"m3.gpu_tests.rows.{name}.raw_log"), name
        )
    draw = exact(
        receipt["draw_webgpu_tests"],
        {
            "manifest", "raw_result", "list_stdout", "list_stderr",
            "total", "passed", "failed", "crashed", "rows",
        },
        "m3.draw_webgpu_tests",
    )
    draw_manifest = ctx.file_ref(draw["manifest"], "m3.draw_webgpu_tests.manifest")
    draw_names = line_manifest(
        draw_manifest, "m3 supplemental DrawWebGPUTest manifest", len(M3_DRAW_WEBGPU_TESTS)
    )
    if draw_names != set(M3_DRAW_WEBGPU_TESTS):
        fail("m3: supplemental DrawWebGPUTest manifest identity differs")
    draw_list_stdout = ctx.file_ref(
        draw["list_stdout"], "m3.draw_webgpu_tests.list_stdout"
    )
    draw_list_stderr = ctx.file_ref(
        draw["list_stderr"], "m3.draw_webgpu_tests.list_stderr"
    )
    if set(verify_m3_draw_webgpu_list(draw_list_stdout, draw_list_stderr)) != draw_names:
        fail("m3: supplemental DrawWebGPUTest raw list differs from its manifest")
    draw_raw, _, _ = ctx.load_ref(
        draw["raw_result"], "m3.draw_webgpu_tests.raw_result"
    )
    exact(
        draw_raw,
        {
            "schema", "verdict", "run_label", "source_freeze_sha256",
            "binary_sha256", "cmake_cache_sha256", "build_ninja_sha256",
            "no_work", "final_no_work", "manifest_sha256", "list_stdout_sha256",
            "list_stderr_sha256", "total", "passed", "failed", "crashed",
        },
        "m3 supplemental DrawWebGPUTest raw result",
    )
    if (draw["total"], draw["passed"], draw["failed"], draw["crashed"]) != (
        len(M3_DRAW_WEBGPU_TESTS), len(M3_DRAW_WEBGPU_TESTS), 0, 0
    ):
        fail("m3: supplemental DrawWebGPUTest suite is not exact 2/2 PASS")
    expected_draw_raw = {
        "schema": 1,
        "verdict": "PASS",
        "run_label": ctx.label,
        "source_freeze_sha256": ctx.freeze_hash,
        "binary_sha256": receipt["binary"]["sha256"],
        "cmake_cache_sha256": receipt["cmake_cache"]["sha256"],
        "build_ninja_sha256": receipt["build_ninja"]["sha256"],
        "no_work": no_work,
        "final_no_work": final_no_work,
        "manifest_sha256": draw["manifest"]["sha256"],
        "list_stdout_sha256": draw["list_stdout"]["sha256"],
        "list_stderr_sha256": draw["list_stderr"]["sha256"],
        "total": len(M3_DRAW_WEBGPU_TESTS),
        "passed": len(M3_DRAW_WEBGPU_TESTS),
        "failed": 0,
        "crashed": 0,
    }
    if draw_raw != expected_draw_raw:
        fail("m3: supplemental DrawWebGPUTest raw result is stale or misbound")
    draw_rows = exact(draw["rows"], set(M3_DRAW_WEBGPU_TESTS), "m3.draw_webgpu_tests.rows")
    for name, value in draw_rows.items():
        row = exact(
            value, {"status", "exit_code", "raw_log"}, f"m3.draw_webgpu_tests.rows.{name}"
        )
        if row["status"] != "PASS" or row["exit_code"] != 0:
            fail(f"m3: supplemental DrawWebGPUTest did not pass: {name}")
        verify_m3_draw_webgpu_run(
            ctx.file_ref(row["raw_log"], f"m3.draw_webgpu_tests.rows.{name}.raw_log"),
            name,
        )
    static = exact(
        receipt["static_shaders"],
        {"canonical_manifest", "manifest", "raw_result", "cold_log", "warm_log",
         "total", "passed", "excluded", "failed", "rows"},
        "m3.static_shaders",
    )
    canonical_shader_path = ctx.file_ref(
        static["canonical_manifest"], "m3.static_shaders.canonical_manifest",
        M3_SHADER_CANONICAL_MANIFEST,
    )
    canonical_shader_names = exact_name_manifest(
        canonical_shader_path, "m3 canonical static-shader manifest", M3_SHADER_COUNT
    )
    if canonical_shader_names != sorted(canonical_shader_names):
        fail("m3: canonical static-shader manifest is not sorted")
    generated_shader_path = ctx.file_ref(
        static["manifest"], "m3.static_shaders.manifest"
    )
    generated_shader_names = exact_name_manifest(
        generated_shader_path, "m3 generated shader manifest", M3_SHADER_COUNT
    )
    if generated_shader_names != canonical_shader_names:
        fail("m3: generated shader manifest differs from the canonical identities")
    shader_names = set(canonical_shader_names)
    static_raw, _, _ = ctx.load_ref(static["raw_result"], "m3.static_shaders.raw_result")
    cold_shader_names = verify_m3_static_log(
        ctx.file_ref(static["cold_log"], "m3.static_shaders.cold_log"),
        "MISS",
        "m3 cold static log",
    )
    warm_shader_names = verify_m3_static_log(
        ctx.file_ref(static["warm_log"], "m3.static_shaders.warm_log"),
        "HIT",
        "m3 warm static log",
    )
    if (set(cold_shader_names) != set(warm_shader_names) or
            set(cold_shader_names) != shader_names):
        fail("m3: cold/warm raw shader or canonical identity set differs")
    exact(static_raw, {"schema", "verdict", "run_label", "source_freeze_sha256", "binary_sha256", "cmake_cache_sha256", "build_ninja_sha256", "no_work", "final_no_work", "manifest_sha256", "canonical_manifest_sha256", "total", "passed", "excluded", "failed"}, "m3 shader raw result")
    integer(static["passed"], "m3.static_shaders.passed")
    integer(static["excluded"], "m3.static_shaders.excluded")
    if (static["total"] != M3_SHADER_COUNT or static["failed"] != 0 or
            static["passed"] + static["excluded"] != M3_SHADER_COUNT):
        fail(
            f"m3: shader census must account exactly for {M3_SHADER_COUNT} "
            "with zero unexplained failures"
        )
    if static_raw != {"schema": 1, "verdict": "PASS", "run_label": ctx.label, "source_freeze_sha256": ctx.freeze_hash, "binary_sha256": receipt["binary"]["sha256"], "cmake_cache_sha256": receipt["cmake_cache"]["sha256"], "build_ninja_sha256": receipt["build_ninja"]["sha256"], "no_work": no_work, "final_no_work": final_no_work, "manifest_sha256": static["manifest"]["sha256"], "canonical_manifest_sha256": static["canonical_manifest"]["sha256"], "total": static["total"], "passed": static["passed"], "excluded": static["excluded"], "failed": 0}:
        fail("m3: raw shader result is stale, red, or bound to another binary/manifest")
    srows = exact(static["rows"], shader_names, "m3.static_shaders.rows")
    deferrals_path = ctx.path("ledger/deferred.json", "m3 deferral registry")
    active, _ = active_deferrals(deferrals_path)
    pass_count = excluded_count = 0
    for name, value in srows.items():
        if not isinstance(value, dict) or value.get("status") not in {"PASS", "EXCLUDED"}:
            fail(f"m3: invalid shader result: {name}")
        if value["status"] == "PASS":
            exact(value, {"status"}, f"m3.static_shaders.rows.{name}")
            pass_count += 1
        else:
            row = exact(value, {"status", "deferral_id", "feature_scope", "non_shipping"}, f"m3.static_shaders.rows.{name}")
            if row["deferral_id"] not in M3_COMPILER_DEFERRALS or row["deferral_id"] not in active or row["non_shipping"] is not True or not isinstance(row["feature_scope"], str) or not row["feature_scope"]:
                fail(f"m3: shader exclusion is not an active, scoped, non-shipping compiler limitation: {name}")
            excluded_count += 1
    if (pass_count, excluded_count) != (static["passed"], static["excluded"]):
        fail("m3: shader counters differ from rows")
    cache = exact(receipt["shader_cache"], {"manifest", "cold_proof", "warm_proof", "source_digest", "toolchain_digest", "entries"}, "m3.shader_cache")
    if cache["source_digest"] != ctx.freeze_hash or cache["toolchain_digest"] != m0_receipt_hash:
        fail("m3: shader cache is not bound to frozen source and exact M0 toolchain receipt")
    cache_manifest = ctx.file_ref(cache["manifest"], "m3.shader_cache.manifest")
    cold, _, _ = ctx.load_ref(cache["cold_proof"], "m3.shader_cache.cold_proof")
    warm, _, _ = ctx.load_ref(cache["warm_proof"], "m3.shader_cache.warm_proof")
    for where, proof, mode in (("cold", cold, "cold"), ("warm", warm, "warm")):
        exact(proof, {"schema", "verdict", "run_label", "mode", "cache_manifest_sha256", "source_digest", "toolchain_digest", "hits", "misses"}, f"m3 cache {where} proof")
        if proof["schema"] != 1 or proof["verdict"] != "PASS" or proof["run_label"] != ctx.label or proof["mode"] != mode or proof["cache_manifest_sha256"] != sha256(cache_manifest) or proof["source_digest"] != cache["source_digest"] or proof["toolchain_digest"] != cache["toolchain_digest"]:
            fail(f"m3: {where} cache proof binding mismatch")
        integer(proof["hits"], f"m3 cache {where}.hits")
        integer(proof["misses"], f"m3 cache {where}.misses")
    if cold["hits"] != 0 or cold["misses"] != cache["entries"] or warm["hits"] != cache["entries"] or warm["misses"] != 0 or cache["entries"] != static["passed"]:
        fail("m3: cold/warm cache census is not exact for every compiled shader")


def verify_runtime_cross_binding(
    m0: dict[str, Any], m1: dict[str, Any], m2: dict[str, Any]
) -> None:
    m1_runtime = m1["runtime"]
    m2_runtime = m2["runtime"]
    for key in ("native_oracle", "node", "javascript", "wasm", "node_version"):
        if m1_runtime[key] != m2_runtime[key]:
            fail(f"m1/m2: canonical runtime identity differs for {key}")
    if m0["artifacts"]["native_oracle"] != m1_runtime["native_oracle"]:
        fail("m0/m1/m2: native oracle is not the exact M0-bound wrapper")


def verify(root: Path, manifest_path: Path, now: dt.datetime, max_age: int) -> dict[str, Any]:
    if max_age < 1 or max_age > MAX_FRESHNESS_SECONDS:
        fail(f"--max-age-seconds must be 1..{MAX_FRESHNESS_SECONDS}")
    ctx = Context(root, now, max_age)
    if manifest_path.resolve().parent != ctx.root and ctx.root not in manifest_path.resolve().parents:
        fail("candidate manifest must be inside the verified root")
    try:
        manifest = strict_json(manifest_path.read_text(encoding="utf-8"), "candidate manifest")
    except OSError as error:
        fail(f"candidate manifest: invalid JSON: {error}")
    manifest = exact(manifest, {"schema", "verdict", "run_label", "created_utc", "source_tree", "source_freeze", "receipts"}, "candidate manifest")
    if manifest["schema"] != 1 or manifest["verdict"] != "PASS" or manifest["source_tree"] != "upstream":
        fail("candidate manifest: wrong schema/verdict/source_tree")
    if not isinstance(manifest["run_label"], str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,79}", manifest["run_label"]):
        fail("candidate manifest: invalid run label")
    ctx.label = manifest["run_label"]
    manifest_time = parse_time(manifest["created_utc"], "candidate manifest.created_utc")
    ctx.manifest_time = manifest_time
    if manifest_time > now or (now - manifest_time).total_seconds() > max_age:
        fail("candidate manifest is future-dated or stale")
    verify_source_freeze(ctx, manifest["source_freeze"])
    if manifest_time < ctx.freeze_time:
        fail("candidate manifest predates source freeze")
    refs = exact(manifest["receipts"], {"m0", "m1", "m2", "m2_deps", "m3"}, "candidate manifest.receipts")
    loaded: dict[str, dict[str, Any]] = {}
    hashes: dict[str, str] = {}
    for name in sorted(refs):
        loaded[name], hashes[name], _ = ctx.load_ref(refs[name], f"candidate manifest.receipts.{name}")
    verify_m0(ctx, loaded["m0"])
    verify_m1(ctx, loaded["m1"])
    verify_m2(ctx, loaded["m2"])
    verify_runtime_cross_binding(loaded["m0"], loaded["m1"], loaded["m2"])
    verify_m2_deps(ctx, loaded["m2_deps"])
    verify_m3(ctx, loaded["m3"], hashes["m0"])
    return {
        "schema": 1,
        "verdict": "PASS",
        "run_label": ctx.label,
        "source_freeze_sha256": ctx.freeze_hash,
        "receipt_sha256": hashes,
        "contracts": {
            "m0": "pins+container+CI+caches+REUSE",
            "m1": "enumerated blenlib+bmesh gtests all-pass; 9+12 state parity",
            "m2": "75 exact keys; active deferrals only; deps complete/compliant",
            "m3": "197/197 GPU; 1003 shader census; cache/source/toolchain bound",
        },
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--max-age-seconds", type=int, default=MAX_FRESHNESS_SECONDS)
    parser.add_argument("--now", help="test-only UTC RFC3339 timestamp; default is the live clock")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        now = parse_time(args.now, "--now") if args.now else dt.datetime.now(dt.timezone.utc)
        result = verify(args.root, args.manifest, now, args.max_age_seconds)
    except (VerificationError, OSError, subprocess.SubprocessError) as error:
        print(f"final-m0-m3: FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
