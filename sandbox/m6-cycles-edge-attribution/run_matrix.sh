#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

LABEL="${1:-}"
if [[ -z "$LABEL" || ! "$LABEL" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
  echo "usage: $0 <unique-label> [variant ...]" >&2
  exit 2
fi
shift

NODE="${NODE:-$ROOT/tools/emsdk/node/22.16.0_64bit/bin/node}"
WASM_BLENDER="${WASM_BLENDER:-$ROOT/build-wasm-cycles/bin/blender.js}"
DRIVER="$ROOT/sandbox/m6-cycles-edge-attribution/render_variant.py"
ADDON_PARENT="$ROOT/sandbox/m6-prep/wasm-first-render/addon"
RUN_ROOT="$ROOT/sandbox/m6-cycles-edge-attribution/runs/$LABEL"

if [[ "$#" -gt 0 ]]; then
  variants=("$@")
else
  variants=(
    baseline
    film_transparent
    alpha_one
    samples_1
    samples_100
    sampling_tabulated_sobol
    sampling_blue_noise_pure
    addon_do_versions
    pixel_jitter
    filter_box
    shader_diffuse
    geometry_flat
    geometry_no_subsurf
    geometry_plane_only
    geometry_sphere_only
  )
fi

scenes=(principled_bsdf_default principled_bsdf_emission_alpha)

[[ -x "$NODE" && -f "$WASM_BLENDER" && -f "${WASM_BLENDER%.js}.wasm" ]] || {
  echo "M6_EDGE_RUN_FAIL missing Wasm runtime or product" >&2
  exit 2
}
[[ -f "$DRIVER" && -d "$ADDON_PARENT" ]] || {
  echo "M6_EDGE_RUN_FAIL missing driver or staged Cycles addon" >&2
  exit 2
}
if [[ -e "$RUN_ROOT" ]]; then
  echo "M6_EDGE_RUN_FAIL refusing to overwrite $RUN_ROOT" >&2
  exit 3
fi
mkdir -p "$RUN_ROOT/native" "$RUN_ROOT/wasm" "$RUN_ROOT/logs/native" "$RUN_ROOT/logs/wasm"

sha256sum \
  "$DRIVER" \
  "$ROOT/sandbox/m6-cycles-edge-attribution/run_matrix.sh" \
  "$ROOT/sandbox/m6-cycles-edge-attribution/analyze_matrix.py" \
  "$ROOT/sandbox/m6-cycles-edge-attribution/verify_attribution.py" \
  "$ROOT/upstream/tests/files/render/principled_bsdf/principled_bsdf_default.blend" \
  "$ROOT/upstream/tests/files/render/principled_bsdf/principled_bsdf_emission_alpha.blend" \
  "$ROOT/sandbox/m6-prep/goldens/cycles/principled_bsdf/principled_bsdf_default.png" \
  "$ROOT/sandbox/m6-prep/goldens/cycles/principled_bsdf/principled_bsdf_emission_alpha.png" \
  > "$RUN_ROOT/source-inputs.sha256"

export BLENDER_SYSTEM_RESOURCES="$ROOT/upstream"
export BLENDER_SYSTEM_PYTHON="$ROOT/lib/wasm"
export BLENDER_SYSTEM_DATAFILES="$ROOT/upstream/release/datafiles"
export M6_CYCLES_ADDON_PARENT="$ADDON_PARENT"

sha256sum "$WASM_BLENDER" "${WASM_BLENDER%.js}.wasm" > "$RUN_ROOT/wasm-product.sha256"
printf 'scene\tvariant\tnative_status\twasm_status\n' > "$RUN_ROOT/render-status.tsv"

for scene in "${scenes[@]}"; do
  blend="$ROOT/upstream/tests/files/render/principled_bsdf/$scene.blend"
  [[ -s "$blend" ]] || { echo "M6_EDGE_RUN_FAIL missing input $blend" >&2; exit 2; }
  for variant in "${variants[@]}"; do
    native_base="$RUN_ROOT/native/${scene}__${variant}"
    wasm_base="$RUN_ROOT/wasm/${scene}__${variant}"
    native_log="$RUN_ROOT/logs/native/${scene}__${variant}.log"
    wasm_log="$RUN_ROOT/logs/wasm/${scene}__${variant}.log"

    set +e
    "$ROOT/scripts/oracle-container.sh" blender "$blend" --debug-exit-on-error --python "$DRIVER" -- \
      --variant "$variant" --out "$native_base" > "$native_log" 2>&1
    native_status=$?
    "$NODE" "$WASM_BLENDER" --background --factory-startup --debug-exit-on-error "$blend" --python "$DRIVER" -- \
      --variant "$variant" --out "$wasm_base" > "$wasm_log" 2>&1
    wasm_status=$?
    set -e

    printf '%s\t%s\t%s\t%s\n' "$scene" "$variant" "$native_status" "$wasm_status" \
      >> "$RUN_ROOT/render-status.tsv"
    if [[ "$native_status" -ne 0 || "$wasm_status" -ne 0 || \
          "$(grep -c 'Traceback (most recent call last)' "$native_log" || true)" -ne 0 || \
          "$(grep -c 'Traceback (most recent call last)' "$wasm_log" || true)" -ne 0 || \
          ! -s "$native_base.exr" || ! -s "$native_base.png" || \
          ! -s "$wasm_base.exr" || ! -s "$wasm_base.png" ]]; then
      native_reason="$(grep -aoE 'M6_EDGE_RENDER_OK|Traceback|ERROR|Error:|Aborted\(' "$native_log" | tail -1 || true)"
      wasm_reason="$(grep -aoE 'M6_EDGE_RENDER_OK|Traceback|ERROR|Error:|Aborted\(' "$wasm_log" | tail -1 || true)"
      echo "M6_EDGE_RENDER_FAIL scene=$scene variant=$variant native=$native_status:$native_reason wasm=$wasm_status:$wasm_reason" >&2
      exit 1
    fi
    echo "M6_EDGE_PAIR_OK scene=$scene variant=$variant"
  done
done

sha256sum -c "$RUN_ROOT/wasm-product.sha256" >/dev/null
sha256sum -c "$RUN_ROOT/source-inputs.sha256" >/dev/null
echo "M6_EDGE_MATRIX_OK label=$LABEL pairs=$((${#scenes[@]} * ${#variants[@]})) artifact_stable=1"
