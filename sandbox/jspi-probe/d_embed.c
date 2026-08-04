/* Case D: minimal libpython embed. Py_Initialize + run raise/except + import
   json, linked against libpython3.13.a. Question: static init + call
   trampoline under a -sJSPI link. */
#include <Python.h>
int main(void) {
  Py_Initialize();
  int rc = PyRun_SimpleString(
    "import json\n"
    "try:\n raise ValueError('x')\nexcept ValueError:\n pass\n"
    "print('RESULT D: PASS', json.dumps({'ok': 2**10}))\n");
  Py_Finalize();
  return rc;
}
