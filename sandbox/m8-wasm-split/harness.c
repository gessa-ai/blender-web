// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// M8 wasm-split feasibility harness (reduced repro of the shipped constraint set).
//
// Purpose: prove/disprove that emscripten 6.0.5's SPLIT_MODULE demand-load works
// under blender-web's LOAD-BEARING link constraints WITHOUT JSPI/Asyncify:
//   -pthread + -sPROXY_TO_PTHREAD (main() on a worker), -sMODULARIZE, -sWASM_BIGINT,
//   -fexceptions (JS-EH), -sALLOW_MEMORY_GROWTH, no -sJSPI (ADR-006).
//
// The C program models Blender's boot/cold split:
//   * hot_function  -> called at boot (stays in the PRIMARY module).
//   * cold_subsystem -> a leaf "subsystem" that is NEVER called at boot; it is the
//     function wasm-split moves to the SECONDARY module. It is reached only on
//     demand, and from two distinct thread contexts:
//       cmd 1: the proxied-main (WM-worker-equivalent) thread calls it directly.
//       cmd 2: a freshly spawned pthread (TBB-worker-equivalent) calls it.
//     Case 2 is the decisive test: does the placeholder/secondary-load runtime
//     work on an arbitrary pthread, or only on the proxied-main thread?
//
// Control channel: JS (browser main thread) only ever WRITES a command int into
// SHARED linear memory via bw_set_cmd(); the cold call itself always executes on a
// worker thread (the command loop below, or the spawned pthread) - never on the
// browser main thread, where a large synchronous WebAssembly compile is illegal.

#include <emscripten.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <time.h>

// --- control block, in shared linear memory (pthreads => SharedArrayBuffer) ---
static _Atomic int g_cmd       = 0; // JS -> worker: 1=cold-here, 2=cold-on-pthread, 99=quit
static _Atomic int g_done_seq  = 0; // worker -> JS: monotonic completion counter
static _Atomic int g_result    = 0; // worker -> JS: last cold_subsystem() result
static _Atomic int g_boot_done = 0; // worker -> JS: boot reached the command loop
static _Atomic int g_cold_runs = 0; // how many times cold_subsystem actually executed

// COLD leaf subsystem. noinline+used so it survives as its own splittable symbol.
// Does real work so it is not folded to a constant.
__attribute__((noinline, used))
int cold_subsystem(int x) {
  volatile int acc = x;
  for (int i = 0; i < 2000; i++) acc = (acc * 1103515245 + 12345) & 0x7fffffff;
  atomic_fetch_add(&g_cold_runs, 1);
  printf("[cold_subsystem] EXECUTED x=%d -> %d (run #%d)\n",
         x, acc, atomic_load(&g_cold_runs));
  return acc;
}

// HOT boot-path function. Stays in the primary module.
__attribute__((noinline, used))
int hot_function(int x) {
  printf("[hot_function] boot-path, x=%d\n", x);
  return x + 1;
}

static void *thread_fn(void *arg) {
  (void)arg;
  printf("[pthread] spawned worker calling cold_subsystem\n");
  int r = cold_subsystem(4242);
  printf("[pthread] cold_subsystem returned %d\n", r);
  return (void *)(intptr_t)r;
}

// JS-callable: WRITE a command. Runs on the caller (browser main) thread but only
// touches shared memory (an atomic store) - safe on any thread, no cold call here.
EMSCRIPTEN_KEEPALIVE void bw_set_cmd(int c)      { atomic_store(&g_cmd, c); }
EMSCRIPTEN_KEEPALIVE int  bw_get_done_seq(void)  { return atomic_load(&g_done_seq); }
EMSCRIPTEN_KEEPALIVE int  bw_get_result(void)    { return atomic_load(&g_result); }
EMSCRIPTEN_KEEPALIVE int  bw_get_boot_done(void) { return atomic_load(&g_boot_done); }
EMSCRIPTEN_KEEPALIVE int  bw_get_cold_runs(void) { return atomic_load(&g_cold_runs); }

int main(void) {
  printf("[boot] main() on proxied-main (worker) thread\n");
  hot_function(7);
  atomic_store(&g_boot_done, 1);
  printf("[boot] complete; cold_subsystem NOT called; entering command loop\n");

  for (;;) {
    int c = atomic_load(&g_cmd);
    if (c == 1) {
      printf("[cmd1] cold_subsystem on the proxied-main worker\n");
      int r = cold_subsystem(100);
      atomic_store(&g_result, r);
      atomic_store(&g_cmd, 0);
      atomic_fetch_add(&g_done_seq, 1);
    } else if (c == 2) {
      printf("[cmd2] cold_subsystem on a fresh pthread\n");
      pthread_t t;
      pthread_create(&t, NULL, thread_fn, NULL);
      void *rv = NULL;
      pthread_join(t, &rv);
      atomic_store(&g_result, (int)(intptr_t)rv);
      atomic_store(&g_cmd, 0);
      atomic_fetch_add(&g_done_seq, 1);
    } else if (c == 99) {
      break;
    }
    struct timespec ts = {0, 3 * 1000 * 1000}; // 3ms yield (legal blocking on a worker)
    nanosleep(&ts, NULL);
  }
  printf("[quit] command loop exit\n");
  return 0;
}
