# Memory64 probe (ADR-004 Decision 3)

Reproduces the wasm32-vs-wasm64 evidence in `notes/m64-probe.md`.
Toolchain: emsdk emcc 6.0.5.  Sources: hello.c, bench.cpp, ztest.c, fmttest.cpp, bench.html.

Build (wasm64 = add `-sMEMORY64=1`):
  em++ -O2 -std=c++20 -sENVIRONMENT=web -sMODULARIZE=1 -sEXPORT_NAME=Bench \
       -sEXIT_RUNTIME=0 -sALLOW_MEMORY_GROWTH=1 -sINITIAL_MEMORY=67108864 bench.cpp -o bench32.mjs
  em++ ... -sMEMORY64=1 bench.cpp -o bench64.mjs
  em++ -O2 -sMEMORY64=1 --use-port=zlib ztest.c -o ztest64.js            # zlib port
  em++ -O2 -std=c++20 -sMEMORY64=1 -I fmt-12.1.0/include fmttest.cpp \
       fmt-12.1.0/src/format.cc -o fmttest64.js                          # fmt dep
Run bench: serve dir, open bench.html?v=32 / ?v=64 in Chrome >=133; read console BENCH_RESULT.
node 22.x CANNOT run wasm64 (V8 12.4 rejects 64-bit table limits).
