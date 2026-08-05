#include <zlib.h>
#include <string.h>
#include <stdio.h>
int main(){ char in[256]; memset(in,'A',255); in[255]=0;
  char out[512]; uLongf ol=sizeof(out);
  int r=compress((Bytef*)out,&ol,(const Bytef*)in,strlen(in));
  char dec[512]; uLongf dl=sizeof(dec);
  int r2=uncompress((Bytef*)dec,&dl,(const Bytef*)out,ol);
  printf("ZLIB ok=%d,%d comp=%lu ptr=%zu\n", r,r2, (unsigned long)ol, sizeof(void*)); return 0; }
