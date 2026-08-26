#!/usr/bin/env python3
"""Freeze the complete technical release source across both project Git roots.

The top-level repository deliberately ignores ``upstream/``.  A release freeze
of only one repository is therefore incomplete: it either omits the top-level
web shell/assemblers/verifiers or omits the patched Blender source.  This driver
creates and binds one canonical freeze for each repository, checks the explicit
technical-release input surface, and then re-snapshots both roots so a mutation
during the other root's replay cannot slip through.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from urllib.parse import unquote_to_bytes

import freeze as canonical


SCHEMA = 1
REQUIRED_PROJECT_PATHS = (
    "GOAL.md",
    "REUSE.toml",
    "ledger/deferred.json",
    "notes/m2-tierb-prep.md",
    "harness/run.sh",
    "scripts/m0-selfcheck.py",
    "scripts/dashboard.sh",
    "scripts/package-tagged-release.py",
    "scripts/deps/opensubdiv.sh",
    "scripts/finalize-wasm-split.py",
    "patches/blender_web.cmake",
    "patches/platform_wasm.cmake",
    "patches/canonical",
    "patches/PREVIEW_SNAPSHOT.patch",
    "patches/PREVIEW_SNAPSHOT.sha256",
    "patches/series",
    "sandbox/series-replay/verify.py",
    "sandbox/dawn-probe/build.sh",
    "platform_web/ghost/GHOST_ContextWGPUWeb.cc",
    "platform_web/shell/diagnostics-bootstrap.js",
    "platform_web/shell/boot-windowed.js",
    "platform_web/shell/file-bridge.js",
    "platform_web/shell/wgpu-preinit-worker.js",
    "platform_web/shell/windowed.html",
    "platform_web/split/profile-export.js",
    "platform_web/split/single-flight.js",
    "sandbox/m7-product-gate/run.sh",
    "sandbox/m7-product-gate/fallback_contract.py",
    "sandbox/m7-product-gate/verify_m7.py",
    "sandbox/m7-product-gate/fallback_receipt.schema.json",
    "sandbox/m7-product-gate/capture_fallback.py",
    "sandbox/m7-product-gate/verify_files.mjs",
    "sandbox/m7-product-gate/verify_bundle_sources.py",
    "sandbox/m7-usd-prep/verify_browser_usd.mjs",
    "sandbox/m7-usd-prep/make_native_receipt.py",
    "sandbox/m7-io-smoke/export_scene.py",
    "sandbox/m7-io-smoke/roundtrip_scene.py",
    "sandbox/m7-io-smoke/parse_obj.py",
    "sandbox/m7-io-smoke/parse_glb.py",
    "sandbox/m8-staged-deploy/make_staged_bundle.sh",
    "sandbox/m8-staged-deploy/brotli_q11.mjs",
    "sandbox/m8-staged-deploy/stage_pack.py",
    "sandbox/m8-staged-deploy/test_stage_pack.py",
    "sandbox/m8-staged-deploy/stage_provenance.py",
    "sandbox/m8-staged-deploy/prepare_split_inventory.py",
    "sandbox/m8-staged-deploy/public_shell_hardening.py",
    "sandbox/m8-staged-deploy/public_shell_minify.mjs",
    "sandbox/m8-staged-deploy/stage1-loader.js",
    "sandbox/m8-staged-deploy/service-worker.js",
    "sandbox/m8-staged-deploy/service-worker-register.js",
    "sandbox/m8-deploy/_headers",
    "sandbox/m8-staged-deploy/transport_contract.py",
    "sandbox/m8-staged-deploy/serve_measure.py",
    "sandbox/m8-staged-deploy/verify_staged.mjs",
    "sandbox/m8-staged-deploy/verify_public_query_hardening.mjs",
    "sandbox/m8-staged-deploy/verify_update_transition.mjs",
    "sandbox/m8-launch-gate/verify_m8.py",
    "sandbox/m8-launch-gate/bundle_identity.mjs",
    "sandbox/m8-launch-gate/make_staged_receipt.py",
    "sandbox/m8-launch-gate/measure_current.mjs",
    "sandbox/m8-launch-gate/browser_matrix.mjs",
    "sandbox/m8-launch-gate/runtime_evidence.mjs",
    "sandbox/m8-launch-gate/runtime_evidence_selfcheck.mjs",
    "sandbox/m8-launch-gate/audit_compliance.py",
    "sandbox/m8-launch-gate/verify_product_bar.mjs",
    "sandbox/m8-launch-gate/soak_current.mjs",
    "sandbox/m8-launch-gate/test_technical_receipt_contracts.py",
    "sandbox/m8-tagged-release/verify.py",
    "sandbox/final-m0-m6/verify.py",
    "sandbox/final-m0-m6/compose.py",
    "sandbox/final-m0-m6/selfcheck.py",
    "sandbox/final-m0-m6/README.md",
    "sandbox/final-m0-m3/verify.py",
    "sandbox/final-m0-m3/compose.py",
    "sandbox/final-m0-m3/compose_selfcheck.py",
    "sandbox/final-m0-m3/selfcheck.py",
    "sandbox/final-m0-m3/run_m0.py",
    "sandbox/final-m0-m3/reuse_evidence_selfcheck.py",
    "sandbox/final-m0-m3/run_m1.py",
    "sandbox/final-m0-m3/run_m2.py",
    "sandbox/tierb-prep/normalize.sed",
    "sandbox/tierb-prep/wasm-denoise.pl",
    "sandbox/final-m0-m3/run_m2_deps.py",
    "sandbox/final-m0-m3/m2_dependency_inventory.json",
    "sandbox/final-m0-m3/run_m3.py",
    "sandbox/final-m0-m3/gpu_webgpu_tests.txt",
    "sandbox/final-m0-m3/static_shader_identities.txt",
    "oracle/bpy.sh",
    "sandbox/final-m0-m3/runner_selfcheck.py",
    "sandbox/final-m0-m3/strict_final_adapter.py",
    "sandbox/final-m0-m3/strict_final_adapter_selfcheck.py",
    "sandbox/m4-d9-gate/capture_m4.mjs",
    "sandbox/m4-d9-gate/bind_current.py",
    "sandbox/m4-d9-gate/verify_current_binding.py",
    "sandbox/m5-final/verify_m5.py",
    "sandbox/m5-final/runtime-artifacts.mjs",
    "sandbox/gpu-r61/workbench-preview/run_matrix.sh",
    "sandbox/gpu-r61/workbench-preview/drive_workbench_case.mjs",
    "sandbox/gpu-r61/eevee-matrix-preview/run_eevee_matrix.mjs",
    "sandbox/gpu-r61/f12-eevee-acceptance/drive_eevee_f12.mjs",
    "sandbox/gpu-r61/cycles-windowed/drive_cycles_f12.mjs",
    "sandbox/m6-prep/run_wasm_cycles.sh",
    "sandbox/m6-prep/verify_render_closeout.py",
    "sandbox/final-source-freeze/freeze.py",
    "sandbox/final-source-freeze/freeze_release.py",
)

REQUIRED_UPSTREAM_PATHS = (
    "CMakeLists.txt",
    "build_files/cmake/testing.cmake",
    "source/blender/blenlib/CMakeLists.txt",
    "source/blender/blenlib/intern/path_utils.cc",
    "source/blender/blenlib/intern/expr_pylike_eval.cc",
    "source/blender/blenlib/tests/BLI_fileops_test.cc",
    "source/blender/blenlib/tests/BLI_expr_pylike_eval_test.cc",
    "source/blender/bmesh/CMakeLists.txt",
    "scripts/modules/addon_utils.py",
    "locale/languages",
    "intern/cycles/blender/addon/__init__.py",
    "intern/cycles/blender/addon/camera.py",
    "intern/cycles/blender/addon/engine.py",
    "intern/cycles/blender/addon/maketx.py",
    "intern/cycles/blender/addon/operators.py",
    "intern/cycles/blender/addon/osl.py",
    "intern/cycles/blender/addon/presets.py",
    "intern/cycles/blender/addon/properties.py",
    "intern/cycles/blender/addon/ui.py",
    "intern/cycles/blender/addon/version_update.py",
    "intern/ghost/intern/GHOST_ContextWGPU.cc",
    "intern/ghost/intern/GHOST_ContextWGPU.hh",
    "intern/opensubdiv/CMakeLists.txt",
    "intern/opensubdiv/internal/evaluator/eval_output_gpu.h",
    "intern/opensubdiv/internal/evaluator/evaluator_capi.cc",
    "intern/opensubdiv/internal/evaluator/gpu_compute_evaluator.cc",
    "source/blender/gpu/CMakeLists.txt",
    "source/blender/gpu/webgpu/wgpu_context.cc",
    "source/blender/gpu/webgpu/wgpu_context.hh",
    "source/blender/gpu/webgpu/wgpu_framebuffer.cc",
    "source/blender/gpu/webgpu/wgpu_texture.cc",
    "source/blender/gpu/webgpu/wgpu_texture.hh",
    "source/blender/gpu/webgpu/wgpu_shader.cc",
    "source/blender/gpu/webgpu/wgpu_shader.hh",
    "source/blender/gpu/webgpu/wgpu_shader_cache.cc",
    "source/blender/gpu/webgpu/wgpu_shader_compiler.cc",
    "source/blender/gpu/webgpu/wgpu_shader_interface_map.cc",
    "source/blender/gpu/webgpu/wgpu_vertex_buffer.cc",
    "source/blender/gpu/webgpu/wgpu_vertex_buffer.hh",
    "source/blender/gpu/intern/gpu_shader_create_info.cc",
    "source/blender/gpu/intern/gpu_shader_dependency.cc",
    "source/blender/gpu/metal/kernels/gpu_shader_fullscreen_blit_infos.hh",
    "source/blender/gpu/shaders/infos/gpu_shader_test_infos.hh",
    "source/blender/gpu/tests/gpu_testing.hh",
    "source/blender/gpu/tests/framebuffer_test.cc",
    "source/blender/gpu/tests/shaders/gpu_texture_atomic_test.glsl",
    "source/blender/gpu/tests/shaders/CMakeLists.txt",
    "source/blender/gpu/tests/shaders/gpu_framebuffer_subpass_input_test.glsl",
    "source/blender/gpu/tests/shader_test.cc",
    "source/blender/gpu/tests/shader_create_info_test.cc",
    "source/blender/gpu/tests/texture_test.cc",
    "source/blender/draw/CMakeLists.txt",
    "source/blender/draw/intern/DRW_gpu_wrapper.hh",
    "source/blender/draw/intern/draw_debug.cc",
    "source/blender/draw/intern/draw_shader.cc",
    "source/blender/draw/intern/draw_shader.hh",
    "source/blender/draw/intern/shaders/draw_debug_infos.hh",
    "source/blender/draw/intern/shaders/draw_debug_draw_display_vert.glsl",
    "source/blender/draw/intern/shaders/draw_debug_draw_compact_comp.glsl",
    "source/blender/draw/tests/draw_testing.cc",
    "source/blender/draw/tests/draw_testing.hh",
    "source/blender/draw/tests/draw_debug_test.cc",
    "source/blender/draw/intern/draw_cache_impl_curves.cc",
    "source/blender/draw/intern/draw_cache_impl_particles.cc",
    "source/blender/draw/intern/draw_curves.cc",
    "source/blender/draw/intern/draw_curves_defines.hh",
    "source/blender/draw/intern/draw_hair_private.hh",
    "source/blender/draw/intern/shaders/draw_curves_infos.hh",
    "source/blender/draw/intern/shaders/draw_curves_interpolation_comp.glsl",
    "source/blender/draw/intern/shaders/draw_curves_test.glsl",
    "source/blender/draw/tests/draw_curves_test.cc",
    "source/blender/draw/intern/draw_cache_impl_subdivision.cc",
    "source/blender/draw/intern/shaders/subdiv_patch_eval_infos.hh",
    "source/blender/draw/intern/shaders/subdiv_patch_evaluation_comp.glsl",
)

# These are exact generator-owned ledgers/dashboard/runtime captures, not
# executable/source inputs. The source freeze still captures their pre-run
# bytes for reproducibility, but final consumers may accept post-freeze
# regeneration only for this literal set and must independently hash-bind the
# resulting bytes.
VOLATILE_GENERATED_OUTPUTS = (
    "ledger/results/m0.json",
    "ledger/results/m1.json",
    "ledger/results/m2b.json",
    "ledger/results/m3.json",
    "ledger/results/m4.json",
    "ledger/results/m5.json",
    "ledger/results/m6.json",
    "ledger/results/m7.json",
    "ledger/results/m8.json",
    "reports/dashboard.md",
    "sandbox/m8-staged-deploy/artifacts/staged_boot_1280x720.png",
    "sandbox/m8-staged-deploy/artifacts/staged_boot_1280x720.png.license",
)


def manifest_paths(path: Path) -> set[bytes]:
    result: set[bytes] = set()
    for number, line in enumerate(path.read_bytes().splitlines(), 1):
        try:
            row = json.loads(line)
            encoded = row["path"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise canonical.FreezeError(
                f"invalid manifest row {number}: {path}"
            ) from exc
        if not isinstance(encoded, str):
            raise canonical.FreezeError(f"manifest path is not text at row {number}")
        raw = unquote_to_bytes(encoded)
        if raw in result:
            raise canonical.FreezeError(f"duplicate manifest path: {encoded}")
        result.add(raw)
    return result


def require_release_coverage(
    project_manifest: Path, upstream_manifest: Path
) -> dict[str, object]:
    project_paths = manifest_paths(project_manifest)
    missing_project = [
        name for name in REQUIRED_PROJECT_PATHS if os.fsencode(name) not in project_paths
    ]
    if missing_project:
        raise canonical.FreezeError(
            "top-level freeze omits required technical-release inputs: "
            + ", ".join(missing_project)
        )
    upstream_paths = manifest_paths(upstream_manifest)
    missing_upstream = [
        name for name in REQUIRED_UPSTREAM_PATHS if os.fsencode(name) not in upstream_paths
    ]
    if missing_upstream:
        raise canonical.FreezeError(
            "upstream freeze omits required technical-release inputs: "
            + ", ".join(missing_upstream)
        )
    return {
        "policy": "all project+upstream source byte-exact; exact generator-owned outputs independently post-bound",
        "required_paths": list(REQUIRED_PROJECT_PATHS),
        "required_paths_present": len(REQUIRED_PROJECT_PATHS),
        "required_upstream_paths": list(REQUIRED_UPSTREAM_PATHS),
        "required_upstream_paths_present": len(REQUIRED_UPSTREAM_PATHS),
        "volatile_generated_outputs": list(VOLATILE_GENERATED_OUTPUTS),
    }


def require_upstream_separate(project: Path, upstream: Path) -> None:
    try:
        upstream.relative_to(project)
    except ValueError as exc:
        raise canonical.FreezeError("--upstream must be inside --project") from exc
    if upstream != project / "upstream":
        raise canonical.FreezeError("--upstream must be the project's exact upstream/ directory")
    ignored = canonical.run_git(
        project, ["check-ignore", "--quiet", "--", "upstream"], check=False
    )
    if ignored.returncode != 0:
        raise canonical.FreezeError(
            "top-level repository must ignore upstream/ so the two freeze domains cannot overlap"
        )
    tracked = canonical.git_stdout(project, ["ls-files", "-z", "--", "upstream"])
    if tracked:
        raise canonical.FreezeError("top-level repository unexpectedly tracks upstream/")


def resnapshot_matches(source: Path, pin: str, receipt_dir: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="release-freeze-resnapshot-") as name:
        temp = Path(name)
        environment, patch = canonical.make_snapshot(source, pin, temp)
        manifest, entries = canonical.manifest_bytes(source, env=environment)
    expected_patch = (receipt_dir / "canonical-source.patch").read_bytes()
    expected_manifest = (receipt_dir / "live.manifest.jsonl").read_bytes()
    receipt = json.loads((receipt_dir / "receipt.json").read_text(encoding="utf-8"))
    if patch != expected_patch or manifest != expected_manifest:
        raise canonical.FreezeError(
            f"{source} changed after its component freeze completed"
        )
    if entries != receipt.get("live_manifest", {}).get("entries"):
        raise canonical.FreezeError(f"{source} manifest entry count changed")


def paired_resnapshots_match(
    project: Path,
    project_pin: str,
    project_dir: Path,
    upstream: Path,
    upstream_pin: str,
    upstream_dir: Path,
) -> dict[str, object]:
    """Verify both live roots in nested, overlapping final resnapshot passes.

    A single ``project -> upstream`` pass leaves the project unchecked while the
    upstream snapshot is being computed.  The nested ``project -> upstream ->
    upstream -> project`` order closes that window: each root is checked twice,
    and the intervals bounded by its two byte-exact checks overlap.  Publication
    follows this function without another replay or other long-running operation.
    """

    order = (
        ("project", project, project_pin, project_dir),
        ("upstream", upstream, upstream_pin, upstream_dir),
        ("upstream", upstream, upstream_pin, upstream_dir),
        ("project", project, project_pin, project_dir),
    )
    for _name, source, pin, receipt_dir in order:
        resnapshot_matches(source, pin, receipt_dir)
    return {
        "policy": "nested overlapping live resnapshots immediately before publication",
        "order": [name for name, _source, _pin, _receipt_dir in order],
        "checks_per_root": 2,
    }


def component_identity(path: Path) -> dict[str, object]:
    receipt_path = path / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("verdict") != "PASS":
        raise canonical.FreezeError(f"component receipt is not PASS: {receipt_path}")
    return {
        "directory": path.name,
        "receipt_sha256": canonical.sha256_file(receipt_path),
        "patch": receipt["patch"],
        "live_manifest": receipt["live_manifest"],
    }


def freeze_release(
    project: Path,
    project_pin: str,
    upstream: Path,
    upstream_pin: str,
    upstream_pin_file: Path,
    output_dir: Path,
) -> dict[str, object]:
    project = project.resolve(strict=True)
    upstream = upstream.resolve(strict=True)
    output_dir = output_dir.absolute()
    require_upstream_separate(project, upstream)
    for source in (project, upstream):
        try:
            output_dir.resolve().relative_to(source)
        except ValueError:
            pass
        else:
            raise canonical.FreezeError("--output-dir must be outside both source repositories")
    if output_dir.exists() or output_dir.is_symlink():
        raise canonical.FreezeError(f"refusing to overwrite existing output path: {output_dir}")
    if not output_dir.parent.is_dir():
        raise canonical.FreezeError(f"output parent does not exist: {output_dir.parent}")

    # Validate both roots before reserving output. Each component repeats these
    # checks around its own replay.
    canonical.require_exact_pin(project, project_pin, None)
    canonical.require_pristine_real_index(project, project_pin)
    canonical.require_exact_pin(upstream, upstream_pin, upstream_pin_file)
    canonical.require_pristine_real_index(upstream, upstream_pin)

    os.mkdir(output_dir, 0o755)
    incomplete = output_dir / "INCOMPLETE"
    canonical.write_exclusive(incomplete, b"complete technical source freeze did not complete\n")
    try:
        project_dir = output_dir / "project"
        upstream_dir = output_dir / "upstream"
        canonical.freeze(project, project_pin, project_dir)
        canonical.freeze(upstream, upstream_pin, upstream_dir, upstream_pin_file)
        coverage = require_release_coverage(
            project_dir / "live.manifest.jsonl", upstream_dir / "live.manifest.jsonl"
        )

        canonical.require_exact_pin(project, project_pin, None)
        canonical.require_pristine_real_index(project, project_pin)
        canonical.require_exact_pin(upstream, upstream_pin, upstream_pin_file)
        canonical.require_pristine_real_index(upstream, upstream_pin)
        # Close the cross-root race with nested double passes as the final live
        # source operation before receipt publication. The second project check
        # detects a mutation during either upstream check; the second upstream
        # check detects a mutation during the first project check.
        paired_resnapshot = paired_resnapshots_match(
            project,
            project_pin,
            project_dir,
            upstream,
            upstream_pin,
            upstream_dir,
        )

        receipt: dict[str, object] = {
            "schema": SCHEMA,
            "verdict": "PASS",
            "created_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
            "project": component_identity(project_dir),
            "upstream": component_identity(upstream_dir),
            "coverage": coverage,
            "final_paired_resnapshot": paired_resnapshot,
            "checks": {
                "repositories_disjoint": True,
                "project_component_pass": True,
                "upstream_component_pass": True,
                "technical_release_inputs_present": True,
                "cross_root_resnapshot_byte_exact": True,
                "final_overlapping_double_resnapshot": True,
                "both_heads_and_real_indexes_stable": True,
                "outputs_created_without_overwrite": True,
            },
        }
        receipt_bytes = json.dumps(receipt, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        canonical.write_exclusive(output_dir / "receipt.json", receipt_bytes)
        incomplete.unlink()
        return receipt
    except BaseException:
        shutil.rmtree(output_dir)
        raise


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--project-pin", required=True)
    parser.add_argument("--upstream", required=True, type=Path)
    parser.add_argument("--upstream-pin", required=True)
    parser.add_argument("--upstream-pin-file", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        receipt = freeze_release(
            args.project,
            args.project_pin,
            args.upstream,
            args.upstream_pin,
            args.upstream_pin_file,
            args.output_dir,
        )
    except (canonical.FreezeError, OSError) as exc:
        print(f"release-source-freeze: FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
