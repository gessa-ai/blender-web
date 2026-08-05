// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// M7-prep standalone probe: validate WasmFS + OPFS backend under the SAME flag
// family the real browser Blender binary links (patches/platform_wasm.cmake:287-289
// — the _bw_browser_flags WASMFS profile). This is a bring-up probe, not derived
// from upstream Blender; it exists only to retire the M7 "sync access handles are
// worker-only — threads and sync IO are one coupled decision" architecture risk
// (GOAL.md "Emscripten posture") with measured, in-browser evidence.
//
// main() runs on the -sPROXY_TO_PTHREAD worker (NOT the browser main thread), so
// every file op here is a synchronous WasmFS op on a worker/pthread — exactly the
// posture ADR-003 depends on (IO is worker-side sync-handle, not main-thread JSPI).
//
// Tests, all reported to the page via MAIN_THREAD_EM_ASM -> window.opfsReport():
//   1. mount OPFS, write a ~100 MB (.blend-scale) file, read it back byte-identical,
//      measure write + read throughput.
//   2. persistence: on a fresh instance (page reload) the prior file is re-read from
//      OPFS and re-verified (a new wasm instance => fresh linear memory => the read
//      genuinely comes from OPFS storage, not a stale in-RAM cache).
//   3. sync IO from a pthread (main() worker + an explicit spawned thread) — proven
//      by 1/2/4; the browser-main-thread half is characterized in boot.js (JS).
//   4. concurrency: two pthreads writing/reading two distinct files simultaneously.

#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include <fcntl.h>
#include <pthread.h>
#include <sys/stat.h>
#include <unistd.h>

#include <emscripten/emscripten.h>
#include <emscripten/threading.h>
#include <emscripten/wasmfs.h>

// The exact link profile this TU is built under (see build.sh) — reported so the
// note records the tested flags verbatim.
#ifndef OPFS_PROBE_PROFILE
#  define OPFS_PROBE_PROFILE "unknown"
#endif

static void report(const char *s)
{
  MAIN_THREAD_EM_ASM(
      { if (typeof opfsReport === 'function') opfsReport(UTF8ToString($0)); }, s);
}

static void reportf(const char *fmt, ...)
{
  char buf[512];
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(buf, sizeof(buf), fmt, ap);
  va_end(ap);
  report(buf);
}

// Position-dependent deterministic payload; `salt` distinguishes concurrent files.
static inline uint8_t pat_byte(uint64_t i, uint8_t salt)
{
  uint64_t x = i + (uint64_t)salt * 0x9E3779B97F4A7C15ull;
  return (uint8_t)(x ^ (x >> 8) ^ (x >> 13) ^ (x >> 21));
}

static uint64_t fnv1a(const uint8_t *p, size_t n)
{
  uint64_t h = 1469598103934665603ull;
  for (size_t i = 0; i < n; i++) {
    h ^= p[i];
    h *= 1099511628211ull;
  }
  return h;
}

static void fill_pattern(uint8_t *buf, size_t n, uint8_t salt)
{
  for (size_t i = 0; i < n; i++) buf[i] = pat_byte(i, salt);
}

// Full write / read loops (handle short write/read). Return false on any error.
static bool write_all(int fd, const uint8_t *buf, size_t n)
{
  size_t off = 0;
  const size_t CHUNK = 8u * 1024 * 1024;
  while (off < n) {
    size_t want = n - off < CHUNK ? n - off : CHUNK;
    ssize_t w = write(fd, buf + off, want);
    if (w <= 0) return false;
    off += (size_t)w;
  }
  return true;
}

static bool read_all(int fd, uint8_t *buf, size_t n)
{
  size_t off = 0;
  const size_t CHUNK = 8u * 1024 * 1024;
  while (off < n) {
    size_t want = n - off < CHUNK ? n - off : CHUNK;
    ssize_t r = read(fd, buf + off, want);
    if (r <= 0) return false;
    off += (size_t)r;
  }
  return true;
}

// Write `n` bytes of salted pattern to `path`; return write-milliseconds or -1.
static double write_file(const char *path, size_t n, uint8_t salt, uint64_t *out_sum)
{
  uint8_t *buf = (uint8_t *)malloc(n);
  if (!buf) return -1;
  fill_pattern(buf, n, salt);
  if (out_sum) *out_sum = fnv1a(buf, n);
  double t0 = emscripten_get_now();
  int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0666);
  if (fd < 0) { free(buf); return -1; }
  bool ok = write_all(fd, buf, n);
  close(fd);
  double ms = emscripten_get_now() - t0;
  free(buf);
  return ok ? ms : -1;
}

// Read `path`, verify size + byte-identity against salted pattern. Sets *out_ms.
static bool verify_file(const char *path, size_t n, uint8_t salt, double *out_ms)
{
  struct stat st;
  if (stat(path, &st) != 0) return false;
  if ((size_t)st.st_size != n) {
    reportf("  [verify %s] SIZE MISMATCH got=%lld want=%zu", path,
            (long long)st.st_size, n);
    return false;
  }
  uint8_t *buf = (uint8_t *)malloc(n);
  uint8_t *ref = (uint8_t *)malloc(n);
  if (!buf || !ref) { free(buf); free(ref); return false; }
  fill_pattern(ref, n, salt);
  double t0 = emscripten_get_now();
  int fd = open(path, O_RDONLY);
  bool ok = fd >= 0 && read_all(fd, buf, n);
  if (fd >= 0) close(fd);
  if (out_ms) *out_ms = emscripten_get_now() - t0;
  bool identical = ok && memcmp(buf, ref, n) == 0;
  free(buf);
  free(ref);
  return identical;
}

