// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// M7 project-store prototype (browser half). Builds the ACTUAL M7 OPFS project
// store designed in notes/m7-files-prep.md §2b + notes/m7-store-design.md and
// exercises it with REAL .blend bytes — this is the store the platform account-sync
// design (notes/platform-integration-design.md) consumes.
//
// It is NOT derived from upstream Blender: it is the port-layer T1/T2 mount+bridge
// mechanics (wasmfs_create_opfs_backend + wasmfs_create_directory + nested mkdir +
// POSIX write/read/readdir) exercised standalone, so the design is validated before
// it lands as a platform_web init fn against the M4 shell.
//
// main() runs on the -sPROXY_TO_PTHREAD worker (NOT the browser main thread), so
// every file op is a synchronous WasmFS OPFS op on a worker/pthread — the exact
// posture ADR-003 / m7-opfs-probe requires (sync access handles are worker-only).
//
// The designed layout, mounted at /projects (== the real T1 `wasmfs_create_directory
// ("/projects", 0777, opfs)` on the main() worker):
//
//   /projects/                        OPFS mount root ( == BLENDER_USER_RESOURCES )
//     <name>.blend                    user documents (save target; operator filepath)
//     config/                         BLENDER_USER_CONFIG  -> userpref.blend, recent-files.txt
//     .recovery/                      TMPDIR / BKE_tempdir_base -> <pid>_autosave.blend, quit.blend
//     .cache/                         shader OPFS cache (GOAL GPU)
//
// Steps (each reported to the page via window.storeReport):
//   A. mount OPFS at /projects, create the designed subdir layout (config/.recovery/.cache).
//   B. write a REAL embedded corpus .blend's bytes to /projects/<name>.blend, read
//      back byte-identical (memcmp) AND confirm the .blend magic header survived.
//   C. write the designed config + recovery artifacts (userpref.blend stand-in,
//      recent-files.txt, .recovery/quit.blend) — the platform-facing seams.
//   D. directory listing (readdir) of /projects and /projects/config — the
//      recent-files / library / account-sync seam the platform design needs.
//   E. 50 MB .blend save + load timing (a .blend-magic-prefixed 50 MB payload).
//   F. persistence: on reload (fresh wasm instance) re-read the real .blend +
//      config/recovery artifacts and re-verify — proves the bytes came from OPFS.

#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include <cerrno>
#include <dirent.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <emscripten/emscripten.h>
#include <emscripten/wasmfs.h>

#ifndef M7_STORE_PROFILE
#  define M7_STORE_PROFILE "unknown"
#endif
// Baked-in path of the embedded real corpus .blend (see build.sh --embed-file).
#ifndef M7_EMBED_BLEND
#  define M7_EMBED_BLEND "/embed/sample.blend"
#endif

static void report(const char *s)
{
  MAIN_THREAD_EM_ASM(
      { if (typeof storeReport === 'function') storeReport(UTF8ToString($0)); }, s);
}
static void reportf(const char *fmt, ...)
{
  char buf[640];
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(buf, sizeof(buf), fmt, ap);
  va_end(ap);
  report(buf);
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

// ---- byte-exact IO helpers --------------------------------------------------
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
// Write whole buffer to `path`; returns write-ms or -1.
static double write_bytes(const char *path, const uint8_t *buf, size_t n)
{
  double t0 = emscripten_get_now();
  int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0666);
  if (fd < 0) return -1;
  bool ok = write_all(fd, buf, n);
  close(fd);
  return ok ? emscripten_get_now() - t0 : -1;
}
// Read whole file into a fresh buffer; returns bytes read (caller frees) + read-ms.
static uint8_t *read_bytes(const char *path, size_t *out_n, double *out_ms)
{
  struct stat st;
  if (stat(path, &st) != 0) return nullptr;
  size_t n = (size_t)st.st_size;
  uint8_t *buf = (uint8_t *)malloc(n ? n : 1);
  if (!buf) return nullptr;
  double t0 = emscripten_get_now();
  int fd = open(path, O_RDONLY);
  bool ok = fd >= 0 && read_all(fd, buf, n);
  if (fd >= 0) close(fd);
  if (out_ms) *out_ms = emscripten_get_now() - t0;
  if (!ok) { free(buf); return nullptr; }
  *out_n = n;
  return buf;
}
static bool write_str(const char *path, const char *s)
{
  return write_bytes(path, (const uint8_t *)s, strlen(s)) >= 0;
}
static bool is_blend_magic(const uint8_t *b, size_t n)
{
  // Uncompressed .blend starts "BLENDER"; zstd-compressed starts 28 b5 2f fd.
  if (n >= 7 && memcmp(b, "BLENDER", 7) == 0) return true;
  if (n >= 4 && b[0] == 0x28 && b[1] == 0xb5 && b[2] == 0x2f && b[3] == 0xfd) return true;
  return false;
}

