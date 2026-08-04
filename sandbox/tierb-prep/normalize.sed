# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: CC0-1.0
#
# Output normalization for tier-(b) oracle baselines.
# Applied to combined stdout+stderr so native-oracle output can be compared
# (normalized-diff) against the wasm build's output. Each rule masks a source
# of legitimate run-to-run / platform variance that is NOT a parity signal.

# Build banner: hash is pinned but build DATE/TIME differ per build.
s/^\(Blender [0-9][0-9.]* LTS\) (hash [0-9a-f]* built [^)]*)/\1 (hash <PIN> built <DATE>)/

# Python unittest summary timing (wall time varies).
s/^Ran \([0-9][0-9]*\) tests\? in [0-9][0-9.]*s/Ran \1 tests in <T>s/

# unittest per-test timing occasionally embedded (e.g. "... ok (0.001s)")
s/ (\([0-9][0-9.]*\)s)$/ (<T>s)/

# Heap/pointer addresses (guardedalloc reports, repr of objects, etc.)
s/0x[0-9a-fA-F]\{5,\}/0xADDR/g

# Temp dirs: macOS oracle uses /var/folders/..., wasm uses /tmp/...; also our
# scratch OUT dir. Collapse all to <TMP>.
s#/private/var/folders/[^ '\"]*#<TMP>#g
s#/var/folders/[^ '\"]*#<TMP>#g
s#/tmp/[^ '\"]*#<TMP>#g

# Repo-absolute paths -> <REPO> (testdir/output-dir echoes, tracebacks).
s#/Users/paws/blender-web#<REPO>#g

# Elapsed-time lines some scripts print ("finished in 1.23 sec").
s/finished in [0-9][0-9.]* *\(sec\|s\|ms\)/finished in <T>/g
