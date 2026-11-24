"""Control conservador de avisos de folios, sin estimar ni inventar saldos."""
import json
import re
from datetime import datetime
from pathlib import Path

# Las expresiones exigen mención de folios y un agotamiento explícito.
PATRONES = (
    r"(?:sin|no (?:hay|quedan|existen|dispone de))\s+folios?",
    r"folios?\s+(?:agotados?|insuficientes?|no disponibles?|terminados?)",
    r"(?:agotamiento|falta)\s+de\s+folios?",
    r"(?:no (?:hay|quedan|existen))\s+folios?\s+(?:disponibles?)?",
)

def es_agotamiento_explicito(texto):
    # Se usa únicamente sobre mensajes del proveedor, no sobre textos genéricos.
    if not isinstance(texto,str):return False
    return any(re.search(p,texto,re.I) for p in PATRONES)

def registrar_alerta(carpeta,venta_id,mensaje):
    if not es_agotamiento_explicito(mensaje):return False
    carpeta=Path(carpeta)
    registro={'fecha':datetime.now().isoformat(timespec='seconds'),
              'venta_id':int(venta_id),'estado':'POSIBLE_AGOTAMIENTO',
              'origen':'respuesta_emision','detalle':mensaje[:1200]}
    with (carpeta/'romeral_alertas_folios.jsonl').open('a',encoding='utf-8') as f:
        f.write(json.dumps(registro,ensure_ascii=False)+'\n')
    return True

def leer_estado(carpeta):
    ruta=Path(carpeta)/'romeral_alertas_folios.jsonl'
    if not ruta.exists():return None
    try:
        lineas=ruta.read_text(encoding='utf-8').splitlines()
        for linea in reversed(lineas):
            try:return json.loads(linea)
            except (ValueError,TypeError):continue
    except OSError:pass
    return None

def mensaje_alerta(estado):
    base=('No existe una consulta de saldo de folios confirmada por Facturacion.com.\n'
          'ROMERAL no puede mostrar una cantidad real de folios restantes ni\n'
          'advertir preventivamente por 500 o 100 sin esa información.\n\n'
          'Consulta el stock de CAF / folios DTE 39 en el portal del proveedor\n'
          'y solicita nuevos folios con anticipación.\n')
    if not estado:return base+'\nNo hay alertas de agotamiento registradas localmente.'
    return base+('\nÚLTIMA ALERTA REGISTRADA (requiere comprobación):\n'
                 f"Fecha: {estado.get('fecha','—')}\n"
                 f"Venta: {estado.get('venta_id','—')}\n"
                 f"Detalle: {estado.get('detalle','—')[:500]}\n\n"
                 'Verifica el estado de la venta antes de repetir cualquier operación.')
