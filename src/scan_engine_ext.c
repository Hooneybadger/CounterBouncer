/* scan_engine_ext.c — scan_engine.c의 scan_run()을 *CPython 확장*으로 노출한다(import 로드용).
 *
 * 왜: 평가 서버는 동봉 네이티브 엔진을 **`import`(CPython 확장)**로 로드한다 — 2024 우승작(DMS,
 * TEAM027)이 pybind11 `import engine`으로 우승했고(eval_results.json status=ok), 우리 v1.4.x의
 * `ctypes.CDLL`은 4연패했다. .bin은 서버에 도달했고(전송·git 확인)·로컬선 로드되며(dlopen 확장자
 * 무관)·추출 dir은 exec 가능한데(DMS .so가 거기서 import됨) `_CENGINE_OK=False`였으므로, 유일한
 * 일탈인 `ctypes`가 막혔거나(샌드박스 탈출 벡터) import의 sys.path 해석과 어긋난 것으로 좁혀진다.
 * 둘 다 *DMS식 import*로 사라진다. 그래서 같은 엔진을 import 가능한 확장으로도 빌드한다.
 *
 * abi3: Py_LIMITED_API로 빌드해 산물이 `scan_engine_ext.abi3.so` — Python 3.8+ 어느 마이너서도
 * 로드된다(서버가 3.10/3.11/3.12 무엇이든 무관; DMS의 cpython-310 전용 .so보다 강건).
 * 평문 .so(ctypes/memfd 폴백)와 분리된 파일이라 평문 빌드엔 Python 의존이 들어가지 않는다.
 *
 * 사용: `import scan_engine_ext; rc = scan_engine_ext.run(in_path, out_path, max_s)`.
 */
#define PY_SSIZE_T_CLEAN
#include <Python.h>

/* scan_engine.c에서 정의(같은 .so로 함께 컴파일). */
extern int scan_run(const char *in_path, const char *out_path, double max_s);

static PyObject *ext_run(PyObject *self, PyObject *args) {
    const char *in_path, *out_path;
    double max_s;
    int rc;
    if (!PyArg_ParseTuple(args, "ssd", &in_path, &out_path, &max_s))
        return NULL;
    Py_BEGIN_ALLOW_THREADS              /* GIL 해제 — C 엔진이 길게 도는 동안 */
    rc = scan_run(in_path, out_path, max_s);
    Py_END_ALLOW_THREADS
    return PyLong_FromLong((long)rc);
}

static PyMethodDef ext_methods[] = {
    {"run", ext_run, METH_VARARGS,
     "run(in_path, out_path, max_s) -> rc; scan 엔진을 in/out 파일경로로 호출(rc=0 성공)"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef ext_module = {
    PyModuleDef_HEAD_INIT,
    "scan_engine_ext",
    "OGC scan engine (CPython 확장, abi3) — scan_run 래퍼",
    -1,
    ext_methods,
    NULL, NULL, NULL, NULL
};

PyMODINIT_FUNC PyInit_scan_engine_ext(void) {
    return PyModule_Create(&ext_module);
}
