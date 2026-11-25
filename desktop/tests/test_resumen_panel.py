"""Tests for romeral.Romeral.actualizar_resumen(), the live on-screen
summary panel.

The panel and the printed/archived cash close must never disagree about the
same day's numbers, so actualizar_resumen() uses the same aggregation the
close uses (cierre_caja.calcular_resumen_cierre). Before that it grouped by
tipo/medio with no `origen` awareness, so an online redemption was folded
into 'Entrada General' on screen while the close showed it on its own line.

Driving this needs the real `romeral` module, which the rest of the suite
replaces with a stand-in (desktop/conftest.py) because importing it creates
the gate's sqlite3 file. So this runs in a subprocess with HOME pointed at a
temporary directory, like tests/test_app_startup.py, and calls the method
unbound against a stub `self` -- no Tkinter window is ever constructed.
"""
import json
import subprocess
import sys
from pathlib import Path

DESKTOP_DIR = Path(__file__).resolve().parent.parent

DRIVER = r"""
import json
from datetime import datetime

import romeral

hoy = datetime.now().strftime('%Y-%m-%d')
romeral.conn.executemany(
    'INSERT INTO ventas (fecha,cantidad,precio,total,medio,tipo,estado_boleta,origen) '
    'VALUES (?,?,?,?,?,?,?,?)',
    [
        (f'{hoy} 10:00:00', 2, 12000, 24000, 'Webpay', 'Entrada General',
         'EMITIDA', 'ONLINE'),
        (f'{hoy} 11:00:00', 3, 12000, 36000, 'Efectivo', 'Entrada General',
         'EMITIDA', 'PRESENCIAL'),
    ],
)
romeral.conn.commit()


class _Var:
    def set(self, value):
        self.value = value


class _App:
    pass


app = _App()
app.resumen = _Var()
romeral.Romeral.actualizar_resumen(app)
print('---PANEL---')
print(json.dumps(app.resumen.value))
"""


def _panel_text(tmp_path):
    result = subprocess.run(
        [sys.executable, '-c', DRIVER],
        cwd=DESKTOP_DIR,
        env={
            'HOME': str(tmp_path),
            'USERPROFILE': str(tmp_path),
            'PATH': '/usr/bin:/bin:/usr/sbin:/sbin',
        },
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    payload = result.stdout.split('---PANEL---', 1)[1].strip()
    return json.loads(payload)


def test_online_redemptions_are_not_folded_into_a_presencial_tipo(tmp_path):
    panel = _panel_text(tmp_path)

    # The day has one online redemption (2 people, $24.000) and one in-person
    # sale (3 people, $36.000). "Entrada General" must show only the
    # in-person half, exactly as the printed close's POR SERVICIO does.
    assert 'Entrada General: 3 pers. · $36.000' in panel
    assert 'Entrada General: 5 pers.' not in panel


def test_online_redemptions_get_their_own_line(tmp_path):
    panel = _panel_text(tmp_path)

    assert 'ONLINE (no suma a efectivo esperado)' in panel
    assert '2 pers. · 1 canje · $24.000' in panel


def test_grand_totals_still_include_online_revenue(tmp_path):
    panel = _panel_text(tmp_path)

    # Online money is real revenue even though it is not cash.
    assert 'PERSONAS INGRESADAS\n5' in panel
    assert 'RECAUDACIÓN\n$60.000' in panel
    assert 'VENTAS REALIZADAS\n2' in panel
    # ...but expected cash stays Efectivo-only.
    assert 'Efectivo: $36.000' in panel
    assert 'Webpay: $24.000' in panel
