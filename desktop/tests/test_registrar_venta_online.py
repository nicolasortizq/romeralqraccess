"""Regression test for the `tipo` value `registrar_venta_online()` writes.

`romeral.py`'s `registrar_venta_online()` (desktop/romeral.py) always writes
`tipo=TIPO_VENTA_ONLINE` (currently `'Entrada General'`) for an online
redemption, instead of the earlier `'Entrada Online'`. The reason is
`VentaBoleta.validar()` (desktop/integracion_facturacion.py): it only
accepts a fixed set of `tipo` values and raises `ValueError` on anything
else, which would make `emitir_automaticamente()` fail on every single
online redemption if the inserted row's `tipo` were not one of those
accepted values.

This test imports `TIPO_VENTA_ONLINE` from `tipos_venta.py` — the same
constant `registrar_venta_online()` uses for its insert — instead of a
hand-typed copy of the literal, so a future regression in that constant's
value is what actually makes this test fail, not a coincidentally-matching
string here.

This module never imports `romeral` (see desktop/conftest.py's docstring
for why) or touches sqlite; it exercises `VentaBoleta.validar()` directly
with the exact `tipo`/`medio` combination `registrar_venta_online()` inserts,
so the regression would be caught here without needing a real DB or a
Tkinter app instance.
"""
import pytest

from integracion_facturacion import VentaBoleta
from tipos_venta import TIPO_VENTA_ONLINE


def test_entrada_general_with_webpay_is_accepted():
    """The exact tipo/medio combination registrar_venta_online() inserts."""
    venta = VentaBoleta(referencia='VR1TESTCODE', tipo=TIPO_VENTA_ONLINE,
                         personas=2, total=20000, medio='Webpay')
    venta.validar()  # must not raise


def test_entrada_online_is_rejected():
    """Regression guard: the old tipo value this fix replaced must still fail.

    If `registrar_venta_online()` ever regresses back to 'Entrada Online',
    this documents why that breaks boleta emission for every online canje.
    """
    venta = VentaBoleta(referencia='VR1TESTCODE', tipo='Entrada Online',
                         personas=2, total=20000, medio='Webpay')
    with pytest.raises(ValueError):
        venta.validar()
