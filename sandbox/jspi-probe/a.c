/* Case A: setjmp/longjmp with NO suspension. Built JS-EH (-fexceptions). */
#include <setjmp.h>
#include <stdio.h>
static jmp_buf b;
int main(void) {
  volatile int step = 0;
  if (setjmp(b) == 0) { step = 1; longjmp(b, 7); }
  else printf("RESULT A: PASS longjmp returned, step=%d (expect 1)\n", step);
  return 0;
}