// The designed OPFS mount + layout (matches the real T1 shim / notes recipe).
static const char *MOUNT = "/projects";
static const char *REAL_BLEND = "/projects/mesh_dense.blend";  // user document
static const char *CFG_USERPREF = "/projects/config/userpref.blend";
static const char *CFG_RECENT = "/projects/config/recent-files.txt";
static const char *RECOVERY_QUIT = "/projects/.recovery/quit.blend";
static const char *BIG_BLEND = "/projects/big50.blend";
static const size_t BIG_BYTES = 50u * 1024 * 1024;

// ---- D: directory listing (the recent-files / account-sync seam) ------------
static int list_dir(const char *dir)
{
  DIR *d = opendir(dir);
  if (!d) { reportf("  [ls %s] opendir FAIL", dir); return -1; }
  int n = 0;
  struct dirent *e;
  while ((e = readdir(d)) != nullptr) {
    if (strcmp(e->d_name, ".") == 0 || strcmp(e->d_name, "..") == 0) continue;
    char full[512];
    snprintf(full, sizeof(full), "%s/%s", dir, e->d_name);
    struct stat st;
    long long sz = (stat(full, &st) == 0) ? (long long)st.st_size : -1;
    const char *kind = (stat(full, &st) == 0 && S_ISDIR(st.st_mode)) ? "dir " : "file";
    reportf("    [%s] %-24s %10lld B", kind, e->d_name, sz);
    n++;
  }
  closedir(d);
  return n;
}

