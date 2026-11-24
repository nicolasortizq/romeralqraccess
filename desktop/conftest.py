"""Shared pytest setup for the desktop app's test suite.

Importing the real `romeral` module pulls in tkinter, creates
~/Documents/ROMERAL_Datos/romeral.sqlite3 and runs schema DDL against it as a
side effect of module import. That is unacceptable in a test run (it could
touch a machine's real gate database), so tests get a lightweight stand-in
module instead, registered in sys.modules before anything imports it.

This file also doubles as the mechanism that puts `desktop/` on sys.path:
pytest inserts a conftest.py's own directory into sys.path when it imports
the conftest, which is what lets `desktop/tests/test_*.py` do a plain
`import ventas_online`.
"""
import sys
import types

_FAKE_CONFIG = {
    'ACCESO_API_URL': 'https://acceso.vallederomeral.cl',
    'ACCESO_TERMINAL_KEY': 'test-terminal-key',
}

_fake_romeral = types.ModuleType('romeral')
_fake_romeral.config = lambda key: _FAKE_CONFIG.get(key)
sys.modules['romeral'] = _fake_romeral
