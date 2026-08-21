<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M8 monolithic deploy diagnostic (prepare-only)

Assembles and locally verifies a monolithic static-hosting bundle for the blender-web
windowed development build. **Prepare-only:** nothing here deploys, pushes, names
anything public, or produces an M8 receipt. The shipping APPLY/staged bundle is owned
by `sandbox/m8-staged-deploy/`; this older monolithic path remains useful for transport
and shell diagnostics against an OFF-mode build. The public brand is undecided and
human-owned (D-7); the shell `<title>` and comments still carry the local working name
and MUST be swapped before any publish.

## Files

| file | role | committed? |
|---|---|---|
| `make_bundle.sh`  | assemble the bundle from the gate build | yes |
| `_headers`        | Cloudflare-Pages COOP/COEP/CORP + MIME + cache (template) | yes |
| `serve_bundle.py` | COOP/COEP static server for local verify (port 8130) | yes |
| `verify_boot.mjs` | headed-Playwright boot -> isolate -> WM_main -> present -> capture | yes |
| `test_portability.py` | root/descendant, fixture assembly, confinement, and zero-browser checks | yes |
| `LAUNCH_AUDIT.md` | per-box LAUNCH.md close-out audit | yes |
| `bundle/`         | assembled output (wasm/data symlinked by default) | **no** (gitignored) |
| `artifacts/`      | verify captures + logs | **no** (gitignored) |

## Quick start

```
# 0. browser/product-free checks (safe before APPLY and on an s7-blocked host)
sandbox/m8-deploy/make_bundle.sh --selfcheck
.host-tools/bin/python3.13 sandbox/m8-deploy/test_portability.py
BW_NODE_MODULES=$PWD/.m4-node/node_modules \
  tools/emsdk/node/22.16.0_64bit/bin/node \
  sandbox/m8-deploy/verify_boot.mjs --selfcheck

# 1. assemble (symlink payload; fast, local-serve only)
sandbox/m8-deploy/make_bundle.sh
#    or a self-contained, uploadable bundle with real file copies:
sandbox/m8-deploy/make_bundle.sh --copy

# 2. serve with cross-origin isolation on port 8130
python3 sandbox/m8-deploy/serve_bundle.py 8130 sandbox/m8-deploy/bundle

# 3. boot-verify in headed Chromium using the pinned local toolchain
BW_NODE_MODULES=$PWD/.m4-node/node_modules \
  tools/emsdk/node/22.16.0_64bit/bin/node \
  sandbox/m8-deploy/verify_boot.mjs 1280x720 8130
```

`make_bundle.sh` reads the gate build from `build-wasm-windowed-opt/bin` (override
with `--bin DIR` or `$BLENDER_WEB_BIN`). It writes `bundle/BUNDLE_MANIFEST.txt` with
exact sizes + mtimes of whatever build was current at assembly time. Pass `--brotli`
to also measure brotli-q11 wire sizes (slow; and unreliable if a build lane is
relinking the binary - cite `sandbox/m8-dce-ranking/RANKING.md` for stable numbers).
The assembler derives its checkout from its own path, accepts caller-relative input
paths, and permits replacement only at `sandbox/m8-deploy/bundle` or a `bundle-*`
test/run path; this confines its intentional output-tree removal away from sources
and evidence.

## Bundle layout (docroot = the bundle dir)

```
index.html                 <- platform_web/shell/windowed.html, verbatim
diagnostics-bootstrap.js   <- current shell's early diagnostic capture
boot-windowed.js           <- shell boot; loads /bin/blender_browser.js, sets BIN_PREFIX=/bin/
file-bridge.js             <- current trusted file/open/save bridge
wgpu-preinit-worker.js     <- PROVENANCE COPY ONLY (baked into blender_browser.js; not fetched)
_headers                   <- COOP/COEP/CORP + MIME + cache
bin/blender_browser.js     <- Emscripten glue (has the WebGPU preinit post-js compiled in)
bin/blender_browser.wasm   <- symlink (or copy with --copy)
bin/blender_browser.data   <- symlink (or copy with --copy); the --preload-file payload
BUNDLE_MANIFEST.txt        <- generated sizes + provenance
```

**No `.worker.js`, no separate preinit worker file.** pthreads reuse the same glue
via `new Worker(pthreadMainJs)` (same-origin), and the WebGPU device pre-acquisition
(`wgpu-preinit-worker.js`) is a `--post-js` compiled into `blender_browser.js`. The
copy of `wgpu-preinit-worker.js` in the bundle is documentation/provenance so the
served bundle is a complete, auditable snapshot of the shell sources; nothing fetches
it at runtime (confirmed: the verify run served `index.html`, `boot-windowed.js`,
`bin/blender_browser.{js,wasm,data}` and nothing else, plus the browser's automatic
`/favicon.ico` -> 404, which is harmless and intentional; see "Favicon" below).

## Payload size + the shipping staged path

The bundle references the binary by **symlink** by default (so the ~200 MiB payload
is not copied on every assembly). `--copy` makes a real self-contained bundle you
could rsync/upload. Representative raw sizes (a moving target - the gpu/render lanes
relink the binary continuously):

