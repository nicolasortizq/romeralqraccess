"""Startup regression tests for the real `romeral.py` entry point.

Every other test in this suite imports its subject with a stand-in `romeral`
module already in `sys.modules` (see `desktop/conftest.py`), which is correct
for unit tests but structurally hides import-cycle bugs in the real startup
path: `romeral.py` runs as `__main__`, so a module-level `import romeral` in
a module that `romeral.py` itself imports re-executes `romeral.py` as a
second module and raises ImportError before the window ever opens.

These tests therefore run the real file in a subprocess, with HOME pointed at
a temporary directory so the app's SQLite database is created there and the
machine's real ~/Documents/ROMERAL_Datos is never touched.
"""
import subprocess
import sys
from pathlib import Path

DESKTOP_DIR = Path(__file__).resolve().parent.parent

# Stub tkinter's mainloop so the app builds its real window and then returns
# instead of blocking the test run forever.
RUN_AS_MAIN = """
import runpy
import sys
import tkinter

sys.argv = ['romeral.py']
tkinter.Tk.mainloop = lambda self: print('STARTUP_OK')
runpy.run_path('romeral.py', run_name='__main__')
"""


def _run(code, tmp_path):
    env = {
        'HOME': str(tmp_path),
        'USERPROFILE': str(tmp_path),
        'PATH': '/usr/bin:/bin:/usr/sbin:/sbin',
    }
    return subprocess.run(
        [sys.executable, '-c', code],
        cwd=DESKTOP_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_importing_romeral_as_a_module_succeeds(tmp_path):
    result = _run("import romeral; print('IMPORT_OK')", tmp_path)
    assert 'ImportError' not in result.stderr, result.stderr
    assert result.returncode == 0, result.stderr
    assert 'IMPORT_OK' in result.stdout


def test_running_romeral_as_main_does_not_hit_the_import_cycle(tmp_path):
    result = _run(RUN_AS_MAIN, tmp_path)
    assert 'ImportError' not in result.stderr, result.stderr
    assert result.returncode == 0, result.stderr
    assert 'STARTUP_OK' in result.stdout


def test_the_app_database_is_created_under_home_not_the_real_one(tmp_path):
    """Proves the two tests above never touch ~/Documents/ROMERAL_Datos."""
    _run("import romeral", tmp_path)
    assert (tmp_path / 'Documents' / 'ROMERAL_Datos' / 'romeral.sqlite3').exists()
