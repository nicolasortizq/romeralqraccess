"""Copia de seguridad consistente SQLite y archivos de configuración; no modifica origen."""
from pathlib import Path
import sqlite3, shutil, datetime, sys
origen=Path.home()/'Documents'/'ROMERAL_Datos'
if not origen.is_dir():
 print('No existe ROMERAL_Datos; no se creó un respaldo.');sys.exit(1)
fecha=datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
destino=Path.home()/'Documents'/f'ROMERAL_Respaldo_{fecha}'
destino.mkdir(exist_ok=False)
db=origen/'romeral.sqlite3'
if db.exists():
 try:
  with sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True) as c:
   with sqlite3.connect(destino/'romeral.sqlite3') as d:
    c.backup(d)
 except Exception:
  shutil.rmtree(destino)
  raise
for f in origen.iterdir():
 if f.is_file() and f.name not in ('romeral.sqlite3','romeral.sqlite3-wal','romeral.sqlite3-shm'):
  shutil.copy2(f,destino/f.name)
print('Respaldo creado:',destino)
print('No se copiaron credenciales del llavero del sistema.')
