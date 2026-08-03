// SPDX-FileCopyrightText: 2026 blender-web contributors
// SPDX-License-Identifier: Apache-2.0
// Runtime proof that oneTBB parallel_for actually executes under wasm threads.
#include <atomic>
#include <cstdio>
#include <tbb/parallel_for.h>
#include <tbb/blocked_range.h>
#include <tbb/global_control.h>
#include <tbb/task_arena.h>

int main() {
  const int N = 1000000;
  std::atomic<long long> sum{0};
  std::atomic<int> workers_seen{0};

  // Warm up per WASM_Support.md so the browser/main thread joins scheduling.
  int nt = tbb::this_task_arena::max_concurrency();
  printf("max_concurrency=%d\n", nt);

  tbb::parallel_for(tbb::blocked_range<int>(0, N),
    [&](const tbb::blocked_range<int>& r) {
      workers_seen.fetch_add(1);
      long long local = 0;
      for (int i = r.begin(); i != r.end(); ++i) local += i;
      sum.fetch_add(local);
    });

  long long expected = (long long)N * (N - 1) / 2;
  printf("sum=%lld expected=%lld chunks=%d\n",
         sum.load(), expected, workers_seen.load());
  if (sum.load() != expected) { printf("FAIL: mismatch\n"); return 1; }
  printf("TBB_WASM_OK\n");
  return 0;
}
