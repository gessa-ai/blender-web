# Third-party dependencies

Runtime dependencies of the blender-web port. Every dependency must be
GPL-compatible (the shipped aggregate is GPL-3.0-or-later). Each is
cross-compiled to WebAssembly via the emcc superbuild and harvested to
`lib/wasm`; the canonical record is `ledger/deps.json`.

Status legend: **pending** = identified, not yet cross-compiled/harvested.

| Dependency | License | GPL-compatible | Status |
|---|---|---|---|
| CPython 3.13 | Python-2.0 (PSF) | yes | pending |
| oneTBB | Apache-2.0 | yes | pending |
| OpenEXR | BSD-3-Clause | yes | pending |
| OpenImageIO | Apache-2.0 | yes | pending |
| OpenColorIO | BSD-3-Clause | yes | pending |
| zlib | Zlib | yes | pending |
| FreeType | FTL OR GPL-2.0-or-later | yes | pending |
| libepoxy | MIT | yes | pending (GL loader; may be dropped once the WebGPU backend replaces GL) |

Notes:

- Seeded from the `pending` list in `ledger/deps.json`; expand as deps are
  pinned, licensed, and harvested (move to `decided` there, `pending -> shipped`
  here, and add version + upstream URL).
- Dependencies forced OFF in `patches/blender_web.cmake` are recorded, with a
  one-word rationale, under `forced_off` in `ledger/deps.json`.
