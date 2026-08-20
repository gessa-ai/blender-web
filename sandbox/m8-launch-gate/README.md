<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M8 technical release gate

This directory is the fail-closed integration gate for the locally testable M8
contract. It binds the staged/offline/performance proof, a current-artifact 30-minute
soak, branded current Chrome + Edge receipts, generated dashboard/deferrals, and a
tracked-input-bound compliance receipt to the exact build hashes.

The technical candidate also requires `current-product-receipt.json` for the complete
30-second product path: local first interaction, orbit/Tab/extrude, own-file wow,
fidelity tells, a safe allowlisted share-scene URL, and the end-to-end skeptic path.
This keeps absent product seams visible instead of letting packaging evidence stand in
for them.

`verify_m8.py` has a non-circular two-phase contract:

- Default: pre-receipt technical candidate. It consumes current M0–M7 plus exact
  M8 evidence, but does not require an M8 result or dashboard row to pre-exist.
- `--post-receipt`: only after the harness writes the exact `technical_release`
  M8 check, require M0–M8 and byte-compare the dashboard to a fresh generator
  output with no timestamp normalization.
- `--launch`: also requires schema-2 `artifacts/external-launch-signoff.json`, its
  detached SSH signature, and a tracked `launch-owner.allowed_signers`. The signed
  owner receipt binds the exact commit and deploy-bundle digest, independent product
  name, real source/demo/dashboard/methodology URLs, lawyer identity/date, and final
  post hash. It must also ratify the exact SHA-256 of `harness/run.sh` and the exact
  production-transport receipt; a bare policy boolean cannot authorize gate changes.
  Local automation must not create or populate those authority values.

Every invocation writes `artifacts/current-m8-preflight.json` with three independent
failure lists: `technical_failures`, `post_receipt_failures`, and
`external_blockers`. A clean local candidate can therefore report
`technical_pass: true` while remaining honestly `launch_ready: false`; missing owner
authority is never mislabeled as a browser or artifact failure. If exact local bundle
bytes do not yet exist, launch mode sets `external_verification_deferred: true` and
`external_launch_pass: null`: the invalid local inventory remains a technical failure,
not a fabricated owner/hosting blocker.

The non-local closure items are deliberately narrow and explicit:

- the owner chooses and approves the independent product/repository/domain/handle
  name, logo posture, repository description, and real public source URL;
- a human owner ratifies the exact harness policy and signs schema-2 launch authority
  binding commit, bundle, public URLs, final-post hash, and review date;
- a GPL-literate lawyer supplies the recorded license/post review, including the
  unresolved OpenSubdiv custom-license compatibility/sufficiency judgment;
- the owner selects a deployable hosting/package design, publishes the exact bytes,
  and supplies the deployed-origin transport/COOP/COEP/offline receipt (the current
  raw bundle cannot be claimed as an unmodified Cloudflare Pages deployment);
- the owner publishes the source, dashboard, methodology, demo, launch media/post,
  and community messages, then checks the corresponding LAUNCH.md boxes; and
- any required human-authored-history remediation and public AI-assistance disclosure
  is performed/approved by the humans responsible for that history.

Locally actionable work remains in `technical_failures`: final split-inventory and
exact-tree packaging, first-present/semantic Stage-0 proof, pinned load budgets,
offline cache/input proof, skeptic path, branded-browser matrix, 30-minute soak,
factual license/notices/dashboard generation, and the post-receipt byte comparison.
The verifier enforces the external evidence schema but cannot manufacture its values.

Launch mode separately requires `artifacts/production-transport-receipt.json` from
the real deployed origin. It must bind every decoded canonical asset to the local
raw bundle file (`_headers` and local `.br` packaging sidecars are not public logical
URLs), record wire encodings/lengths and COOP/COEP, and prove isolated browser boot plus an
offline reload. The local server's raw-URL-to-`.br` behavior is diagnostic only. An
unmodified Cloudflare Pages deploy is currently incompatible with the bundle because
its raw assets exceed Pages' per-file limit; the owner must select a deployable
package/host and produce the deployed-origin receipt.

The technical gate keeps the existing launch budgets: cold first pixels at or below
8 seconds under the pinned 1.5 MB/s + 40 ms profile, at most 15,000,000 compressed
critical bytes, a full 30-minute soak with under 10% JS-heap and browser-process RSS
growth, no stalls/GPU errors/fatals, and real branded Chrome and Edge runs.

