#include <fmt/core.h>
#include <fmt/format.h>
int main(){
  auto s = fmt::format("fmt on wasm ptr={} n={} hex={:#x}", sizeof(void*), 42, 255);
  fmt::print("{}\n", s);
  return 0;
}