int main()
{
  report("[store] start (main() on PROXY_TO_PTHREAD worker)");
  reportf("[store] profile: %s", M7_STORE_PROFILE);

  // === A. mount OPFS at /projects + designed subdir layout ===================
  backend_t opfs = wasmfs_create_opfs_backend();
  if (!opfs) { report("MOUNT FAIL: wasmfs_create_opfs_backend() null"); report("PROBE-DONE"); return 1; }
  int mrc = wasmfs_create_directory(MOUNT, 0777, opfs);
  if (mrc != 0) { reportf("MOUNT FAIL: wasmfs_create_directory('%s') rc=%d", MOUNT, mrc); report("PROBE-DONE"); return 1; }
  // Nested dirs via ordinary mkdir on the OPFS-backed mount — exactly what
  // BLI_dir_create_recursive does when appdir routes config/tempdir onto OPFS.
  // EEXIST on reload (dir already persisted) counts as success.
  auto mkd = [](const char *p) -> bool {
    errno = 0;
    return mkdir(p, 0777) == 0 || errno == EEXIST;
  };
  bool layout_ok = mkd("/projects/config") & mkd("/projects/.recovery") & mkd("/projects/.cache");
  if (layout_ok)
    reportf("MOUNT OK: OPFS at %s + designed layout {config,.recovery,.cache}", MOUNT);
  else
    report("MOUNT WARN: a designed subdir mkdir failed (not EEXIST)");

  // === F(pre). persistence check — read prior real .blend BEFORE re-writing ===
  {
    size_t pn = 0; double pms = 0;
    uint8_t *pb = read_bytes(REAL_BLEND, &pn, &pms);
    if (pb) {
      bool magic = is_blend_magic(pb, pn);
      reportf("PERSIST-SURVIVED %s: %s survived reload, %zu B, magic=%s, fnv=%016llx "
              "(reread %.0f ms, %.1f MB/s)",
              magic ? "OK" : "FAIL", REAL_BLEND, pn, magic ? "yes" : "NO",
              (unsigned long long)fnv1a(pb, pn), pms,
              (double)pn / (1024.0 * 1024.0) / (pms / 1000.0));
      // also confirm the config + recovery artifacts persisted
      size_t un = 0; uint8_t *ub = read_bytes(CFG_USERPREF, &un, nullptr);
      size_t rn = 0; uint8_t *rb = read_bytes(CFG_RECENT, &rn, nullptr);
      size_t qn = 0; uint8_t *qb = read_bytes(RECOVERY_QUIT, &qn, nullptr);
      reportf("PERSIST-ARTIFACTS %s: config/userpref=%zuB recent-files=%zuB .recovery/quit=%zuB",
              (ub && rb && qb) ? "OK" : "PARTIAL", un, rn, qn);
      free(pb); free(ub); free(rb); free(qb);
    }
    else {
      report("PERSIST-FRESH: no prior /projects/mesh_dense.blend (first load) — reload to verify OPFS persistence");
    }
  }

  // === B. write a REAL corpus .blend's bytes to OPFS, read back byte-identical =
  {
    size_t en = 0; double dummy = 0;
    uint8_t *eb = read_bytes(M7_EMBED_BLEND, &en, &dummy);  // embedded (in-memory backend)
    if (!eb) {
      reportf("BLEND-RW FAIL: embedded corpus %s not readable", M7_EMBED_BLEND);
    }
    else {
      uint64_t src = fnv1a(eb, en);
      bool src_magic = is_blend_magic(eb, en);
      double wms = write_bytes(REAL_BLEND, eb, en);
      size_t rn = 0; double rms = 0;
      uint8_t *rb = (wms >= 0) ? read_bytes(REAL_BLEND, &rn, &rms) : nullptr;
      bool identical = rb && rn == en && memcmp(rb, eb, en) == 0;
      bool magic_ok = rb && is_blend_magic(rb, rn);
      double mb = (double)en / (1024.0 * 1024.0);
      if (identical && magic_ok && src_magic)
        reportf("BLEND-RW OK: real .blend %zu B byte-identical on OPFS (magic BLENDER preserved, "
                "fnv=%016llx) | save %.0f ms (%.1f MB/s) | load %.0f ms (%.1f MB/s)",
                en, (unsigned long long)src, wms, mb / (wms / 1000.0), rms, mb / (rms / 1000.0));
      else
        reportf("BLEND-RW FAIL: identical=%d magic_ok=%d src_magic=%d rn=%zu en=%zu",
                identical, magic_ok, src_magic, rn, en);
      free(rb);
      free(eb);
    }
  }

  // === C. write the designed config + recovery artifacts (platform seams) =====
  {
    // userpref.blend stand-in: a minimal .blend-magic'd blob (the real binary writes
    // a genuine userpref here via BKE_appdir_folder_id_create(BLENDER_USER_CONFIG)).
    const char *up = "BLENDER-v502\0m7-store userpref stand-in";
    bool a = write_bytes(CFG_USERPREF, (const uint8_t *)up, 40) >= 0;
    // recent-files.txt: exactly the format wm_files.cc writes (one path per line).
    bool b = write_str(CFG_RECENT, "/projects/mesh_dense.blend\n/projects/scene_two.blend\n");
    // .recovery/quit.blend: BKE_tempdir_base() autosave/recovery target.
    const char *q = "BLENDER-v502\0m7-store quit.blend stand-in";
    bool c = write_bytes(RECOVERY_QUIT, (const uint8_t *)q, 41) >= 0;
    reportf("ARTIFACTS %s: wrote config/userpref.blend + config/recent-files.txt + .recovery/quit.blend",
            (a && b && c) ? "OK" : "FAIL");
  }

  // === D. directory listing — the recent-files / library / account-sync seam ==
  {
    report("DIRLIST /projects:");
    int n1 = list_dir("/projects");
    report("DIRLIST /projects/config:");
    int n2 = list_dir("/projects/config");
    if (n1 >= 0 && n2 >= 0)
      reportf("DIRLIST OK: /projects has %d entr(ies), /projects/config has %d — readdir seam works",
              n1, n2);
    else
      report("DIRLIST FAIL: readdir error");
  }

  // === E. 50 MB .blend save + load timing =====================================
  {
    uint8_t *buf = (uint8_t *)malloc(BIG_BYTES);
    if (!buf) { report("BIG50 FAIL: OOM allocating 50 MB"); }
    else {
      memcpy(buf, "BLENDER-v502", 12);              // real .blend magic prefix
      for (size_t i = 12; i < BIG_BYTES; i++)
        buf[i] = (uint8_t)((i * 2654435761u) >> 13);  // deterministic body
      uint64_t src = fnv1a(buf, BIG_BYTES);
      double wms = write_bytes(BIG_BLEND, buf, BIG_BYTES);
      size_t rn = 0; double rms = 0;
      uint8_t *rb = (wms >= 0) ? read_bytes(BIG_BLEND, &rn, &rms) : nullptr;
      bool ok = rb && rn == BIG_BYTES && fnv1a(rb, rn) == src && is_blend_magic(rb, rn);
      double mb = (double)BIG_BYTES / (1024.0 * 1024.0);
      if (ok)
        reportf("BIG50 OK: 50 MB .blend save %.0f ms (%.1f MB/s) | load %.0f ms (%.1f MB/s) | byte-verified",
                wms, mb / (wms / 1000.0), rms, mb / (rms / 1000.0));
      else
        reportf("BIG50 FAIL: wms=%.0f rn=%zu ok=%d", wms, rn, ok ? 1 : 0);
      free(rb);
      free(buf);
    }
  }

  report("PROBE-DONE");
  return 0;
}