Reproduce the static verdict:

```sh
python3 sandbox/m8-launch-gate/verify_m8.py
python3 sandbox/m8-launch-gate/verify_m8.py --post-receipt
python3 sandbox/m8-launch-gate/verify_m8.py --launch
python3 sandbox/m8-launch-gate/verify_m8.py --launch --post-receipt
```

The browser-matrix producer supports two strict host identities. On macOS it resolves the
canonical app bundle and re-runs Apple code-signature, team, CDHash, and notarization checks. On
Linux amd64 it requires the canonical package-owned PIE ELF, exact `dpkg` ownership/version/full
package verification, an equal installed APT candidate with archive SHA-256, and a one-line
`signed-by` vendor repository whose keyring contains only the accepted current vendor primary
fingerprint. Neither platform accepts a Playwright-bundled Chromium binary as branded Chrome or
Edge.

Run the browser-free producer and shared producer/verifier contract checks first. They require
the recorded Node 22.16.0 but do not require a browser, display, package, or GPU:

```sh
tools/emsdk/node/22.16.0_64bit/bin/node \
  sandbox/m8-launch-gate/browser_matrix.mjs --selfcheck
tools/emsdk/node/22.16.0_64bit/bin/node \
  sandbox/m8-launch-gate/runtime_evidence_selfcheck.mjs
.host-tools/bin/python3.13 sandbox/m8-launch-gate/verify_m8.py --selfcheck
```

The macOS capture commands remain, using the same exact Node and module root:

```sh
export BW_NODE_MODULES="$PWD/.m4-node/node_modules"
node22="$PWD/tools/emsdk/node/22.16.0_64bit/bin/node"
"$node22" sandbox/m8-launch-gate/browser_matrix.mjs 8168 chrome \
  sandbox/m8-launch-gate/.browsers/Google\ Chrome.app/Contents/MacOS/Google\ Chrome
"$node22" sandbox/m8-launch-gate/browser_matrix.mjs 8168 edge \
  sandbox/m8-launch-gate/.browsers/Microsoft\ Edge.app/Contents/MacOS/Microsoft\ Edge
```

For Linux, configure dedicated keyrings containing only Google's active Linux signing primary
`EB4C1BFD4F042F6DDDCCEC917721F63BD38B4796` and Microsoft's Edge signing primary
`BC528686B50D79E339D3721CEB3E94ADBE1229CF`. The exact active APT lines must be:

```text
deb [arch=amd64 signed-by=/etc/apt/keyrings/blender-web-google-linux.gpg] https://dl.google.com/linux/chrome/deb/ stable main
deb [arch=amd64 signed-by=/etc/apt/keyrings/blender-web-microsoft-edge.gpg] https://packages.microsoft.com/repos/edge stable main
```

Install current `google-chrome-stable` and `microsoft-edge-stable` from those authenticated
repositories, then run both rows against the same served APPLY bundle with the exact local module
root and canonical package ELFs:

```sh
export BW_NODE_MODULES="$PWD/.m4-node/node_modules"
node22="$PWD/tools/emsdk/node/22.16.0_64bit/bin/node"
"$node22" sandbox/m8-launch-gate/browser_matrix.mjs 8168 chrome \
  /opt/google/chrome/chrome
"$node22" sandbox/m8-launch-gate/browser_matrix.mjs 8168 edge \
  /opt/microsoft/msedge/msedge
```

The Linux producer also checks the platform-specific official stable APIs (`linux` for Chrome and
`Linux` for Edge) and requires the package-derived upstream version, browser runtime version, and
official stable version to be identical. A software WebGPU adapter still binds no browser row;
ornith-lab must clear the separate s7 hardware-adapter and APPLY-product gates first.

The retained Edge 151 package can be reproduced from the immutable Microsoft
enterprise artifact URL/hash recorded in
`artifacts/edge-151-reproducibility.json`; the branded Chrome stable package URL
is mutable, so its signed local app must be retained until the final run.

Run the exact offline skeptic path, trusted own-file drop, and safe share-route
negative/positive proofs against that same bundle. First run the producer-only
self-check; it performs no product access or browser launch:

```sh
tools/emsdk/node/22.16.0_64bit/bin/node \
  sandbox/m8-launch-gate/verify_product_bar.mjs --selfcheck
```

Then use the same exact Node/module root and an explicit canonical branded Chrome
executable. On macOS:

