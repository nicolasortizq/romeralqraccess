"""Registro mínimo de tiempos; no almacena datos personales, PDF ni credenciales."""
import json
import threading
from datetime import datetime
from pathlib import Path

_ARCHIVO = Path.home() / 'Documents' / 'ROMERAL_Datos' / 'romeral_diagnostico_etapas.jsonl'
_LOCK = threading.Lock()

def registrar_tiempo(venta_id, etapa, **datos):
    try:
        registro = {'fecha': datetime.now().isoformat(timespec='seconds'), 'venta': int(venta_id), 'etapa': str(etapa)}
        for clave, valor in datos.items():
            if clave in ('segundos', 'total_desde_inicio', 'resultado', 'error'):
                registro[clave] = valor
        with _LOCK:
            _ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
            with _ARCHIVO.open('a', encoding='utf-8') as f:
                f.write(json.dumps(registro, ensure_ascii=False) + '\n')
    except (OSError, ValueError, TypeError):
        pass  # El diagnóstico nunca puede bloquear una venta.
