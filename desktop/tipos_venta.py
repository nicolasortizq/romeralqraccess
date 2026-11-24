"""Shared `ventas.tipo` constants.

Side-effect-free on purpose: no imports, no romeral.py dependency. This lets
`desktop/tests/test_registrar_venta_online.py` import the exact value
`registrar_venta_online()` inserts without pulling in tkinter or the real
SQLite setup that importing `romeral.py` triggers (see conftest.py's
docstring for why that import is avoided in tests).
"""

# The only product that reaches the system through an online (QR) redemption
# (docs/PROYECTO.md 4.1). Must be one of the fixed set of values
# `VentaBoleta.validar()` (integracion_facturacion.py) accepts, or boleta
# emission fails for every online canje (see romeral.py's
# `registrar_venta_online()` docstring).
TIPO_VENTA_ONLINE = 'Entrada General'