```sh
export BW_NODE_MODULES="$PWD/.m4-node/node_modules"
node22="$PWD/tools/emsdk/node/22.16.0_64bit/bin/node"
"$node22" sandbox/m8-launch-gate/verify_product_bar.mjs 8168 \
  "$PWD/sandbox/m8-launch-gate/.browsers/Google Chrome.app/Contents/MacOS/Google Chrome"
```

On Linux, after installing the authenticated package described above:

```sh
export BW_NODE_MODULES="$PWD/.m4-node/node_modules"
node22="$PWD/tools/emsdk/node/22.16.0_64bit/bin/node"
"$node22" sandbox/m8-launch-gate/verify_product_bar.mjs 8168 \
  /opt/google/chrome/chrome
```

The Linux row binds the same ELF/dpkg/APT/keyring identity as the Chrome browser-matrix
row. It still requires the s7-cleared hardware adapter and exact APPLY bundle; a software
adapter may run diagnostics but cannot produce this receipt.

The only accepted public share selector is `?scene=stress-mixed`. Unknown values,
paths, and URLs are rejected without a request; the accepted same-origin fixture is
length/SHA-256 checked before Blender opens it. Python, argv, capture-gate,
keepalive-tuning, and manual-stage query controls remain available only in the source
development shell and are ignored by the assembled public copy.

Generate the technical-package compliance input. It exits on factual package/source
checks only (REUSE, notices, provenance, third-party inventory, and exact carried
license bytes). The same receipt continues to report public disclaimer, compatibility
judgment, public source URL, and history/disclosure policy as non-blocking external
policy facts; the default technical gate does not manufacture or require them.

```sh
export BW_REUSE_BIN="$PWD/.host-tools/reuse-6.2.0/bin/reuse"
python3 sandbox/m8-launch-gate/audit_compliance.py --selfcheck
python3 sandbox/m8-launch-gate/audit_compliance.py
```

The producer accepts only REUSE 6.2.0 from the explicit absolute non-symlink path, the
repository-local host-tool location, or `PATH`; it records the selected executable's size and
SHA-256. Missing, indirect, or version-drifted tools fail before evidence allocation. The cold-host
installation is pinned in `notes/migration-to-ornith-lab.md`.

After M7 has reassembled and verified the current bundle, run its 1.5 MB/s + 40 ms
measurement and bind both M7 JSON proofs plus q11 wire sizes:

```sh
bash sandbox/m8-staged-deploy/make_staged_bundle.sh --copy --brotli
python3 sandbox/m8-staged-deploy/serve_measure.py 8168 \
  sandbox/m8-staged-deploy/bundle-staged
```

With that exact-tree server running, generate both raw runtime inputs before the
receipt. `make_staged_receipt.py` rejects either input if it is stale for the
current build or bundle. Both producers support Darwin and Linux, require the
exact Node/module versions and an explicit canonical branded Chrome executable,
and provide browser-free contract checks to run before the live capture.

```sh
export BW_NODE_MODULES="$PWD/.m4-node/node_modules"
node22="$PWD/tools/emsdk/node/22.16.0_64bit/bin/node"
"$node22" sandbox/m8-staged-deploy/verify_staged.mjs --selfcheck
"$node22" sandbox/m8-launch-gate/measure_current.mjs --selfcheck
"$node22" sandbox/m8-staged-deploy/verify_staged.mjs 8168 \
  /opt/google/chrome/chrome
"$node22" sandbox/m8-launch-gate/measure_current.mjs 8168 \
  /opt/google/chrome/chrome 3
python3 sandbox/m8-launch-gate/make_staged_receipt.py
```

On Darwin, replace the Linux ELF with the canonical signed Google Chrome app
executable already documented for the browser matrix; no implicit browser fallback
is accepted on either host.

`serve_measure.py` refuses every docroot that is not the exact current public
tree: it validates the sanitized split manifest, current build identities,
symlink-free allowlist, q11 siblings, and the complete `_headers` block policy
(including JSON MIME and revalidation). Its no-store transport-proof endpoint
records origin GET counters. `verify_staged.mjs` binds those counters to three
fresh processes: a cold trusted semantic interaction with one exact shard
request and full PARK/PREPARED/APPLY/PAGE_READY/RESUMED state change, an online
warm cache-first shard response with zero additional origin GETs, and the same
semantic/deferred lifecycle while Chromium is offline. Missing M7 APIs fail the
run; the rig never substitutes a weaker WM-main or cache-inventory assertion.

