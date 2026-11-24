"""Configura nombre exacto de la impresora sin abrir ROMERAL ni emitir DTE."""
import os
import sqlite3
from pathlib import Path
from impresion_windows import impresoras_windows, _sumatra

if os.name != 'nt':
    raise SystemExit('Esta herramienta se ejecuta solamente en Windows.')
print('\nROMERAL - CONFIGURACION DE IMPRESORA WINDOWS\n')
nombres = impresoras_windows()
for i, nombre in enumerate(nombres, 1):
    print(f'{i}. {nombre}')
if not nombres:
    raise SystemExit('Instala primero el controlador de la impresora en Windows.')
try:
    print('\nSumatraPDF detectado:', _sumatra())
except RuntimeError as exc:
    print('\nAVISO:', exc)
seleccion = input('\nNumero de la impresora termica de 80 mm (ENTER cancela): ').strip()
if not seleccion:
    raise SystemExit('Sin cambios.')
try:
    indice = int(seleccion) - 1
    if not 0 <= indice < len(nombres):
        raise ValueError
except ValueError:
    raise SystemExit('Numero no valido. Sin cambios.')
carpeta = Path.home() / 'Documents' / 'ROMERAL_Datos'
carpeta.mkdir(parents=True, exist_ok=True)
base = carpeta / 'romeral.sqlite3'
with sqlite3.connect(base, timeout=15) as db:
    db.execute('CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
    db.execute("INSERT INTO config (key,value) VALUES ('impresora_80mm',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (nombres[indice],))
print('\nImpresora configurada:', nombres[indice])
print('Esta operacion NO imprime ni emite boletas.')
