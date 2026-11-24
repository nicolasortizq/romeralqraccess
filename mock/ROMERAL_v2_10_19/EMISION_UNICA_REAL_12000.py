"""Emisión tributaria REAL de UNA entrada general por $12.000, efectivo.
No modifica el bloqueo general. No reintentar tras un resultado incierto.
"""
import sqlite3, uuid, sys, traceback
from datetime import datetime
from pathlib import Path
from tkinter import Tk, messagebox
from validacion_produccion import CONFIG
from EMISION_REAL_CONTROLADA import operacion
from registro_dte import registrar_venta

DATA=Path.home()/'Documents'/'ROMERAL_Datos'
DB=DATA/'romeral.sqlite3'

def ejecutar():
    if not DB.exists() or not CONFIG.exists():
        raise RuntimeError('Falta la base ROMERAL o la configuración de producción.')
    import json
    cfg=json.loads(CONFIG.read_text(encoding='utf-8'))
    if cfg.get('ambiente')!='produccion' or cfg.get('emision_habilitada') is True:
        raise RuntimeError('Esta prueba exige ambiente producción con emisión GENERAL bloqueada (false).')
    with sqlite3.connect(DB,timeout=20) as db:
        db.execute('PRAGMA busy_timeout=20000')
        db.execute('PRAGMA foreign_keys=ON')
        # Autorización permanente en la base: una vez creada, no puede crearse otra.
        db.execute("""CREATE TABLE IF NOT EXISTS autorizacion_emision_unica (
            id INTEGER PRIMARY KEY CHECK(id=1), venta_id INTEGER NOT NULL UNIQUE,
            estado TEXT NOT NULL CHECK(estado IN ('AUTORIZADA','CONSUMIDA')),
            fecha TEXT NOT NULL)""")
        db.commit()
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM autorizacion_emision_unica WHERE id=1').fetchone():
            raise RuntimeError('Ya existe una autorización única. NO repetir ni borrar registros.')
        if db.execute("SELECT 1 FROM control_emision WHERE estado IN ('RESERVADA','INCIERTA','REVISAR') LIMIT 1").fetchone():
            raise RuntimeError('Hay emisiones por revisar. No se permite esta prueba.')
        ahora=datetime.now().isoformat(timespec='seconds')
        ref=str(uuid.uuid4())
        cur=db.execute("""INSERT INTO ventas(fecha,cantidad,precio,total,medio,tipo,estado_boleta,referencia_venta,tipo_dte)
            VALUES(?,?,?,?,?,?,?,?,?)""",(ahora,1,12000,12000,'Efectivo','Entrada General','PENDIENTE_INTEGRACION',ref,39))
        vid=cur.lastrowid
        registrar_venta(db,vid,ref)
        db.execute("INSERT INTO autorizacion_emision_unica(id,venta_id,estado,fecha) VALUES(1,?,'AUTORIZADA',?)",(vid,ahora))
        db.commit()
    # A partir de aquí la venta ya existe: NO repetir aunque falle la conexión.
    return vid,operacion(vid,f'EMITIR {vid} 12000',autorizacion_unica=True)

def main():
    root=Tk();root.withdraw()
    if not messagebox.askyesno('ROMERAL · DTE 39 REAL',
        'ATENCIÓN: esta acción EMITE UNA BOLETA TRIBUTARIA REAL.\n'
        'Entrada General · 1 persona · Efectivo · $12.000.\n\n'
        'Cierra ROMERAL antes de continuar.\n'
        'Se registra una venta y se hace UN SOLO envío a Facturacion.com.\n'
        'Si falla o queda incierto, NO repitas la operación.\n\n¿Autorizar ahora?'):
        return
    try:
        vid,resultado=ejecutar()
        messagebox.showinfo('Resultado DTE 39 · venta '+str(vid),resultado)
        print('VENTA:',vid,'\n',resultado)
        if 'RESPUESTA SOAP CONFIRMADA' in resultado:
            messagebox.showinfo('Emisión confirmada',
                'La emisión fue confirmada en ROMERAL. Comprueba el folio en Facturacion.com.\n'
                'Para esta operación controlada NO se imprime automáticamente; '                'reimprime el PDF oficial una vez verificado el folio. No emitas otra boleta.')
    except Exception as e:
        messagebox.showerror('Detenido · NO REINTENTAR',str(e)+'\n\nNo repitas el proceso sin revisar el registro y el portal.')
        print('ERROR · NO REINTENTAR:',repr(e),file=sys.stderr)
    finally:root.destroy()

if __name__=='__main__':main()
