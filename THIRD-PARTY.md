# Third-party dependencies

This is the shipped WebAssembly/runtime dependency inventory. The machine-readable
canonical record, including pin/hash source, rationale, compatibility analysis and
build notes, is `ledger/deps.json`. Every row below is recorded there as built. License
compatibility is a separate per-dependency field in that ledger: it is not inferred
from this inventory, and the OpenSubdiv and OpenUSD custom-license reviews remain
explicitly unresolved and require GPL-literate human review. Disabled/non-shipped
components remain explicit in `ledger/deps.json` (`forced_off`) and
`ledger/deferred.json`.

| Dependency | Pinned version | License | Shipped role |
|---|---|---|---|
| OpenSubdiv | 3.7.0 | LicenseRef-OpenSubdiv-TOST-1.0 | CPU subdivision runtime |
| Imath | 3.2.2 | BSD-3-Clause | image/math runtime |
| Eigen | 8a1083e9bf41b91fdea6546681f806154efdc25a | MPL-2.0 | header/runtime code |
| zlib | 1.3.1 | Zlib | compression runtime |
| zstd | 1.5.7 | BSD-3-Clause | `.blend` compression runtime |
| fmt | 12.1.0 | MIT | formatting runtime |
| oneTBB | 2022.3.0 | Apache-2.0 | threaded task runtime |
| libjpeg-turbo | 2.1.3 | IJG AND BSD-3-Clause AND Zlib | JPEG codec |
| libpng | 1.6.58 | libpng-2.0 | PNG codec |
| shaderc | v2025.4 | Apache-2.0 | in-browser GLSL to SPIR-V compiler |
| glslang (shaderc-bundled) | Dawn pin 8d6dd0e41424c25806ca20523430f2e4c3aeb1a1 | BSD-3-Clause AND Apache-2.0 AND MIT | shader compiler runtime |
| Tint / Dawn | Dawn chromium/7989 @ 36cf1fae0cd8a81a4fb4580751648b80b2e6255c | BSD-3-Clause | in-browser SPIR-V to WGSL compiler |
| SPIRV-Tools | Dawn pin a9cdf5bdd25d516294b5c25502b67e6116ed7eb5 | Apache-2.0 | shader compiler runtime |
| SPIRV-Headers | Dawn pin 4015a331f5ffd6fc5c6fa7b03e08fb4a692491d7 | MIT | shader build input |
| Abseil | Dawn pin 63f52bfdb2ebc0ef3add13b98af45778d0040278 | Apache-2.0 | Tint runtime closure |
| Dawn shared utilities | chromium/7989 @ 36cf1fae0cd8a81a4fb4580751648b80b2e6255c | BSD-3-Clause | Tint runtime closure |
| libdeflate | 1.18 | MIT | OpenEXR compression runtime |
| OpenJPH | 0.25.2 | BSD-2-Clause | HTJ2K codec |
| OpenEXR | 3.4.10 | BSD-3-Clause | EXR codec/runtime |
| libtiff | 4.7.1 | libtiff | TIFF codec |
| tsl::robin-map | 1.3.0 | MIT | OpenImageIO header dependency |
| Expat | 2.7.5 | MIT | XML parser |
| pystring | 1.1.3 | BSD-3-Clause | OpenColorIO runtime |
| yaml-cpp | 0.8.0 | MIT | OpenColorIO configuration parser |
| minizip-ng | 4.0.10 | Zlib | ZIP container runtime |
| OpenColorIO | 2.5.0 | BSD-3-Clause | color-management runtime |
| OpenImageIO | 3.1.13.1 | Apache-2.0 | image-I/O runtime |
| pugixml (OpenImageIO-bundled) | OpenImageIO 3.1.13.1 pin | MIT | XML runtime |
| Brotli | 1.0.9 | MIT | FreeType/WOFF2 compression runtime |
| FreeType | 2.13.3 | FTL OR GPL-2.0-or-later | font runtime |
| Inter loader subset | 4.001 | OFL-1.1 | local loading-shell typography |
| CPython | 3.13.13 | PSF-2.0 | embedded Python runtime |
| NumPy | 2.3.4 | BSD-3-Clause | embedded Python extension/runtime |
| cattrs | 25.1.1 | MIT | Blender extension-system Python runtime |
| attrs | 25.3.0 | MIT | cattrs Python dependency |
| typing_extensions | 4.14.1 | PSF-2.0 | Python compatibility dependency |
| Requests | 2.32.3 | Apache-2.0 | embedded Python package |
| urllib3 | 2.4.0 | MIT | Requests dependency; browser transport is explicitly deferred |
| certifi | 2025.4.26 | MPL-2.0 | CA bundle/package |
| charset-normalizer | 3.4.1 | MIT | Requests dependency |
| idna | 3.10 | BSD-3-Clause | Requests dependency |
| OpenUSD | 26.03 | TOST-1.0 | core USD import/export runtime; Imaging/Hydra/Python bindings excluded |

Inter loader subset: Copyright 2016 The Inter Project Authors. The subset is a
renamed OFL-1.1 Modified Version derived from the font distributed at the Blender pin.

The browser bundle is fully client-side. No Blender-derived server component is part
of this inventory. Source and notices for the exact pins are retained by their build
recipes and the provenance fields in `ledger/deps.json`.
