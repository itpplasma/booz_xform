#!/usr/bin/env python3

"""Regression tests for two booz_xform builds in one process.

Two copies of LLVM's libomp cannot be initialized in one process, so a build
that links an OpenMP runtime aborts ("OMP: Error #15") on its first transform as
soon as another build, for instance the PyPI wheel with its vendored libomp, has
already used its own.  The extension therefore must not load any OpenMP runtime.
Each scenario runs in a child interpreter, because the failure is an abort.
"""

import glob
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile

import booz_xform

WOUT = os.path.join(os.path.dirname(__file__), 'test_files', 'wout_li383_1.4m.nc')
EXT = glob.glob(os.path.join(os.path.dirname(booz_xform.__file__), '_booz_xform*'))[0]

LOADER = '''
import glob, importlib.util, os, sys
import numpy as np

def load(name, directory):
    path = glob.glob(directory + "/booz_xform/_booz_xform*.so")
    path = path or glob.glob(directory + "/booz_xform/_booz_xform*.pyd")
    spec = importlib.util.spec_from_file_location(name + "._booz_xform", path[0])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def transform(module, wout):
    b = module.Booz_xform()
    b.verbose = 0
    b.read_wout(wout)
    b.mboz, b.nboz = 6, 3
    b.run()
    return np.array(b.bmnc_b)
'''

LIBRARIES = '''
def loaded_libraries():
    if sys.platform == "darwin":
        import ctypes
        dyld = ctypes.CDLL(None)
        dyld._dyld_get_image_name.restype = ctypes.c_char_p
        return [dyld._dyld_get_image_name(i).decode()
                for i in range(dyld._dyld_image_count())]
    return [line.split()[-1] for line in open("/proc/self/maps") if "/" in line]
'''


def run_child(code, **kwargs):
    env = dict(os.environ)
    env.pop('KMP_DUPLICATE_LIB_OK', None)
    return subprocess.run([sys.executable, '-c', code], capture_output=True,
                          text=True, env=env, **kwargs)


class OpenMPClashTest(unittest.TestCase):
    def test_transform_loads_no_openmp_runtime(self):
        """Running a transform must not pull an OpenMP runtime into the process."""
        if not (sys.platform == 'darwin' or sys.platform.startswith('linux')):
            self.skipTest('no way to list the loaded libraries')
        code = LOADER + LIBRARIES + f'''
bx = load("this_build", {os.path.dirname(os.path.dirname(EXT))!r})
transform(bx, {WOUT!r})
openmp = sorted({{n for n in loaded_libraries() if any(
    tag in os.path.basename(n) for tag in ("libomp", "libgomp", "libiomp"))}})
print("OPENMP", openmp)
sys.exit(1 if openmp else 0)
'''
        result = run_child(code)
        self.assertEqual(result.returncode, 0, result.stdout[-2000:] + result.stderr[-2000:])

    def test_two_builds_in_one_process(self):
        """This build and the PyPI wheel agree when both run in the same process."""
        with tempfile.TemporaryDirectory() as tmp:
            download = subprocess.run(
                [sys.executable, '-m', 'pip', 'download', '--no-deps', '--only-binary', ':all:',
                 '--dest', tmp, 'booz_xform'], capture_output=True, text=True)
            wheels = glob.glob(os.path.join(tmp, 'booz_xform-*.whl'))
            if download.returncode != 0 or not wheels:
                self.skipTest('PyPI wheel not available: ' + download.stderr[-200:])
            reference = os.path.join(tmp, 'pypi')
            with zipfile.ZipFile(wheels[0]) as wheel:
                wheel.extractall(reference)
            code = LOADER + f'''
pypi = load("pypi_build", {reference!r})
this = load("this_build", {os.path.dirname(os.path.dirname(EXT))!r})
a = transform(pypi, {WOUT!r})
b = transform(this, {WOUT!r})
c = transform(pypi, {WOUT!r})
np.testing.assert_allclose(b, a, rtol=1e-12, atol=1e-14)
np.testing.assert_array_equal(a, c)
print("BOTH OK", a.shape)
'''
            result = run_child(code)
            self.assertEqual(result.returncode, 0, result.stdout[-2000:] + result.stderr[-2000:])
            self.assertIn('BOTH OK', result.stdout)


if __name__ == '__main__':
    unittest.main()
