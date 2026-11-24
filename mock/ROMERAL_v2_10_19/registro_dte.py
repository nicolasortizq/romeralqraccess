"""Registro local de DTE asociado a ventas. SIN ENVÍO, SIN RED."""
from datetime import datetime
import sqlite3

PENDIENTE = 'PENDIENTE_INTEGRACION'

def crear_tabla(db):
    db.execute("""CREATE TABLE IF NOT EXISTS control_emision (
        venta_id INTEGER PRIMARY KEY,
        referencia TEXT NOT NULL UNIQUE,
        estado TEXT NOT NULL CHECK(estado IN ('PENDIENTE_INTEGRACION','RESERVADA','INCIERTA','EMITIDA','REVISAR')),
        folio TEXT,
        creado TEXT NOT NULL,
        actualizado TEXT NOT NULL,
        FOREIGN KEY(venta_id) REFERENCES ventas(id)
    )""")

def registrar_venta(db, venta_id, referencia):
    """Debe llamarse dentro de la MISMA transacción que inserta la venta."""
    if not isinstance(venta_id, int) or venta_id <= 0 or not referencia or not referencia.strip():
        raise ValueError('Venta o referencia inválida')
    venta = db.execute('SELECT referencia_venta, estado_boleta FROM ventas WHERE id=?', (venta_id,)).fetchone()
    if not venta or venta[0] != referencia or venta[1] != PENDIENTE:
        raise ValueError('Venta no elegible para preemisión')
    ahora = datetime.now().isoformat(timespec='seconds')
    db.execute('INSERT INTO control_emision (venta_id,referencia,estado,creado,actualizado) VALUES (?,?,?,?,?)',
               (venta_id, referencia, PENDIENTE, ahora, ahora))

def resumen(db):
    return db.execute('SELECT estado,COUNT(*) FROM control_emision GROUP BY estado ORDER BY estado').fetchall()
