# Canonical final source freeze

The technical release uses `freeze_release.py`, because its source spans two
independent Git roots: the top-level project repository and its deliberately
ignored, separately pinned `upstream/` repository. A one-root receipt is not a
complete blender-web release freeze.

`freeze.py` creates one complete Git patch from an exact pristine commit to the
live source worktree, then proves that patch in an isolated clone. It is intended
to run once the project source has stopped changing. It does not read or rewrite
the historical `patches/series` files.

The source worktree is expected to contain the port changes. Its **real index**
must still exactly equal the pinned commit, its `HEAD` must be the full expected
object ID, no repository operation may be in progress, and initialized
submodules must be clean. Non-ignored untracked files are captured as additions.
Paths ignored by the repository are deliberately excluded and their sorted,
NUL-delimited path-list digest is recorded in the receipt.

The tool redirects both its synthetic index and new Git objects into a temporary
directory. It creates the requested output directory with no-overwrite `mkdir`,
writes an `INCOMPLETE` sentinel while working, and removes the entire newly-owned
directory on an ordinary failure. A crash may leave the sentinel for inspection;
the next invocation refuses to overwrite that directory.

## Final technical-release invocation

Run this only after all top-level shell, assembler, harness, dashboard, and
verifier changes have stopped, and after the upstream M7 relink/source changes
have stopped. The output must be outside both repositories. `--project-pin` is
the exact top-level `HEAD`; the upstream pin remains the Blender 5.2 pin.

```sh
python3 sandbox/final-source-freeze/freeze_release.py \
  --project /Users/paws/blender-web \
  --project-pin "$(git -C /Users/paws/blender-web rev-parse HEAD)" \
  --upstream /Users/paws/blender-web/upstream \
  --upstream-pin fbe6228777e7d9afefcd61a413844e790ae75db7 \
  --upstream-pin-file /Users/paws/blender-web/oracle/PIN \
  --output-dir /Users/paws/blender-web-final-source-freeze
```

The composite directory contains `project/` and `upstream/` component freezes
plus a top-level `receipt.json` binding both component receipts, patches, and
manifests. It asserts the complete technical-release input surface (shell,
split finalizer, staged-bundle assembler, service worker, M7/M8 verifiers,
harness, and dashboard), then performs nested final live resnapshots in the order
project → upstream → upstream → project. Each root is therefore checked twice,
with overlapping verification intervals immediately before the composite receipt
is published; a persistent mutation in the former one-pass cross-root window is
rejected.

`freeze.py` remains the canonical one-repository primitive. Its direct upstream
invocation is useful for diagnosis, but is not the complete release receipt.

The upstream diagnostic's `receipt.json` is retained at
`sandbox/series-replay/canonical-freeze-receipt.json` only when its generated
`canonical-source.patch` is byte-identical to `patches/PREVIEW_SNAPSHOT.patch`.
Those two files and `patches/PREVIEW_SNAPSHOT.sha256` are one accepted update:
`sandbox/series-replay/verify.py` rejects a stale receipt, snapshot/pin mismatch,
malformed exclusion proof, failed freezer check, or unequal live/replay manifest
before publishing `CANONICAL_REPLAY_PASS`. Never present the fixed-path JSON as current evidence
without that verdict. Run `sandbox/series-replay/selfcheck.py` to exercise the
fail-closed receipt mutations without reading the Blender source tree.

## One-repository diagnostic invocation

Use a new receipt directory outside `upstream/`. The full commit ID is required;
the first token in `oracle/PIN` must be its prefix.

```sh
python3 sandbox/final-source-freeze/freeze.py \
  --source /Users/paws/blender-web/upstream \
  --expected-pin fbe6228777e7d9afefcd61a413844e790ae75db7 \
  --pin-file /Users/paws/blender-web/oracle/PIN \
  --output-dir /Users/paws/blender-web/sandbox/final-source-freeze/final-receipt
```

The output directory contains only:

- `canonical-source.patch`: `git diff --cached --binary --full-index` from the
  pin, including additions, deletions, executable/symlink/gitlink modes, and Git
  binary patches.
- `live.manifest.jsonl`: every path in the synthetic live index, sorted by raw
  path bytes. Each line has reversible percent-encoded `path`, Git `mode`, exact
  blob `size`, and content `sha256`. A gitlink hashes its target object-ID bytes.
- `replay.manifest.jsonl`: independently generated after `git apply --index` in
  a pristine isolated clone; it must be byte-identical to the live manifest.
- `receipt.json`: exact patch/manifest hashes and all fail-closed checks.

The replay also regenerates the complete patch and requires it to be
byte-identical to the original. After replay, the tool takes a second synthetic
snapshot and requires its patch and manifest to remain byte-identical; it also
rechecks the pin file, real index, repository state, initialized submodules, and
ignored-path set. Existing output paths, short or mismatched pins,
staged changes, unmerged entries, sparse checkouts, dirty initialized submodules,
and dirty replay clones are rejected.

Replay sets `GIT_LFS_SKIP_SMUDGE=1`, so an LFS-enabled source tree is checked at
its canonical Git-blob layer without network downloads or expanded payloads.

## Hermetic self-check

The self-check creates a tiny temporary repository and never reads the Blender
tree. Its fixture covers text modification, deletion, an executable mode change,
a new executable whose path contains a space, a symlink, and binary content. It
also proves rejection of overwrite, an unexpected pin, a dirty real index, and a
deterministically injected mutation after the first project pass of the final
cross-root resnapshot.

```sh
python3 sandbox/final-source-freeze/selfcheck.py
python3 sandbox/final-source-freeze/release_selfcheck.py
```
