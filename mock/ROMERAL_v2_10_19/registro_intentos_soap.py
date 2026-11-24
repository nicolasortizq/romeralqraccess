"""Bitácora de intentos de envío DTE; NO transmite documentos.

Una solicitud de envío se marca antes de cualquier operación de red.
La ausencia de confirmación obliga a revisión manual, nunca a reintento.
"""
from datetime import datetime
import hashlib
import sqlite3


def crear_tabla(db: sqlite3.Connection):
    db.execute('''CREATE TABLE IF NOT EXISTS intentos_soap_dte (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      venta_id INTEGER NOT NULL UNIQUE,
      creado TEXT NOT NULL,
      estado TEXT NOT NULL CHECK(estado IN ('PREPARADO','ENVIO_INICIADO','CONFIRMADO','INCIERTO','RECHAZADO')),
      sha256_txt TEXT NOT NULL,
      sha256_respuesta TEXT,
      folio TEXT,
      FOREIGN KEY(venta_id) REFERENCES ventas(id)
    )''')


def preparar_intento(db, venta_id, txt):
    if not isinstance(venta_id, int) or venta_id <= 0 or not isinstance(txt, str) or not txt:
        raise ValueError('Solicitud inválida')
    row = db.execute('''SELECT c.estado,v.estado_boleta,v.tipo_dte
      FROM control_emision c JOIN ventas v ON v.id=c.venta_id WHERE c.venta_id=?''', (venta_id,)).fetchone()
    if row is None or row[0] != 'RESERVADA' or row[1] == 'ANULADA_PRUEBA' or row[2] != 39:
        raise ValueError('Venta no apta para emisión')
    digest = hashlib.sha256(txt.encode('utf-8')).hexdigest()
    with db:
        crear_tabla(db)
        db.execute('''INSERT INTO intentos_soap_dte(venta_id,creado,estado,sha256_txt)
          VALUES(?,?,?,?)''', (venta_id, datetime.now().isoformat(timespec='seconds'), 'PREPARADO', digest))
    return digest


def marcar_inicio_envio(db, venta_id):
    # Debe confirmarse en disco ANTES de llamar al servicio externo.
    with db:
        cur = db.execute('''UPDATE intentos_soap_dte SET estado='ENVIO_INICIADO'
          WHERE venta_id=? AND estado='PREPARADO' ''', (venta_id,))
        if cur.rowcount != 1:
            raise RuntimeError('Envío ya iniciado o no preparado; no reintentar')


def marcar_incierto(db, venta_id):
    with db:
        cur = db.execute('''UPDATE intentos_soap_dte SET estado='INCIERTO'
          WHERE venta_id=? AND estado='ENVIO_INICIADO' ''', (venta_id,))
        if cur.rowcount != 1:
            raise RuntimeError('Estado no apto para marcar incertidumbre')
