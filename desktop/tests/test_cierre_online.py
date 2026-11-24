"""Tests for cierre_caja.calcular_resumen_cierre(), the aggregation behind
panel_cierre()'s resumen() closure in romeral.py.

The business rule under test (CLAUDE.md, docs/PROYECTO.md 4.7): online
redemptions (origen='ONLINE', from ventas_online.py's
registrar_venta_online()) get their own line in the daily cash close --
they count toward people and boleta totals, but never add to expected cash,
since they are always paid by Webpay and never Efectivo.

This module never imports `romeral` (it would pull in Tkinter and create a
real sqlite3 file on disk as an import side effect -- see
desktop/conftest.py). Instead it builds a throwaway in-memory sqlite3
connection with just the `ventas` table shape `calcular_resumen_cierre`
reads, including the `origen` column added in Task 19.
"""
import sqlite3

import pytest

from cierre_caja import calcular_resumen_cierre

FECHA = '2026-11-23'


@pytest.fixture
def db_with_online_and_cash_sales():
    conn = sqlite3.connect(':memory:')
    conn.execute('''CREATE TABLE ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT NOT NULL,
        cantidad INTEGER NOT NULL, precio INTEGER NOT NULL,
        total INTEGER NOT NULL, medio TEXT NOT NULL,
        tipo TEXT NOT NULL DEFAULT 'Entrada General',
        estado_boleta TEXT NOT NULL DEFAULT 'PENDIENTE_INTEGRACION',
        folio_dte TEXT,
        origen TEXT NOT NULL DEFAULT 'PRESENCIAL'
    )''')
    rows = [
        # fecha, cantidad, precio, total, medio, tipo, estado_boleta, folio_dte, origen
        (f'{FECHA} 10:00:00', 2, 12000, 24000, 'Webpay', 'Entrada General', 'EMITIDA', '100', 'ONLINE'),
        (f'{FECHA} 11:00:00', 3, 12000, 36000, 'Efectivo', 'Entrada General', 'EMITIDA', '101', 'PRESENCIAL'),
        (f'{FECHA} 12:00:00', 1, 15000, 15000, 'Tarjeta', 'Alojamiento', 'EMITIDA', '102', 'PRESENCIAL'),
    ]
    conn.executemany(
        'INSERT INTO ventas(fecha,cantidad,precio,total,medio,tipo,estado_boleta,folio_dte,origen) '
        'VALUES (?,?,?,?,?,?,?,?,?)',
        rows,
    )
    conn.commit()
    yield conn
    conn.close()


def test_cierre_includes_online_line_with_people_and_invoice_count(db_with_online_and_cash_sales):
    resumen = calcular_resumen_cierre(db_with_online_and_cash_sales, fecha=FECHA)
    assert resumen['online']['personas'] == 2
    assert resumen['online']['boletas'] == 1
    assert resumen['online']['total'] == 24000


def test_cierre_online_total_does_not_add_to_expected_cash(db_with_online_and_cash_sales):
    resumen = calcular_resumen_cierre(db_with_online_and_cash_sales, fecha=FECHA)
    assert resumen['efectivo_esperado'] == resumen['efectivo_esperado_sin_online']
    # The only Efectivo row is the presencial one; online (Webpay) never counts.
    assert resumen['efectivo_esperado'] == 36000


def test_presencial_breakdown_excludes_online_rows(db_with_online_and_cash_sales):
    resumen = calcular_resumen_cierre(db_with_online_and_cash_sales, fecha=FECHA)
    # 'Entrada General' presencial bucket must not include the online row's
    # people/total, even though both share tipo='Entrada General'.
    assert resumen['presencial']['Entrada General']['personas'] == 3
    assert resumen['presencial']['Entrada General']['total'] == 36000
    assert resumen['presencial']['Entrada General']['ventas'] == 1
    assert 'Cabañas' in resumen['presencial']  # Alojamiento is renamed for display.


def test_grand_totals_include_online_as_real_revenue(db_with_online_and_cash_sales):
    resumen = calcular_resumen_cierre(db_with_online_and_cash_sales, fecha=FECHA)
    assert resumen['ventas'] == 3
    assert resumen['personas'] == 6
    assert resumen['total'] == 75000


def test_ignores_other_dates_and_cancelled_test_sales(db_with_online_and_cash_sales):
    conn = db_with_online_and_cash_sales
    conn.execute(
        "INSERT INTO ventas(fecha,cantidad,precio,total,medio,tipo,estado_boleta,folio_dte,origen) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        ('2026-11-24 09:00:00', 5, 1000, 5000, 'Efectivo', 'Entrada General', 'EMITIDA', '200', 'PRESENCIAL'),
    )
    conn.execute(
        "INSERT INTO ventas(fecha,cantidad,precio,total,medio,tipo,estado_boleta,folio_dte,origen) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (f'{FECHA} 13:00:00', 1, 1000, 1000, 'Efectivo', 'Entrada General', 'ANULADA_PRUEBA', '201', 'PRESENCIAL'),
    )
    conn.commit()
    resumen = calcular_resumen_cierre(conn, fecha=FECHA)
    assert resumen['ventas'] == 3
    assert resumen['total'] == 75000
