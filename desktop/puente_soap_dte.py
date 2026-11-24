"""Puente seguro entre una respuesta Procesar previamente obtenida y control_emision.
No realiza conexiones, no llama Procesar y no almacena secretos.
La respuesta debe ser aportada por una operación explícitamente autorizada.
"""
import hashlib
import sqlite3
from RESPUESTAS_SOAP_DTE import analizar_respuesta
from conciliacion_dte import confirmar_respuesta_verificada, enviar_revision, marcar_incierta


def conciliar_respuesta(db: sqlite3.Connection, venta_id: int, xml: str):
    """Conciliar una sola respuesta SOAP de DTE39 con una venta RESERVADA.

    Éxito explícito => EMITIDA; rechazo => REVISAR; ambiguo => INCIERTA.
    Una respuesta de una operación no enviada nunca debe usarse aquí.
    """
    if not isinstance(venta_id, int) or venta_id < 1:
        raise ValueError('Identificador de venta inválido')
    actual = db.execute('''SELECT c.estado, v.estado_boleta, v.tipo_dte
        FROM control_emision c JOIN ventas v ON v.id=c.venta_id
        WHERE c.venta_id=?''', (venta_id,)).fetchone()
    if actual is None:
        raise ValueError('Venta sin control tributario')
    estado, estado_venta, tipo = actual
    if estado != 'RESERVADA' or estado_venta == 'ANULADA_PRUEBA' or tipo != 39:
        raise ValueError('La venta no está reservada para conciliar DTE 39')
    if not isinstance(xml, str) or len(xml) > 1_000_000:
        raise ValueError('Respuesta inválida')
    resultado = analizar_respuesta(xml)
    evidencia = 'SOAP-Procesar SHA256:' + hashlib.sha256(xml.encode('utf-8')).hexdigest()
    if resultado['estado'] == 'EMITIDA':
        confirmar_respuesta_verificada(db, venta_id, str(resultado['folio']), evidencia)
    elif resultado['estado'] == 'REVISAR':
        enviar_revision(db, venta_id, evidencia)
    else:
        marcar_incierta(db, venta_id, evidencia)
    return {'venta_id': venta_id, 'estado': resultado['estado'],
            'folio': resultado.get('folio'), 'evidencia': evidencia,
            'motivo': resultado['motivo']}
