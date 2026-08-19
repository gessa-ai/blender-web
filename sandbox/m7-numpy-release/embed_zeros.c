/* SPDX-FileCopyrightText: 2026 blender-web contributors
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * numpy release-mode (-DNDEBUG) verification gate. Registers the 13 production numpy
 * C-extension PyInit_* in a custom inittab (exactly as bpy_interface.cc will) and runs the
 * EXACT m7-io-smoke repro: a bare `numpy.zeros(5)` allocation. Under the -sPROXY_TO_PTHREAD
 * profile (main proxied to a worker) the DEBUG build aborts here on
 * `assert(PyGILState_Check())` (numpy/_core/src/multiarray/alloc.c:130); the release build
 * (assertions compiled out) allocates cleanly. numpy resolves from the HARVESTED tree
 * (lib/wasm/lib/python3.13/site-packages/numpy) + the linked archive, so this validates what
 * scripts/deps/numpy.sh actually swapped into lib/wasm — WITHOUT relinking blender.js.
 */
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdio.h>
#include <stdlib.h>

#define NP_MODS(X) \
  X(_multiarray_umath) X(_umath_linalg) X(lapack_lite) X(_pocketfft_umath) \
  X(mtrand) X(_common) X(bit_generator) X(_bounded_integers) X(_generator) \
  X(_mt19937) X(_philox) X(_pcg64) X(_sfc64)

#define DECL(n) extern PyObject *PyInit_##n(void);
NP_MODS(DECL)
#undef DECL

static struct _inittab numpy_inittab[] = {
  {"numpy._core._multiarray_umath", PyInit__multiarray_umath},
  {"numpy.linalg._umath_linalg",    PyInit__umath_linalg},
  {"numpy.linalg.lapack_lite",      PyInit_lapack_lite},
  {"numpy.fft._pocketfft_umath",    PyInit__pocketfft_umath},
  {"numpy.random.mtrand",           PyInit_mtrand},
  {"numpy.random._common",          PyInit__common},
  {"numpy.random.bit_generator",    PyInit_bit_generator},
  {"numpy.random._bounded_integers", PyInit__bounded_integers},
  {"numpy.random._generator",       PyInit__generator},
  {"numpy.random._mt19937",         PyInit__mt19937},
  {"numpy.random._philox",          PyInit__philox},
  {"numpy.random._pcg64",           PyInit__pcg64},
  {"numpy.random._sfc64",           PyInit__sfc64},
  {NULL, NULL},
};

int main(void) {
  setenv("PYTHONHOME", "/Users/paws/blender-web/lib/wasm", 1);
  setenv("PYTHONPATH",
         "/Users/paws/blender-web/lib/wasm/lib/python3.13/site-packages", 1);
  setenv("PYTHONDONTWRITEBYTECODE", "1", 1);

  if (PyImport_ExtendInittab(numpy_inittab) != 0) {
    fprintf(stderr, "FATAL: PyImport_ExtendInittab failed\n");
    return 2;
  }

  PyConfig config;
  PyConfig_InitPythonConfig(&config);
  PyStatus status = Py_InitializeFromConfig(&config);
  PyConfig_Clear(&config);
  if (PyStatus_Exception(status)) {
    fprintf(stderr, "FATAL: Py_InitializeFromConfig failed\n");
    return 3;
  }

  const char *code =
    "import numpy\n"
    "print('NUMPY', numpy.__version__)\n"
    "a = numpy.zeros(5)\n"                       /* the exact m7 repro (first alloc) */
    "print('ZEROS_OK', tuple(a.shape), float(a.sum()))\n"
    "s = int(numpy.array([1,2,3]).sum())\n"
    "print('SUM', s)\n"
    "assert s == 6, s\n"
    "print('NUMPY_GATE_OK')\n";
  int rc = PyRun_SimpleString(code);
  if (rc != 0) {
    fprintf(stderr, "GATE FAIL: python raised\n");
    Py_Finalize();
    return 1;
  }
  Py_Finalize();
  return 0;
}
