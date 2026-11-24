"""Recuperación de PDF oficial con sondeo temprano, sin reemitir DTE."""
import time
import json
from datetime import datetime
from pathlib import Path
from recuperacion_pdf import recuperar, DATA

# Sondeo inicial más ágil, sin peticiones paralelas ni reemisión.
# Pausas posteriores conservadoras para no saturar al proveedor.
ESPERAS_SEGUNDOS = (0.5, 0.75, 1.5, 2, 3, 4, 5, 6, 8)


def _log_tiempo(venta_id, intento, duracion, estado, pausa=0):
    """Solo telemetría de tiempos, sin URL, credenciales ni contenido tributario."""
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        with (DATA / 'romeral_tiempos_impresion.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps({'fecha': datetime.now().isoformat(timespec='seconds'),
                                'venta': int(venta_id), 'intento': intento,
                                'segundos_consulta': round(duracion, 2),
                                'estado': estado, 'espera_siguiente': pausa}, ensure_ascii=False) + '\n')
    except OSError:
        pass


def recuperar_con_espera(venta_id, notificar=None, dormir=time.sleep, obtener=recuperar):
    """Hasta diez consultas, con esperas progresivas. Nunca reintenta emisión."""
    ultimo_error = None
    for intento in range(len(ESPERAS_SEGUNDOS) + 1):
        inicio = time.monotonic()
        try:
            ruta = Path(obtener(venta_id))
            if not ruta.is_file():
                raise RuntimeError('El PDF recuperado no es válido')
            with ruta.open('rb') as f:
                firma=f.read(5)
            if firma != b'%PDF-':
                raise RuntimeError('El PDF recuperado no es válido')
            _log_tiempo(venta_id, intento + 1, time.monotonic() - inicio, 'PDF_RECUPERADO')
            return ruta
        except Exception as exc:
            ultimo_error = exc
            detalle = str(exc).lower()
            transitorio = (
                'el enlace no devolvió un pdf oficial válido' in detalle
                or 'descarga pdf: http 404' in detalle
                or 'descarga pdf: http 403' in detalle
                or 'descarga pdf: http 429' in detalle
                or 'descarga pdf: http 503' in detalle
                or 'descarga pdf: http 502' in detalle
                or 'descarga pdf: http 500' in detalle
                or 'obtenerlink no devolvió una url https reconocible' in detalle
                or 'el proveedor no entregó un enlace pdf válido' in detalle
                or 'el pdf recuperado no es válido' in detalle
            )
            pausa = ESPERAS_SEGUNDOS[intento] if transitorio and intento < len(ESPERAS_SEGUNDOS) else 0
            _log_tiempo(venta_id, intento + 1, time.monotonic() - inicio,
                        'PDF_NO_DISPONIBLE' if transitorio else 'ERROR_NO_TRANSITORIO', pausa)
            if not pausa:
                break
            if notificar:
                notificar(intento + 1, len(ESPERAS_SEGUNDOS) + 1, pausa)
            dormir(pausa)
    raise RuntimeError(
        f'No se pudo recuperar el PDF oficial tras los intentos de espera: {ultimo_error}. '
        'El DTE permanece emitido; NO registrar otra venta. Reimprimir por folio más tarde.'
    ) from ultimo_error