static const size_t TP_BYTES = 100u * 1024 * 1024;  // ~100 MB .blend-scale payload
static const char *TP_PATH = "/opfs/throughput.bin";

// ---- Test 4: concurrent writers on distinct pthreads ------------------------
struct ConcArg {
  const char *path;
  size_t n;
  uint8_t salt;
  bool ok;
  double write_ms;
};

static void *conc_worker(void *p)
{
  ConcArg *a = (ConcArg *)p;
  uint64_t sum = 0;
  double w = write_file(a->path, a->n, a->salt, &sum);
  a->write_ms = w;
  a->ok = w >= 0 && verify_file(a->path, a->n, a->salt, nullptr);
  return nullptr;
}

int main()
{
  report("[probe] start (main() on PROXY_TO_PTHREAD worker)");
  reportf("[probe] profile: %s", OPFS_PROBE_PROFILE);

  // --- mount OPFS ---
  backend_t opfs = wasmfs_create_opfs_backend();
  if (!opfs) {
    report("MOUNT FAIL: wasmfs_create_opfs_backend() returned null");
    report("PROBE-DONE");
    return 1;
  }
  int mrc = wasmfs_create_directory("/opfs", 0777, opfs);
  if (mrc != 0) {
    reportf("MOUNT FAIL: wasmfs_create_directory('/opfs') rc=%d", mrc);
    report("PROBE-DONE");
    return 1;
  }
  report("MOUNT OK: OPFS backend mounted at /opfs");

  // --- Test 2 (persistence, runs BEFORE test 1 overwrites): re-read prior file ---
  {
    struct stat st;
    if (stat(TP_PATH, &st) == 0) {
      double rms = 0;
      bool ok = verify_file(TP_PATH, TP_BYTES, /*salt=*/7, &rms);
      if (ok)
        reportf("PERSIST-SURVIVED OK: %s survived reload, %zu bytes byte-identical "
                "(reread %.0f ms, %.1f MB/s)",
                TP_PATH, TP_BYTES, rms, (double)TP_BYTES / (1024.0 * 1024.0) / (rms / 1000.0));
      else
        reportf("PERSIST-SURVIVED FAIL: %s present but content/size mismatch", TP_PATH);
    }
    else {
      report("PERSIST-FRESH: no prior file (first load) — reload the tab to verify "
             "OPFS persistence");
    }
  }

  // --- Test 1: ~100 MB write + read-back byte-identical + throughput ---
  {
    uint64_t wsum = 0;
    double wms = write_file(TP_PATH, TP_BYTES, /*salt=*/7, &wsum);
    if (wms < 0) {
      report("THROUGHPUT FAIL: write error");
    }
    else {
      double rms = 0;
      bool ok = verify_file(TP_PATH, TP_BYTES, /*salt=*/7, &rms);
      double mb = (double)TP_BYTES / (1024.0 * 1024.0);
      if (ok)
        reportf("THROUGHPUT OK: %zu bytes byte-identical | write %.0f ms (%.1f MB/s) "
                "| read %.0f ms (%.1f MB/s)",
                TP_BYTES, wms, mb / (wms / 1000.0), rms, mb / (rms / 1000.0));
      else
        report("THROUGHPUT FAIL: read-back not byte-identical");
    }
  }

  // --- Test 4: two pthreads writing distinct files simultaneously ---
  {
    const size_t CN = 24u * 1024 * 1024;  // 24 MB each, concurrent
    ConcArg a = {"/opfs/concA.bin", CN, 11, false, -1};
    ConcArg b = {"/opfs/concB.bin", CN, 200, false, -1};
    pthread_t ta, tb;
    double t0 = emscripten_get_now();
    int ra = pthread_create(&ta, nullptr, conc_worker, &a);
    int rb = pthread_create(&tb, nullptr, conc_worker, &b);
    if (ra != 0 || rb != 0) {
      reportf("CONCURRENT FAIL: pthread_create ra=%d rb=%d", ra, rb);
    }
    else {
      pthread_join(ta, nullptr);
      pthread_join(tb, nullptr);
      double wall = emscripten_get_now() - t0;
      // Cross-check: distinct salts => distinct content, no cross-file corruption.
      bool distinct = verify_file("/opfs/concA.bin", CN, 11, nullptr) &&
                      verify_file("/opfs/concB.bin", CN, 200, nullptr);
      if (a.ok && b.ok && distinct)
        reportf("CONCURRENT OK: 2 pthreads wrote+verified 2x%zu MB distinct files "
                "(A %.0f ms, B %.0f ms, wall %.0f ms)",
                CN / (1024 * 1024), a.write_ms, b.write_ms, wall);
      else
        reportf("CONCURRENT FAIL: A.ok=%d B.ok=%d distinct=%d", a.ok, b.ok, distinct);
    }
  }

  report("PROBE-DONE");
  return 0;
}