The transport parser/path/docroot negative fixtures are browser-free:

```sh
node22="$PWD/tools/emsdk/node/22.16.0_64bit/bin/node"
bash sandbox/m8-staged-deploy/make_staged_bundle.sh --selfcheck
.host-tools/bin/python3.13 sandbox/m8-staged-deploy/serve_measure.py --selfcheck
"$node22" sandbox/m8-staged-deploy/verify_update_transition.mjs
.host-tools/bin/python3.13 sandbox/m8-launch-gate/test_technical_receipt_contracts.py
```

The assembly and server self-checks derive the checkout from their own files and
read no APPLY manifest or product bytes. The transition fixture models two distinct
generated cache versions. It proves that
an old cache-first shell revalidates `/service-worker-register.js` online,
authenticates and precaches the new active worker before that worker claims the
page, and retains the old register/cache as the verified offline and failed-claim
fallback. The control resource remains in `PRECACHE_URLS` but is the sole launch
asset excluded from `CACHE_FIRST_URLS`.

The receipt fixture rejects missing, duplicate, unlisted, queryless, or early
deferred-Wasm requests and extra artifact identities. Performance evidence is valid
only when every finalizer-owned shipping shard is actually observed exactly once:
the primary before the semantic interaction and the content-addressed deferred URL
strictly afterward.

Assembly is fail-closed on the public legal payload. The bundle carries the aggregate
license, AUTHORS/NOTICE, provenance, third-party inventory, all repository SPDX license
texts needed by the assembled tree, the exact OpenSubdiv custom license/NOTICE, and the
exact OpenUSD 26.03 LICENSE/NOTICE bytes under `legal/`; the persistent visible footer
links the inventory and the service worker must cache every legal file for the offline
proof.

The split build is also fail-closed. Every runner reads
`build-wasm-windowed-opt/bin/blender_browser.split-build.json`, requires a successful
APPLY contract, verifies every inventory hash/path/role, and rejects any unlisted
`blender_browser*.wasm*` file. Every shipped primary/deferred shard, its q11 sibling,
and a sanitized `bin/split-build.json` are part of the exact bundle identity. The
public manifest contains only shipped filenames/roles/hashes/phases plus its source
manifest/glue digests; absolute build/profile/map paths and timestamps are rejected.
Performance rows
must prove the manifest's critical/deferred request phase against the first decoded
semantic scene plus trusted visible interaction.

Finally run the current-artifact stability window after all source/bundle bytes
have stopped moving. The soak waits for strict product pixels before starting its
full 30-minute clock, samples JS heap plus the complete browser-process RSS tree, and
fails on missing/zero/discontinuous samples, growth at or above 10%, external
requests, stalls, GPU errors, or fatal/page failures.

Run the browser-free portability contract first. It derives the checkout and output
roots from the producer, requires exact Node 22.16.0 plus Playwright 1.61.1/PNGJS
7.0.0, checks both Darwin and Linux Chrome identity/release selectors, and launches
no browser:

```sh
export BW_NODE_MODULES="$PWD/.m4-node/node_modules"
node22="$PWD/tools/emsdk/node/22.16.0_64bit/bin/node"
"$node22" sandbox/m8-launch-gate/soak_current.mjs --selfcheck
```

Then use the same exact Node/module root and an explicit canonical branded Chrome
executable. On macOS:

```sh
"$node22" sandbox/m8-launch-gate/soak_current.mjs 8168 30 \
  "$PWD/sandbox/m8-launch-gate/.browsers/Google Chrome.app/Contents/MacOS/Google Chrome"
```

On Linux, after installing the authenticated package described above:

```sh
"$node22" sandbox/m8-launch-gate/soak_current.mjs 8168 30 \
  /opt/google/chrome/chrome
```

The Linux row uses the same canonical ELF/dpkg/APT/keyring identity and stable-release
feed as the performance and Chrome-matrix rows. Its process-tree RSS sampler uses the
host `ps` command from procps. It still requires the s7-cleared hardware adapter and
exact APPLY bundle; a software adapter cannot produce this receipt.

Receipt files are generated evidence and are CC0-1.0 through `REUSE.toml`. Never copy
an older PASS forward: the verifier recalculates the current build and bundle hashes.
