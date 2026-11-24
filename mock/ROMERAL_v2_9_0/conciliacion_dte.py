"""ROMERAL: conciliación LOCAL DTE 39, sin red ni emisión.
Solo permite confirmar emisión con evidencia externa verificada y explícita.
No consulta ni modifica credenciales. No invoca Procesar.
"""
from datetime import datetime
import sqlite3

ESTADOS = ('PENDIENTE_INTEGRACION','RESERVADA','INCIERTA','EMITIDA','REVISAR')

def preparar(db):
    db.execute("""CREATE TABLE IF NOT EXISTS conciliacion_eventos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        venta_id INTEGER NOT NULL,
        fecha TEXT NOT NULL,
        estado_anterior TEXT NOT NULL,
        estado_nuevo TEXT NOT NULL,
        origen TEXT NOT NULL,
        referencia_evidencia TEXT NOT NULL,
        folio TEXT,
        FOREIGN KEY(venta_id) REFERENCES ventas(id)
    )""")
    db.execute('CREATE INDEX IF NOT EXISTS idx_conciliacion_venta ON conciliacion_eventos(venta_id)')

def _cambiar(db, venta_id, destino, origen, evidencia, folio=None):
    if destino not in ESTADOS: raise ValueError('Estado desconocido')
    if not isinstance(venta_id,int) or venta_id<=0: raise ValueError('Venta inválida')
    if not isinstance(evidencia,str) or not evidencia.strip() or len(evidencia)>500: raise ValueError('Se exige referencia de evidencia')
    if origen not in ('REVISION_MANUAL','RESPUESTA_VERIFICADA'): raise ValueError('Origen inválido')
    actual=db.execute("""SELECT c.estado,c.folio,v.estado_boleta,v.referencia_venta
        FROM control_emision c JOIN ventas v ON v.id=c.venta_id WHERE c.venta_id=?""",(venta_id,)).fetchone()
    if actual is None: raise ValueError('Venta sin control DTE')
    previo,folio_actual,estado_venta,ref=actual
    if estado_venta=='ANULADA_PRUEBA': raise ValueError('Venta anulada')
    if previo=='EMITIDA': raise ValueError('Emisión ya confirmada: inmutable')
    if destino=='EMITIDA':
        if origen!='RESPUESTA_VERIFICADA': raise ValueError('No se puede confirmar emisión manualmente sin respuesta verificada')
        if previo not in ('RESERVADA','INCIERTA','REVISAR'): raise ValueError('Estado previo no apto para confirmar')
        if not isinstance(folio,str) or not folio.isdecimal() or int(folio)<=0: raise ValueError('Folio inválido')
        if db.execute("SELECT 1 FROM control_emision WHERE folio=? AND venta_id<>? LIMIT 1",(folio,venta_id)).fetchone():
            raise ValueError('Folio ya asociado a otra venta')
    else:
        if folio is not None: raise ValueError('Folio solo con emisión verificada')
        if destino=='RESERVADA' and previo!='PENDIENTE_INTEGRACION': raise ValueError('Reserva no permitida')
        if destino=='INCIERTA' and previo!='RESERVADA': raise ValueError('Incertidumbre no permitida')
        if destino=='REVISAR' and previo not in ('RESERVADA','INCIERTA'): raise ValueError('Revisión no permitida')
        if destino=='PENDIENTE_INTEGRACION': raise ValueError('No se permite reiniciar estado ni reenvío')
    ahora=datetime.now().isoformat(timespec='seconds')
    with db:
        resultado=db.execute("""UPDATE control_emision SET estado=?,folio=?,actualizado=?
           WHERE venta_id=? AND estado=?""",(destino,folio if destino=='EMITIDA' else folio_actual,ahora,venta_id,previo))
        if resultado.rowcount!=1: raise RuntimeError('Estado cambió durante conciliación')
        db.execute("""INSERT INTO conciliacion_eventos
          (venta_id,fecha,estado_anterior,estado_nuevo,origen,referencia_evidencia,folio)
          VALUES (?,?,?,?,?,?,?)""",(venta_id,ahora,previo,destino,origen,evidencia.strip(),folio))
        # Solo una confirmación con evidencia actualiza la venta tributaria.
        if destino=='EMITIDA':
            db.execute("""UPDATE ventas SET estado_boleta='EMITIDA',folio_dte=?,fecha_emision=?
              WHERE id=? AND estado_boleta!='ANULADA_PRUEBA' """,(folio,ahora,venta_id))
    return destino

def reservar(db,venta_id,evidencia):
    """Reserva LOCAL para un futuro proceso de emisión; no envía nada."""
    return _cambiar(db,venta_id,'RESERVADA','REVISION_MANUAL',evidencia)

def marcar_incierta(db,venta_id,evidencia):
    return _cambiar(db,venta_id,'INCIERTA','REVISION_MANUAL',evidencia)

def enviar_revision(db,venta_id,evidencia):
    return _cambiar(db,venta_id,'REVISAR','REVISION_MANUAL',evidencia)

def confirmar_respuesta_verificada(db,venta_id,folio,evidencia):
    """API interna: NO usar con XML no validado o por simple consulta CAF."""
    return _cambiar(db,venta_id,'EMITIDA','RESPUESTA_VERIFICADA',evidencia,folio)

def consultar(db):
    return db.execute("""SELECT c.venta_id,c.referencia,c.estado,c.folio,c.actualizado
      FROM control_emision c ORDER BY c.venta_id DESC""").fetchall()
