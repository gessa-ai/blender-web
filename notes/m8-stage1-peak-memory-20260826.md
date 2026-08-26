<!-- SPDX-FileCopyrightText: 2026 blender-web contributors -->
<!-- SPDX-License-Identifier: CC0-1.0 -->

# M8 Stage-1 peak-memory bound — 2026-08-26

## Outcome

Commit `39b40d7` removes the public Stage-1 loader's payload-sized JavaScript allocation. The
current deferred payload is 152,362,255 bytes across 2,963 files, while its largest file is
11,425,316 bytes. The loader now accepts only manifest files at or below 16 MiB, accepts only
stream chunks at or below 16 MiB, and holds at most one file buffer plus the current response
chunk. Its explicit loader-owned transient ceiling is therefore 32 MiB rather than one complete
payload plus the copy being installed.

Each completed file is written to a generation-scoped `/tmp/.bw-stage1-*` WasmFS entry while the
response streams. No target path is published until the response has ended at exactly the
manifest byte count. Publication then uses `FS.rename`, preserving the already-installed WasmFS
bytes instead of copying them again. Interrupted, short, long, oversized-file, oversized-chunk,
and oversized non-streaming-fallback attempts remove their temporary entries and remain bounded
by the existing three-attempt recovery contract.

The 32 MiB figure covers loader-owned JavaScript response/file views, not Blender's total memory:
the completed 152,362,255-byte asset set necessarily remains resident in WasmFS. The M8 staged
receipt now records the exact buffer/chunk/transient peaks and requires zero retained loader
buffers at completion. The 30-minute soak additionally samples JS heap and the browser process
RSS throughout the one-time Stage-1 transfer, so browser/WasmFS copy overhead cannot disappear
behind the later steady-state sampling window.

## Evidence

- The exact predecessor fails first by trying to allocate the complete 18-byte fixture under a
  six-byte one-file ceiling; it exhausts all three attempts and reports `error` instead of `done`
  (`ledger/buildlogs/20260826T184347-1139655.log`).
- The current canonical pack measures 152,362,255 bytes, 2,963 files, and an 11,425,316-byte
  largest file, all below the 16 MiB per-file ceiling
  (`ledger/buildlogs/20260826T185846-1150271.log`).
- An actual tiny Emscripten WasmFS module verifies that cross-directory `/tmp` to `/bw` rename is
  supported and preserves exact bytes (`ledger/buildlogs/20260826T185817-1149975.log`).
- The final pinned-Node contract passes 20 Stage-1 behavior cases and rejects 22 mutations,
  including whole-payload allocation, early target publication, oversized files, oversized
  response chunks, and an oversized non-streaming fallback
  (`ledger/buildlogs/20260826T190237-1153665.log`).
- The expanded soak self-check, deterministic minification/provenance, M8 consumer, technical
  receipt contracts, and generated-source syntax are green
  (`ledger/buildlogs/20260826T190237-1153666.log`,
  `ledger/buildlogs/20260826T190257-1154067.log`,
  `ledger/buildlogs/20260826T190257-1154068.log`,
  `ledger/buildlogs/20260826T190257-1154072.log`, and
  `ledger/buildlogs/20260826T190257-1154086.log`).
- Exact REUSE 6.2.0 covers all 2,672 files (`ledger/buildlogs/20260826T190855-1160288.log`).
- Required M8 remains honestly red at its existing 25 APPLY/receipt/tier boundaries
  (`ledger/buildlogs/20260826T190326-1154900.log`). Authoritative container-backed regression
  restores M0 to 6/6 while M1-M8 retain their strict boundaries
  (`ledger/buildlogs/20260826T190529-1156479.log`).

## Boundary

The attempted full browser A/B timed out after 180 seconds waiting for the untouched monolithic
control to reach its running-state predicate, before the staged candidate or changed loader ran
(`ledger/buildlogs/20260826T185353-1147587.log`). It therefore binds no browser-memory result.
The M8 staged and soak receipts remain fail-closed until a real APPLY product exercises the new
telemetry. This task creates no APPLY artifact, public bundle, browser or hardware receipt,
profile, result promotion, promise, tolerance, golden, blacklist, dependency, or deferral change.
