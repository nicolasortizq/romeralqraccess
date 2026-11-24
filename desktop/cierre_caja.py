"""Cash-close aggregation for a single day's `ventas` rows.

Extracted from panel_cierre()'s `resumen()` closure in romeral.py so the
logic is testable with a plain sqlite3 connection, without pulling in
Tkinter (importing romeral.py has import-time side effects: it creates the
real gate sqlite3 file -- see desktop/conftest.py's docstring). This module
therefore keeps its own small copies of PAYMENTS and nombre_visible instead
of importing romeral, the same pattern cierre_termico.py already uses.

Business rule (CLAUDE.md, docs/PROYECTO.md 4.7): online redemptions
(origen='ONLINE', written by ventas_online.py's registrar_venta_online())
get their own line in the daily cash close -- they count toward people and
sales/invoice totals, but never add to expected cash. They are always paid
by Webpay, never Efectivo, so excluding them from efectivo_esperado happens
automatically via the `medio` filter; `efectivo_esperado_sin_online` below
recomputes the Efectivo total by excluding origen='ONLINE' explicitly, to
prove both paths agree.
"""

PAYMENTS = ('Efectivo', 'Webpay', 'Tarjeta')


def nombre_visible(tipo):
    return 'Cabañas' if tipo == 'Alojamiento' else tipo


def rows_changed(rows_before, rows_after):
    """True if the day's row-set changed between two reads.

    Used by panel_cierre()'s cerrar() right before the irreversible
    cierres_caja INSERT, to detect a venta registered or modified between
    opening the close screen and confirming it (e.g. another till selling a
    ticket, or an online redemption landing mid-review). Both arguments are
    the `rows` list calcular_resumen_cierre() returns (same column order),
    so this is a plain list-of-tuples comparison -- pulled out on its own
    because it is the single safety-critical line in the whole close flow
    and deserves a direct test, not just inspection.
    """
    return list(rows_before) != list(rows_after)


def calcular_resumen_cierre(conn, fecha):
    """Aggregate one day's `ventas` rows for the daily cash close.

    Returns a dict:
      rows: raw rows for the day (id, fecha, tipo, medio, cantidad, total,
        estado_boleta, folio_dte, origen), ordered by id. Callers that need
        to detect stale reads (panel_cierre()'s cerrar(), via rows_changed())
        or persist cierre_operaciones can use this as-is; the first 8
        columns match the shape the old inline query returned.
      medios: {Efectivo, Webpay, Tarjeta} totals, every origin included.
      presencial: per-tipo breakdown ({personas, ventas, total}) for
        origen != 'ONLINE' rows only, keyed by nombre_visible(tipo). Online
        rows are excluded so they are not silently folded into an in-person
        bucket (e.g. 'Entrada General').
      tipos: `presencial` plus an extra 'Online' key (same {personas,
        ventas, total} shape) for origen == 'ONLINE' rows, only present when
        there was at least one online sale that day. This is the dict meant
        for anything that gets persisted or printed as "the modality
        breakdown" (desglose_json, the thermal receipt, the history report)
        -- it must cover 100% of `total`/`personas`/`ventas` below, or the
        printed document stops reconciling with its own header. `presencial`
        stays online-free for the on-screen panel's separate "POR SERVICIO"
        + "ONLINE (no suma a efectivo esperado)" display.
      online: {personas, ventas, total} for origen == 'ONLINE' rows. Note:
        `ventas` here counts online redemption rows (ventas table entries),
        not confirmed-issued boletas -- online boleta issuance is
        asynchronous (estado_boleta starts as 'PENDIENTE_INTEGRACION'), so a
        row can exist here before its boleta is actually emitted. The name
        matches the `ventas` key already used by each presencial bucket.
      ventas, personas, total: grand totals across ALL rows, online
        included -- it is real revenue, even though it is not cash.
      efectivo_esperado: medios['Efectivo'].
      efectivo_esperado_sin_online: medios['Efectivo'] recomputed while
        explicitly excluding origen == 'ONLINE' rows. Must equal
        efectivo_esperado -- online sales are always medio='Webpay', so
        excluding them from Efectivo changes nothing. This key exists to
        make that fact an assertion, not an assumption.
    """
    rows = conn.execute(
        "SELECT id,fecha,tipo,medio,cantidad,total,estado_boleta,folio_dte,origen "
        "FROM ventas WHERE substr(fecha,1,10)=? AND estado_boleta != 'ANULADA_PRUEBA' "
        "ORDER BY id",
        (fecha,),
    ).fetchall()
    medios = {m: sum(int(r[5]) for r in rows if r[3] == m) for m in PAYMENTS}
    medios_sin_online = {
        m: sum(int(r[5]) for r in rows if r[3] == m and r[8] != 'ONLINE')
        for m in PAYMENTS
    }
    presencial = {}
    online = {'personas': 0, 'ventas': 0, 'total': 0}
    for _id, _fecha, tipo, _medio, personas, total, _estado, _folio, origen in rows:
        if origen == 'ONLINE':
            online['personas'] += int(personas)
            online['ventas'] += 1
            online['total'] += int(total)
        else:
            tipo_visible = nombre_visible(tipo)
            acumulado = presencial.setdefault(tipo_visible, {'personas': 0, 'total': 0, 'ventas': 0})
            acumulado['personas'] += int(personas)
            acumulado['total'] += int(total)
            acumulado['ventas'] += 1
    tipos = dict(presencial)
    if online['ventas']:
        tipos['Online'] = dict(online)
    return {
        'rows': rows,
        'medios': medios,
        'presencial': presencial,
        'tipos': tipos,
        'online': online,
        'ventas': len(rows),
        'personas': sum(int(r[4]) for r in rows),
        'total': sum(int(r[5]) for r in rows),
        'efectivo_esperado': medios['Efectivo'],
        'efectivo_esperado_sin_online': medios_sin_online['Efectivo'],
    }
