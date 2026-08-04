/* M2.7c: does a C++ try/catch (emscripten JS-EH invoke_* machinery) break a real
   JSPI suspension the way setjmp does? Parametrized by -DCASE=1|2|3.
   Built under JS-EH (-fexceptions) and Wasm-EH (-fwasm-exceptions) — see run.sh.
   NOTE: 'ay' is extern "C" but NOT noexcept, so at -O0 a call to it inside a try
   generates an invoke_* landing-pad wrapper (a JS frame). */
#include <cstdio>
#include <emscripten.h>
extern "C" EM_ASYNC_JS(int, ay, (int x), {
  await new Promise(r => setTimeout(r, 0));
  return x + 1;
});
struct Boom {};

#if CASE == 1
/* F1: suspend INSIDE an active try block */
int main() {
  int r = -9;
  try { r = ay(41); }              /* suspend directly inside the try */
  catch (Boom&) { r = -1; }
  printf("RESULT F1: reached r=%d (expect 42)\n", r);
  return 0;
}
#elif CASE == 2
/* F2: function CONTAINS try/catch, but the suspend is OUTSIDE it lexically */
int main() {
  volatile int t = 0;
  try { if (t) throw Boom{}; }     /* a real (kept) try/catch, not active at suspend */
  catch (Boom&) {}
  int r = ay(41);                  /* suspend with NO active try on the stack */
  printf("RESULT F2: reached r=%d (expect 42)\n", r);
  return 0;
}
#elif CASE == 3
/* F3: active try several plain frames above the suspend */
__attribute__((noinline)) static int d0() { return ay(41); }   /* the suspend */
__attribute__((noinline)) static int d1() { return d0(); }
__attribute__((noinline)) static int d2() { return d1(); }
__attribute__((noinline)) static int d3() { return d2(); }
__attribute__((noinline)) static int d4() { return d3(); }
__attribute__((noinline)) static int d5() { return d4(); }
int main() {
  int r = -9;
  try { r = d5(); }                /* active try 6 frames above the suspend */
  catch (Boom&) { r = -1; }
  printf("RESULT F3: reached r=%d (expect 42)\n", r);
  return 0;
}
#endif
