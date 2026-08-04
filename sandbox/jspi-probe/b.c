/* Case B: does a JS-EH setjmp/longjmp survive a suspend/resume?
   B1 = setjmp -> suspend -> longjmp back after resume (the dangerous shape).
   B2 = suspend inside the setjmp region, normal return (no longjmp).
   Built with -sJSPI (native stack switch; runtime browser-gated) and, as a
   runnable node proxy, -sASYNCIFY (=1). JSPI is ASYNCIFY=2 internally. */
#include <stdio.h>
#include <setjmp.h>
#include <emscripten.h>
EM_ASYNC_JS(int, async_yield, (int x), {
  await new Promise(r => setTimeout(r, 0));
  return x + 1;
});
static jmp_buf buf;
static void b1(void) {
  volatile int n = -1;
  if (setjmp(buf) == 0) {
    int r = async_yield(41);   /* suspend + resume */
    n = r;                     /* 42 */
    longjmp(buf, 1);           /* longjmp AFTER a suspension crossed the frame */
  } else {
    printf("RESULT B1: PASS suspend-then-longjmp n=%d (expect 42)\n", n);
  }
}
static void b2(void) {
  int captured = 0;
  if (setjmp(buf) == 0) {
    int r = async_yield(99);   /* suspend + resume, jmp_buf live but unused */
    captured = r;              /* 100 */
    printf("RESULT B2: PASS suspend-normal-return captured=%d (expect 100)\n", captured);
  }
}
int main(void){ b1(); b2(); return 0; }
