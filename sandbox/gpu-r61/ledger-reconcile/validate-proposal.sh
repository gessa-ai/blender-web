#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Blender Web contributors
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
proposal="$repo_root/sandbox/gpu-r61/ledger-reconcile/accepted-baseline-reconcile.patch"

test -f "$proposal"

expected_paths="$(printf '%s\n' fix_plan.md ledger/progress.txt patches/series | sort)"
actual_paths="$(git apply --numstat "$proposal" | awk '{print $3}' | sort)"
if [[ "$actual_paths" != "$expected_paths" ]]; then
  printf 'unexpected proposal paths:\n%s\n' "$actual_paths" >&2
  exit 1
fi

git -C "$repo_root" apply --check --whitespace=error-all "$proposal"

git -C "$repo_root" cat-file -e 'dc56eef^{commit}'
git -C "$repo_root" cat-file -e '7090add^{commit}'

printf '%s  %s\n' \
  b4fdb24cb2c34740d2e60cff5dc9fcf33e8ac94d784f85f106ba2ae706f1d032 \
  "$repo_root/patches/0144-gpu-eevee-storage-format-and-final-mip.patch" | shasum -a 256 -c -
printf '%s  %s\n' \
  986f95b9d3645c4fffc1cfc65e1d0b7fcce09ca7ef7605b991e2e54ba4613899 \
  "$repo_root/patches/0146-gpu-eevee-shadow-tag-readonly.patch" | shasum -a 256 -c -

rg -Fq 'GPUWebGPUTest: 164 PASS / 7 FAIL / 2 CRASH / 173 tests' \
  "$repo_root/sandbox/gpu-eevee-phase-aprime/0144-final-receipt.txt"
rg -Fq 'Static shaders: 970 / 987' \
  "$repo_root/sandbox/gpu-eevee-phase-aprime/0144-final-receipt.txt"
rg -Fq 'GPUWebGPUTest: 164 PASS / 7 FAIL / 2 CRASH / 173 tests' \
  "$repo_root/sandbox/gpu-eevee-phase-b0/0146-final-receipt.txt"
rg -Fq 'Static shaders: 971 / 987' \
  "$repo_root/sandbox/gpu-eevee-phase-b0/0146-final-receipt.txt"

if rg -q '(^|/)(source|harness|reports|ledger/results)/|ledger/deferred\.json|0145-.*\.patch|0147-.*\.patch' \
  "$proposal"; then
  echo 'proposal contains an excluded path or nonexistent patch entry' >&2
  exit 1
fi

if rg -q '973 / 989|973/989|GPU_readback\.hh|gpu-eevee-phase-b1' "$proposal"; then
  echo 'proposal contains excluded B1/L-B WIP evidence' >&2
  exit 1
fi

echo 'PASS: proposal applies cleanly and is limited to accepted 0144/0146 bookkeeping.'

