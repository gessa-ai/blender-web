# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: CC0-1.0
#
# WASM banner rule, applied (after normalize.sed + wasm-denoise.pl) to BOTH the
# wasm output and the oracle baseline for the secondary diff. The wasm banner is
# "Blender 5.2.0 LTS" (no "(hash … built …)"); collapse both sides to a bare
# banner so it is not a spurious diff. Benign startup-noise removal lives in
# wasm-denoise.pl (BSD-sed can't do the multi-line block deletes portably).
s/^Blender [0-9][0-9.]* LTS.*/Blender <VER> LTS/
