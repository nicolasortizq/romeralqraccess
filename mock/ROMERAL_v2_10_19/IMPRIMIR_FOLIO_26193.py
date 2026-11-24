"""Imprime exclusivamente DTE 39 folio 26193 ya emitido; jamás llama Procesar."""
import sqlite3
from pathlib import Path
from datetime import datetime
from tkinter import Tk, messagebox
from recuperacion_pdf import recuperar
from impresion_oficial import imprimir_pdf_oficial

DB=Path.home()/'Documents'/'ROMERAL_Datos'/'romeral.sqlite3'
FOLIO='26193'

def ejecutar():
    if not DB.is_file():
        raise RuntimeError('No se encontró la base de datos ROMERAL_Datos.')
    with sqlite3.connect(DB,timeout=15) as db:
        rows=db.execute("SELECT id,fecha,cantidad,total,medio,tipo FROM ventas WHERE folio_dte=? AND tipo_dte=39 AND estado_boleta='EMITIDA'",(FOLIO,)).fetchall()
        if len(rows)!=1:
            raise RuntimeError('No existe exactamente una venta EMITIDA para DTE 39 folio 26193. No se imprimirá.')
        venta,fecha,cantidad,total,medio,tipo=rows[0]
        if (cantidad,total,medio,tipo)!=(1,12000,'Efectivo','Entrada General'):
            raise RuntimeError('Los datos registrados no coinciden con la prueba autorizada. No se imprimirá.')
    from romeral import config
    impresora=config('impresora_80mm') or None
    return venta,impresora

def main():
    root=Tk();root.withdraw()
    try:
        venta,impresora=ejecutar()
        if not messagebox.askyesno('ROMERAL · Impresión folio 26193',
                'Imprimir la boleta YA EMITIDA DTE 39 folio 26193 por $12.000 en impresora térmica de 80 mm?\n\nNO se emite otra boleta.'):
            return
        ruta=recuperar(venta)
        resultado=imprimir_pdf_oficial(ruta,impresora,venta_id=venta)
        with sqlite3.connect(DB,timeout=15) as db:
            db.execute('INSERT INTO eventos_dte(venta_id,fecha,evento,detalle) VALUES(?,?,?,?)',
                       (venta,datetime.now().isoformat(timespec='seconds'),'IMPRESION_FOLIO_EXISTENTE',
                        'Folio 26193 enviado a cola de impresión desde herramienta de prueba sin emisión SOAP'))
        messagebox.showinfo('ROMERAL · Impresión enviada',resultado+'\n\nVerifica físicamente el papel y el timbre.')
    except Exception as exc:
        messagebox.showerror('ROMERAL · No se imprimió',str(exc)+'\n\nNo se emitió ninguna boleta nueva.')
    finally:
        root.destroy()

if __name__=='__main__':main()
