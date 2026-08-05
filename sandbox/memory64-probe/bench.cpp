#include <cstdio>
#include <cstdint>
#include <unordered_map>
#include <chrono>
int main(){
  using clk=std::chrono::high_resolution_clock;
  // (1) Hash-map churn — BLI Map<>-flavored: pointer/hash-heavy, memory-bound.
  auto t0=clk::now();
  std::unordered_map<uint64_t,uint64_t> m; m.reserve(1u<<20);
  uint64_t x=88172645463325252ull, acc=0; const int N=20000000;
  for(int i=0;i<N;i++){ x^=x<<13; x^=x>>7; x^=x<<17; uint64_t k=x&0xFFFFF;
    auto it=m.find(k); if(it==m.end()) m.emplace(k,x); else { acc+=it->second; if((x&3)==0) m.erase(it); } }
  auto t1=clk::now();
  // (2) Float loop — compute-bound (FP-contract off elsewhere; here plain).
  double f=1.0; const int FN=60000000;
  for(int i=0;i<FN;i++){ f=f*1.0000001+0.5; if(f>1e6) f-=1e6; }
  auto t2=clk::now();
  double map_ms=std::chrono::duration<double,std::milli>(t1-t0).count();
  double flt_ms=std::chrono::duration<double,std::milli>(t2-t1).count();
  printf("map_ms=%.1f flt_ms=%.1f acc=%llu f=%.3f size=%zu\n",map_ms,flt_ms,(unsigned long long)acc,f,m.size());
  return 0;
}
