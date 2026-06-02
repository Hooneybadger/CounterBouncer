#define _POSIX_C_SOURCE 200809L
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
static double seconds(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t); return t.tv_sec+t.tv_nsec*1e-9; }
static uint64_t random64(uint64_t *x) { *x ^= *x << 13; *x ^= *x >> 7; *x ^= *x << 17; return *x; }
int main(int argc,char **argv) {
 if(argc!=3) return 2;
 uint64_t checksum=0,seed=42; double start=seconds();
 if(!strcmp(argv[1],"branch")) {
  size_t n=1<<20; unsigned char *a=malloc(n); if(!a)return 3;
  for(size_t i=0;i<n;i++)a[i]=!strcmp(argv[2],"random") ? random64(&seed)&1 : 1;
  volatile uint64_t yes=0,no=0;
  for(int r=0;r<120;r++)for(size_t i=0;i<n;i++){if(a[i])yes+=i;else no+=i;}
  checksum=yes+no; free(a);
 } else if(!strcmp(argv[1],"cache")) {
  size_t n=!strcmp(argv[2],"large") ? (1<<24) : (1<<12);
  uint32_t *a=malloc(n*sizeof(*a)); if(!a)return 3;
  for(size_t i=0;i<n;i++)a[i]=(uint32_t)i;
  for(size_t i=n-1;i>0;i--){size_t j=random64(&seed)%(i+1);uint32_t t=a[i];a[i]=a[j];a[j]=t;}
  uint32_t x=0;for(size_t i=0;i<(1<<25);i++)x=a[x]; checksum=x;free(a);
 } else if(!strcmp(argv[1],"memory")) {
  size_t n=1<<24; double *a=malloc(n*8),*b=malloc(n*8),*c=malloc(n*8);if(!a||!b||!c)return 3;
  for(size_t i=0;i<n;i++){b[i]=i%13;c[i]=i%7;}
  do {for(size_t i=0;i<n;i++)a[i]=b[i]+3*c[i];checksum+=(uint64_t)a[checksum%n];} while(seconds()-start<1.0);
  free(a);free(b);free(c);
 } else return 2;
 printf("CALIBRATION runtime_s=%.9f checksum=%llu\n",seconds()-start,(unsigned long long)checksum);return 0;
}
