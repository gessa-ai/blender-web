/* Case C: libjpeg-turbo's classic setjmp/longjmp error path (one of our 29
   deps). Feed a corrupt stream; error_exit must longjmp back. No suspension. */
#include <stdio.h>
#include <setjmp.h>
#include "jpeglib.h"
struct my_err { struct jpeg_error_mgr pub; jmp_buf jb; };
static void my_exit(j_common_ptr c) { longjmp(((struct my_err*)c->err)->jb, 1); }
int main(void) {
  struct jpeg_decompress_struct cinfo;
  struct my_err jerr;
  unsigned char garbage[64];
  for (int i = 0; i < 64; i++) garbage[i] = 0xFF;   /* not a valid JPEG */
  cinfo.err = jpeg_std_error(&jerr.pub);
  jerr.pub.error_exit = my_exit;
  if (setjmp(jerr.jb)) {
    jpeg_destroy_decompress(&cinfo);
    printf("RESULT C: PASS libjpeg setjmp error path fired\n");
    return 0;
  }
  jpeg_create_decompress(&cinfo);
  jpeg_mem_src(&cinfo, garbage, sizeof garbage);
  jpeg_read_header(&cinfo, TRUE);   /* -> error_exit -> longjmp */
  printf("RESULT C: UNEXPECTED no error\n");
  return 1;
}