| file | raw | note |
|---|---:|---|
| `bin/blender_browser.wasm` | ~118-152 MiB | swings with in-flight instrumentation |
| `bin/blender_browser.data` | ~81 MB | the monolithic `--preload-file` payload |
| `bin/blender_browser.js`   | ~0.59 MB | Emscripten glue + baked post-js |

The **wire** size (brotli) is what LAUNCH.md gates on, not raw. See
`LAUNCH_AUDIT.md` for the historical wire math. The required staged loading and
primary/deferred Wasm APPLY inventory now live in `sandbox/m8-staged-deploy/`; they
are deliberately not approximated by this monolithic diagnostic. A PASS here never
substitutes for the staged-product, accepted-hardware, or M8 receipts.

## MIME + brotli (hosting expectations)

**Required MIME:**

| ext | Content-Type | why |
|---|---|---|
| `.wasm` | `application/wasm` | `WebAssembly.instantiateStreaming` REJECTS any other type, and `_headers` sets `X-Content-Type-Options: nosniff` so it cannot be guessed |
| `.js`   | `text/javascript`  | ES module / worker script |
| `.data` | `application/octet-stream` | Emscripten fetches it as an ArrayBuffer; no sniffing needed |
| `.html` | `text/html`        | |

- **Cloudflare Pages** infers `.wasm`/`.js`/`.html` from the extension automatically;
  `.data` serves as `application/octet-stream`. The explicit Content-Type lines in
  `_headers` are belt-and-braces (safe alongside `nosniff`).
- `serve_bundle.py` sets the same map (Python's default `.wasm` handling is
  version-dependent, so it is set explicitly), so local verify matches production.

**Brotli precompression:**

- **Cloudflare Pages compresses at the edge automatically** (brotli for compressible
  types incl. `application/wasm`); you do NOT upload `.br` files - Pages ignores them
  and compresses the original. So on Pages, hosting is: upload raw, get brotli on the
  wire for free.
- **If you self-host** (nginx / S3+CloudFront / Caddy) precompress with
  `brotli -q 11 -k bin/blender_browser.wasm` (and `.data`, `.js`), serve the `.br`
  with `Content-Encoding: br` + `Vary: Accept-Encoding`, and keep the original for
  non-brotli clients. `-q 11` matches the measured wire numbers; `-k` keeps the
  original. Do NOT precompress on Pages.
- brotli is content-dependent and the binary is a moving target; treat any single
  measurement as +/- ~20% and defer to `RANKING.md` for the authoritative q11 figures.

## COOP/COEP (non-negotiable)

The module is `-pthread` (SharedArrayBuffer), so the page MUST be
cross-origin-isolated or it aborts before WM_main. `_headers` sets, on `/*`:

```
Cross-Origin-Opener-Policy:   same-origin
Cross-Origin-Embedder-Policy: require-corp
Cross-Origin-Resource-Policy: same-origin   (all assets same-origin)
X-Content-Type-Options:       nosniff
```

Runtime check: `self.crossOriginIsolated === true` (asserted by `verify_boot.mjs`).
If any asset ever moves to a separate CDN origin, that origin must send
`Cross-Origin-Resource-Policy: cross-origin` and the fetch must be crossorigin -
keeping everything same-origin avoids that entirely.

## Favicon

The bundle ships **no favicon on purpose.** A favicon is brand art, and the public
name/logo is a human-owned D-7 decision (no Blender logo anywhere). The browser's
automatic `/favicon.ico` request 404s harmlessly. Add one only after the brand is
chosen.

## Boot verdict (local verification)

Historical run 2026-08-08, HEAD `5750083`, gate build `build-wasm-windowed-opt/bin`, headed
bundled Chromium via Playwright, bundle served COOP/COEP on port 8130:

```
crossOriginIsolated=true  SharedArrayBuffer=true
WM_main reached in 829 ms
gate: backing 1280x720 dpr 1 __bwModule=true gateClass=true
toDataURL bitmap 1280x720  (presentBackbuffer x1, seen=true)
captured -> artifacts/bundle_boot_1280x720.png
VERDICT: PASS - bundle served COOP/COEP-isolated, booted to WM_main,
                presented real pixels, captured
```

**PASS on bundle mechanics:** the COOP/COEP server + `index.html` + `boot-windowed.js`
+ `bin/*` boot the `-pthread` module in a crossOriginIsolated tab, reach WM_main,
expose `window.__bwModule`, honor the `?gate=WxH` exact-size contract, and execute the
present path (`presentBackbuffer`). This historical diagnostic is not a current
artifact binding. On ornith-lab, s7 still requires an accepted hardware adapter before
any profile or gate receipt; llvmpipe may be used only for diagnosis.

**Caveat - the captured frame is black.** The current gate binary is an actively
relinked r29 in-flight build (it carries `[bw-r29-name]` printf instrumentation and
was rewritten at assembly time); it presents one black frame then idles for both the
workspace and the splash. This is a **GPU/render-lane state (the open solid-cube
Bug B), not a bundle fault** - the identical `page.screenshot({clip})` capture method
produced a non-black 390 KB image on the earlier r28 binary
(`sandbox/m4-fullscreen-parity/artifacts/web_1600x900.png`, 2026-08-07). Re-run the
verify against a rendering binary to capture a non-black frame; the bundle path is
proven.
