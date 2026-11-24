"""Habilitación local supervisada. No emite boletas ni lee claves."""
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from tkinter import Tk, messagebox

DATA=Path.home()/'Documents'/'ROMERAL_Datos'
CFG=DATA/'facturacion_produccion.json'
DB=DATA/'romeral.sqlite3'

def main():
 root=Tk();root.withdraw()
 try:
  if not CFG.is_file() or not DB.is_file():
   raise RuntimeError('Falta la configuración de producción o la base de datos ROMERAL.')
  data=json.loads(CFG.read_text(encoding='utf-8'))
  if data.get('ambiente')!='produccion' or not data.get('rut') or not data.get('usuario'):
   raise RuntimeError('Configuración de producción incompleta.')
  with sqlite3.connect(f'file:{DB.as_posix()}?mode=ro',uri=True) as db:
   tablas={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
   if 'intentos_soap_dte' not in tablas or 'ventas' not in tablas:
    raise RuntimeError('No existe la bitácora de emisión requerida. Abrir ROMERAL y revisar instalación.')
   pendiente=db.execute("SELECT venta_id,estado FROM intentos_soap_dte WHERE estado IN ('INCIERTO','ENVIO_INICIADO') LIMIT 1").fetchone()
   if pendiente:
    raise RuntimeError(f'Venta {pendiente[0]} en estado {pendiente[1]}. Conciliar antes de activar.')
  if data.get('emision_habilitada') is True:
   messagebox.showinfo('ROMERAL','La emisión automática ya está habilitada. No se hicieron cambios.');return
  if not messagebox.askyesno('ROMERAL · ACTIVACIÓN REAL',
    'ATENCIÓN: habilitará emisión tributaria REAL para TODAS las ventas que registre ROMERAL.\n\n'
    'Cada pulsación de Registrar venta podrá generar un DTE 39 en Facturacion.com.\n\n'
    '¿Confirmas que ROMERAL está cerrado, que tienes respaldo y que deseas activar producción?'):
   return
  respaldo=CFG.with_name('facturacion_produccion_antes_activar_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.json')
  respaldo.write_bytes(CFG.read_bytes())
  data['emision_habilitada']=True
  temporal=CFG.with_suffix('.json.tmp')
  with temporal.open('w',encoding='utf-8') as f:
   json.dump(data,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
  os.replace(temporal,CFG)
  messagebox.showinfo('ROMERAL','Emisión automática habilitada. Abre ROMERAL y registra ventas reales solo cuando corresponda.')
 except Exception as e:
  messagebox.showerror('Activación detenida',str(e))
 finally:root.destroy()
if __name__=='__main__':main()
