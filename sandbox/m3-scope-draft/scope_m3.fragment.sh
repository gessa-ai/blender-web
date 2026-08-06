# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: CC0-1.0
#
# DRAFT run.sh fragment for the M3 (WebGPU backend, native Dawn) gate.
# ------------------------------------------------------------------------------
# This is the exact block the driver pastes into harness/run.sh, between
# scope_m2b() and the "scope runner" section, mirroring the m0/m1/m2b style
# (record NAME PASS DETAIL; helpers `record` supplied by the run.sh runner).
# The driver also adds "m3" to SCOPES_REGISTERED (see INSTALL.md).
#
# It is written to run UNCHANGED both (a) installed in run.sh and (b) standalone
# via sandbox/m3-scope-draft/dryrun.sh — the only external contracts are `record`
# (runner-supplied) and a repo-root CWD (run.sh cd's to ROOT; dryrun.sh does the
# same). The native test binary is parameterized via $M3_TEST_BIN (default is the
# real gate build), so the driver can validate against an alternate build.
#
# --------------------------------------------------------------- scope: m3
# M3: the WebGPU (native Dawn) GPU-backend gate. Runs Blender's own GPUWebGPUTest
# suite against build-native-gpu (native Dawn/Metal) and reconciles every result
# to the M3 census (notes/gpu-gate-census.md), the deferral registry
# (ledger/deferred.json), and the blacklist doc (notes/gpu-gate-blacklist.md).
#
# EXIT-CODE is the per-test gate signal, exactly as m1/m2b use it: the census
# runs each GPUWebGPUTest one-per-process (crash isolation — the imageAtomic /
# vertex-RW crashers segfault on a null module and must not poison siblings), so
# rc 0 = PASS, rc>128 = CRASH (signal), any other nonzero = FAIL. Counts come
# from the process exit code, never from scraped multi-line stdout.
#
# Expected state at this pin (patches through 0091, census round 15+):
#   - GPUWebGPUTest: 148 PASS / 8 FAIL / 2 CRASH (158 tests). Every non-PASS maps
#     by test name to a registered deferral id or a documented blacklist group.
#   - static_shaders: >= 956 / 973 internal shaders compile (MINIMUM — a
#     concurrent gpu round that fixes more keeps this green); every remaining
#     non-compile buckets by error signature into a registered deferral class
#     (storage-texture-atomics, vertex-stage-rw-storage) or a documented blacklist
#     group (subdiv runtime-generated, fullscreen_blit Metal-only).
scope_m3() {
  local BIN="${M3_TEST_BIN:-build-native-gpu/bin/tests/blender_test}"

  # --- preflight: the native gate binary must exist + list its suite. A missing
  #     or busy/relinking binary FAILs with the rebuild recipe (a rebuild is a
  #     worker action, not a harness side effect). Per notes: the build-native-gpu
  #     blender_test is NOT relinked by the concurrent gpu round (only rebuilt
  #     libs); if it is mid-rebuild the list is empty -> retry after ~3 min.
  if [ ! -x "$BIN" ]; then
    record gpu_binary 0 "native gate binary missing ($BIN); rebuild: cmake --build build-native-gpu --target blender_test"
    return
  fi
  local LIST NTESTS
  LIST="$("$BIN" --gtest_list_tests --gtest_filter='GPUWebGPUTest.*' 2>/dev/null | grep -E '^  ' | sed 's/^  *//')"
  NTESTS="$(printf '%s\n' "$LIST" | grep -c .)"
  if [ "$NTESTS" -lt 1 ]; then
    record gpu_binary 0 "$BIN listed 0 GPUWebGPUTest tests (busy/relinking? retry after ~3 min per notes/harness-issues.md)"
    return
  fi
  record gpu_binary 1 "$BIN — $NTESTS GPUWebGPUTest tests enumerated"

  # --- patches-series consistency (same invariant as scope_m1's patches_series:
  #     every patches/0*.patch forward-applies clean on pristine, reverse-applies
  #     clean when applied, or is an in-development lane target). Reused verbatim
  #     so the M3 gate re-asserts the patch tree the gpu backend rides on.
  local P BAD="" STATE=""
  for P in patches/0*.patch; do
    if git -C upstream apply --check "../$P" >/dev/null 2>&1; then
      STATE="$STATE ${P##*/}:clean"
    elif git -C upstream apply --check --reverse "../$P" >/dev/null 2>&1; then
      STATE="$STATE ${P##*/}:applied"
    else
      local PFILES MODOK=1 F
      PFILES="$(grep -E '^\+\+\+ b/' "$P" | sed 's|^+++ b/||' | sort -u)"
      for F in $PFILES; do
        git -C upstream status --porcelain -- "$F" 2>/dev/null | grep -q . || { MODOK=0; break; }
      done
      if [ "$MODOK" = 1 ] && [ -n "$PFILES" ]; then
        STATE="$STATE ${P##*/}:in-development"
      else
        BAD="$BAD ${P##*/}"
      fi
    fi
  done
  if [ -z "$BAD" ]; then
    record patches_series 1 "all patches clean-or-applied:$STATE"
  else
    record patches_series 0 "patches neither apply nor reverse-apply (conflict):$BAD"
  fi

  # --- the M3 census expectation: test name -> class. Class is either a
  #     ledger/deferred.json id (deferral:<id>) or a notes/gpu-gate-blacklist.md
  #     group (blacklist:<group>). static_shaders is the aggregate compile test —
  #     it is expected-FAIL as a test; its 973-shader breakdown is validated by
  #     the static_shaders check below, so it maps to the aggregate sentinel.
  #     Source of truth: notes/gpu-gate-census.md §"The 10 non-PASS, characterized".
  local -A EXPECT_NONPASS=(
    [static_shaders]="aggregate:static_shaders-check"
    [buffer_texture]="blacklist:gpu_buffer_texture"
    [shader_sampler_argument_buffer_binding]="blacklist:shader_sampler_argument_buffer_binding"
    [framebuffer_subpass_input]="deferral:subpass-input-attachment"
    [framebuffer_subpass_input_clearops]="deferral:subpass-input-attachment"
    [texture_roundtrip__GPU_DATA_FLOAT__GPU_DEPTH_COMPONENT32F]="deferral:depth-aspect-buffer-upload"
    [texture_roundtrip__GPU_DATA_FLOAT__GPU_DEPTH32F_STENCIL8]="deferral:depth-aspect-buffer-upload"
    [vertex_buffer_fetch_mode__GPU_COMP_I10__GPU_FETCH_INT_TO_FLOAT_UNIT]="deferral:gpu-comp-i10-vertex-format"
    [shader_texture_atomic]="deferral:storage-texture-atomics"
    [specialization_constants_graphic]="deferral:vertex-stage-rw-storage"
  )

  # --- run the census: each test one-per-process (crash isolation). ~35 s. -------
  local npass=0 nfail=0 ncrash=0
  local newfail="" undefer=""              # regressions / un-defer candidates
  local -A SEEN=()
  local t rc verdict
  while IFS= read -r t; do
    [ -z "$t" ] && continue
    # Run each test in an inner `bash -c` whose OWN stderr is discarded: the 2
    # expected crashers segfault (rc 139) and it is the inner shell that would
    # print the "Segmentation fault" job-control diagnostic — swallowed here.
    # The inner shell then exit()s 139 normally, so this shell sees a clean
    # non-signal exit and prints nothing. rc is still captured and classified.
    bash -c '"$1" --gtest_filter="GPUWebGPUTest.$2" >/dev/null 2>&1' _ "$BIN" "$t" 2>/dev/null; rc=$?
    if   [ "$rc" = 0 ];    then verdict=PASS;  npass=$((npass+1))
    elif [ "$rc" -gt 128 ]; then verdict=CRASH; ncrash=$((ncrash+1))
    else                        verdict=FAIL;  nfail=$((nfail+1)); fi

    if [ -n "${EXPECT_NONPASS[$t]:-}" ]; then
      SEEN[$t]=1
      # a deferred/blacklisted test that now PASSES => un-defer candidate (honest:
      # never a silent green — mirrors scope_m2b deferral_consistency).
      [ "$verdict" = PASS ] && undefer="$undefer $t(${EXPECT_NONPASS[$t]})"
    else
      # any test NOT in the expected non-pass map must PASS; else NEW failure/regression.
      [ "$verdict" != PASS ] && newfail="$newfail $t($verdict)"
    fi
  done < <(printf '%s\n' "$LIST")

  # any expected non-pass test that vanished from the suite = disappeared coverage.
  local missing="" k
  for k in "${!EXPECT_NONPASS[@]}"; do
    [ -n "${SEEN[$k]:-}" ] || missing="$missing $k"
  done

  # --- CHECK: census green — 148 PASS floor, zero new failures, zero un-defers,
  #     no vanished expectation. pass>=148 directly encodes "every census-PASS
  #     still passes"; newfail/undefer/missing keep the map honest.
  local cen_ok=1 cen_detail=""
  [ "$npass" -lt 148 ] && { cen_ok=0; cen_detail="$cen_detail pass=$npass<148(census-PASS regressed/removed);"; }
  [ -n "$newfail" ] && { cen_ok=0; cen_detail="$cen_detail NEW-failure(unmapped):$newfail;"; }
  [ -n "$undefer" ] && { cen_ok=0; cen_detail="$cen_detail UN-DEFER-candidate(deferred test now PASSES):$undefer;"; }
  [ -n "$missing" ] && { cen_ok=0; cen_detail="$cen_detail vanished-expectation:$missing(re-census + update map);"; }
  if [ "$cen_ok" = 1 ]; then
    record gpu_suite_census 1 "$npass PASS / $nfail FAIL / $ncrash CRASH ($NTESTS tests); all non-PASS map to a registered deferral/blacklist"
  else
    record gpu_suite_census 0 "${cen_detail# } [$npass PASS / $nfail FAIL / $ncrash CRASH / $NTESTS tests]"
  fi

  # --- static_shaders: the aggregate compile test. Parse bucket-style (model:
  #     scope_m2b deferral_consistency). "N / 973 passed" is a MINIMUM on N; every
  #     'compile failed' shader buckets by error signature into a registered class.
  local SS; SS="$("$BIN" --gtest_filter='GPUWebGPUTest.static_shaders' 2>&1)"
  local SUM PASSED TOTAL
  SUM="$(printf '%s\n' "$SS" | grep -m1 'Shader Test compilation result:')"
  PASSED="$(printf '%s' "$SUM" | grep -oE '[0-9]+ / [0-9]+' | head -1 | awk '{print $1}')"
  TOTAL="$(printf '%s' "$SUM" | grep -oE '[0-9]+ / [0-9]+' | head -1 | awk '{print $3}')"
  # bucket every failing shader by error signature.
  local b_atomic=0 b_vertrw=0 b_subdiv=0 b_blit=0 b_unmapped="" line
  while IFS= read -r line; do
    case "$line" in *"compile failed:"*) : ;; *) continue ;; esac
    if   printf '%s' "$line" | grep -q 'OpImageTexelPointer'; then b_atomic=$((b_atomic+1))
    elif printf '%s' "$line" | grep -q 'cannot be used by vertex pipeline stage'; then b_vertrw=$((b_vertrw+1))
    elif printf '%s' "$line" | grep -qE "OsdPatchParamIsRegular|'subdiv_patch_evaluation"; then b_subdiv=$((b_subdiv+1))
    elif printf '%s' "$line" | grep -qE "'fullscreen_blit'|'imageTexture' : undeclared"; then b_blit=$((b_blit+1))
    else b_unmapped="$b_unmapped [$(printf '%s' "$line" | grep -oE "'[^']+'" | head -1)]"
    fi
  done < <(printf '%s\n' "$SS")

  local ss_ok=1 ss_detail=""
  if [ -z "$PASSED" ] || [ -z "$TOTAL" ]; then
    ss_ok=0; ss_detail="could not parse 'Shader Test compilation result:' line"
  else
    [ "$TOTAL" != 973 ] && { ss_ok=0; ss_detail="$ss_detail total=$TOTAL!=973(shader-library size changed);"; }
    [ "$PASSED" -lt 956 ] && { ss_ok=0; ss_detail="$ss_detail passed=$PASSED<956(compile regression);"; }
    [ -n "$b_unmapped" ] && { ss_ok=0; ss_detail="$ss_detail NEW-non-compile(unmapped):$b_unmapped;"; }
  fi
  if [ "$ss_ok" = 1 ]; then
    record static_shaders 1 "$PASSED/$TOTAL compile (>=956 min); non-compiles bucketed: imageAtomic=$b_atomic vertex-rw=$b_vertrw subdiv=$b_subdiv fullscreen_blit=$b_blit (all registered)"
  else
    record static_shaders 0 "${ss_detail# } [$PASSED/$TOTAL; buckets atomic=$b_atomic vertrw=$b_vertrw subdiv=$b_subdiv blit=$b_blit]"
  fi

  # --- deferral_consistency: the honesty cross-check (mirrors scope_m2b). Every
  #     deferral id the census/static rely on must exist in ledger/deferred.json;
  #     every blacklist group must be documented in notes/gpu-gate-blacklist.md.
  #     A missing id/token = undocumented deferral (add it before the gate goes
  #     green); no un-defer/new-failure is re-derived here (owned by the checks
  #     above) — this check owns the ledger↔gate mapping.
  local DEF_IDS BL_DOC=notes/gpu-gate-blacklist.md dc_ok=1 dc_detail=""
  DEF_IDS="$(python3 -c "import json;print(' '.join(e['id'] for e in json.load(open('ledger/deferred.json'))['deferred']))" 2>/dev/null)"
  in_set() { case " $2 " in *" $1 "*) return 0;; *) return 1;; esac; }
  local NEED_DEFERRALS="storage-texture-atomics vertex-stage-rw-storage depth-aspect-buffer-upload gpu-comp-i10-vertex-format subpass-input-attachment"
  local NEED_BLTOKENS="gpu_buffer_texture shader_sampler_argument_buffer_binding subdiv_patch_evaluation fullscreen_blit"
  local id
  for id in $NEED_DEFERRALS; do
    in_set "$id" "$DEF_IDS" || { dc_ok=0; dc_detail="$dc_detail missing-deferral:$id(add to ledger/deferred.json);"; }
  done
  local tok
  for tok in $NEED_BLTOKENS; do
    grep -q "$tok" "$BL_DOC" 2>/dev/null || { dc_ok=0; dc_detail="$dc_detail undocumented-blacklist:$tok(add to $BL_DOC);"; }
  done
  if [ "$dc_ok" = 1 ]; then
    record deferral_consistency 1 "5 M3-gate deferrals present in deferred.json; 4 blacklist groups documented in $BL_DOC"
  else
    record deferral_consistency 0 "${dc_detail# }"
  fi
}
