<!--
SPDX-FileCopyrightText: 2026 blender-web contributors
SPDX-License-Identifier: CC0-1.0
-->

# M8 deploy bundle (prepare-only)

Assembles and locally verifies a static-hosting bundle for the blender-web windowed
gate build. **Prepare-only:** nothing here deploys, pushes, or names anything
public. The public brand is undecided and human-owned (D-7); the shell `<title>` and
comments still carry the local working name and MUST be swapped before any publish.

## Files

| file | role | committed? |
|---|---|---|
| `make_bundle.sh`  | assemble the bundle from the gate build | yes |
| `_headers`        | Cloudflare-Pages COOP/COEP/CORP + MIME + cache (template) | yes |
| `serve_bundle.py` | COOP/COEP static server for local verify (port 8130) | yes |
| `verify_boot.mjs` | headed-Playwright boot -> isolate -> WM_main -> present -> capture | yes |
| `LAUNCH_AUDIT.md` | per-box LAUNCH.md close-out audit | yes |
| `bundle/`         | assembled output (wasm/data symlinked by default) | **no** (gitignored) |
| `artifacts/`      | verify captures + logs | **no** (gitignored) |

## Quick start

```
# 1. assemble (symlink payload; fast, local-serve only)
sandbox/m8-deploy/make_bundle.sh
#    or a self-contained, uploadable bundle with real file copies:
sandbox/m8-deploy/make_bundle.sh --copy

# 2. serve with cross-origin isolation on port 8130
python3 sandbox/m8-deploy/serve_bundle.py 8130 sandbox/m8-deploy/bundle

# 3. boot-verify in headed Chromium (Playwright lives in game-platform)
NODE_PATH=/Users/paws/plushly/game-platform/node_modules \
  node sandbox/m8-deploy/verify_boot.mjs 1280x720 8130
```

`make_bundle.sh` reads the gate build from `build-wasm-windowed-opt/bin` (override
with `--bin DIR` or `$BLENDER_WEB_BIN`). It writes `bundle/BUNDLE_MANIFEST.txt` with
exact sizes + mtimes of whatever build was current at assembly time. Pass `--brotli`
to also measure brotli-q11 wire sizes (slow; and unreliable if a build lane is
relinking the binary - cite `sandbox/m8-dce-ranking/RANKING.md` for stable numbers).

## Bundle layout (docroot = the bundle dir)

```
index.html                 <- platform_web/shell/windowed.html, verbatim
boot-windowed.js           <- shell boot; loads /bin/blender_browser.js, sets BIN_PREFIX=/bin/
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

## Payload size + what staged-loading will change

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
`LAUNCH_AUDIT.md` for the honest wire math (wasm alone 20.13 MB brotli, stage-0
wire-to-interactive 24.71 MB, vs the 15 MB bar). **Staged-loading integration will
change this bundle:** the single `.data` splits into a stage-0 (served first) + a
lazy stage-1 fetched into cache after first pixels; the wasm later splits under JSPI;
a service worker precaches; and content-hashed filenames let `_headers` flip `bin/*`
to `Cache-Control: immutable`. `make_bundle.sh`/`_headers` are shaped so those are
additive (a stage manifest + hashed names + a `/sw.js` rule), not a rewrite.

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

Run 2026-08-08, HEAD `5750083`, gate build `build-wasm-windowed-opt/bin`, headed
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
present path (`presentBackbuffer`).

**Caveat - the captured frame is black.** The current gate binary is an actively
relinked r29 in-flight build (it carries `[bw-r29-name]` printf instrumentation and
was rewritten at assembly time); it presents one black frame then idles for both the
workspace and the splash. This is a **GPU/render-lane state (the open solid-cube
Bug B), not a bundle fault** - the identical `page.screenshot({clip})` capture method
produced a non-black 390 KB image on the earlier r28 binary
(`sandbox/m4-fullscreen-parity/artifacts/web_1600x900.png`, 2026-08-07). Re-run the
verify against a rendering binary to capture a non-black frame; the bundle path is
proven.
