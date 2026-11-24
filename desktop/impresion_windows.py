"""Envío seguro de PDF a una impresora térmica instalada en Windows.
Requiere SumatraPDF (gratuito) y controlador de impresora de Windows.
No interpreta ni altera el documento tributario.
"""
import os
import shutil
import subprocess
import time
import threading
from pathlib import Path


def _sumatra():
    opciones = [os.environ.get('ROMERAL_SUMATRA_PDF', ''), shutil.which('SumatraPDF.exe')]
    for base in (os.environ.get('PROGRAMFILES', ''), os.environ.get('PROGRAMFILES(X86)', ''),
                 os.environ.get('LOCALAPPDATA', '')):
        if base:
            opciones += [str(Path(base) / 'SumatraPDF' / 'SumatraPDF.exe'),
                         str(Path(base) / 'SumatraPDF.exe')]
    for ruta in opciones:
        if ruta and Path(ruta).is_file():
            return str(Path(ruta))
    raise RuntimeError('No se encontró SumatraPDF. Instálalo en Windows para impresión automática y vuelve a ejecutar la prueba de impresión.')


_IMPRESORAS_CACHE = {"nombres": None, "hasta": 0.0}
_IMPRESORAS_LOCK = threading.Lock()

def impresoras_windows(forzar=False):
    # Evita lanzar PowerShell para cada boleta. Caché breve; refrescar ante cambios.
    with _IMPRESORAS_LOCK:
        if not forzar and _IMPRESORAS_CACHE["nombres"] is not None and time.monotonic() < _IMPRESORAS_CACHE["hasta"]:
            return list(_IMPRESORAS_CACHE["nombres"])
    # PowerShell retorna nombres desde el spooler, no desde la impresora predeterminada.
    comando = ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
               '[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; Get-Printer | Select-Object -ExpandProperty Name']
    try:
        r = subprocess.run(comando, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=12)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError('No se pudo consultar la lista de impresoras de Windows.') from exc
    if r.returncode:
        raise RuntimeError('Windows no pudo enumerar impresoras: ' + (r.stderr or '').strip())
    nombres = [x.strip() for x in r.stdout.splitlines() if x.strip()]
    with _IMPRESORAS_LOCK:
        _IMPRESORAS_CACHE.update(nombres=nombres, hasta=time.monotonic()+60)
    return nombres


def elegir_impresora(configurada=None):
    nombres = impresoras_windows()
    if configurada:
        for n in nombres:
            if n.casefold() == configurada.strip().casefold():
                return n
        raise RuntimeError('La impresora configurada «' + configurada + '» no aparece en Windows. Instaladas: ' + ', '.join(nombres))
    candidatas = [n for n in nombres if any(s in n.lower() for s in ('pos-80', 'pos_80', 'pos80', '3nstar', 'thermal'))]
    if len(candidatas) == 1:
        return candidatas[0]
    raise RuntimeError('Configura el nombre exacto de la impresora térmica en ROMERAL (impresora_80mm). Impresoras instaladas: ' + ', '.join(nombres))


def enviar_pdf_windows(ruta, impresora=None):
    archivo = Path(ruta).expanduser().resolve()
    if not archivo.is_file() or archivo.suffix.lower() != '.pdf' or archivo.read_bytes()[:5] != b'%PDF-':
        raise ValueError('No se encontró un PDF válido para imprimir.')
    inicio_preparacion = time.monotonic()
    destino = elegir_impresora(impresora)
    ejecutable = _sumatra()
    segundos_preparacion = time.monotonic() - inicio_preparacion
    inicio_spool = time.monotonic()
    # El proceso termina después de entregar el trabajo al spooler; esto NO confirma salida física.
    args = [ejecutable, '-silent', '-print-to', destino, '-print-settings', 'noscale', str(archivo)]
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=45, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError('La impresora tardó demasiado en aceptar el PDF; revisa la cola antes de reintentar.') from exc
    if r.returncode:
        raise RuntimeError('SumatraPDF no pudo enviar el documento a «' + destino + '»: ' + (r.stderr or r.stdout or str(r.returncode)).strip())
    return ('Trabajo enviado a la cola de Windows «' + destino + '». '
            f'Preparación: {segundos_preparacion:.2f}s; envío a cola: {time.monotonic()-inicio_spool:.2f}s. '
            'Comprueba la salida física, el ancho de papel y el timbre.')
