"""Simulador aislado de conciliación de ventas PLANO. No realiza llamadas de red."""
import json, sqlite3, uuid
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from xml.etree import ElementTree as ET

DATA=Path.home()/'Documents'/'ROMERAL_Datos'
DB=DATA/'pruebas_flujo_plano_v2_10.sqlite3'

def db():
    DATA.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(DB)
    c.execute('CREATE TABLE IF NOT EXISTS pruebas (id TEXT PRIMARY KEY, fecha TEXT NOT NULL, tipo TEXT NOT NULL, cantidad INTEGER NOT NULL, total INTEGER NOT NULL, estado TEXT NOT NULL, folio TEXT, respuesta TEXT)')
    c.commit()
    return c

def interpretar(xml):
    root=ET.fromstring(xml.strip())
    if root.tag!='WSPLANO': raise ValueError('La respuesta no corresponde a WSPLANO')
    resultado=(root.findtext('Resultado') or '').strip().lower()
    documento=root.find('./Detalle/Documento')
    if resultado!='true' or documento is None or (documento.findtext('Resultado') or '').strip().lower()!='true':
        raise ValueError('Facturacion.com no confirma éxito: revisar respuesta')
    if (documento.findtext('TipoDte') or '').strip()!='39':raise ValueError('El documento no es DTE 39')
    folio=(documento.findtext('Folio') or '').strip()
    if not folio.isdigit() or int(folio)<=0:raise ValueError('Folio no válido')
    return folio

def main():
    w=tk.Tk();w.title('ROMERAL v2.10.0 | Simulador aislado PLANO');w.geometry('850x650');w.configure(bg='#f5f7f9')
    tk.Label(w,text='ROMERAL · FLUJO DE VENTAS PLANO',font=('Arial',19,'bold'),bg='#f5f7f9').pack(pady=(18,5))
    tk.Label(w,text='Simulación local: NO emite DTE, NO imprime y NO registra ventas reales.',font=('Arial',11),bg='#f5f7f9',fg='#9b2b25').pack(pady=5)
    f=tk.Frame(w,bg='#f5f7f9');f.pack(pady=12)
    tk.Label(f,text='Personas:',bg='#f5f7f9').grid(row=0,column=0,padx=8)
    personas=tk.StringVar(value='1');tk.Entry(f,textvariable=personas,width=8).grid(row=0,column=1)
    tk.Label(f,text='Precio unitario ($):',bg='#f5f7f9').grid(row=0,column=2,padx=8)
    precio=tk.StringVar(value='1000');tk.Entry(f,textvariable=precio,width=12).grid(row=0,column=3)
    estado=tk.StringVar(value='Sin prueba registrada');tk.Label(w,textvariable=estado,font=('Arial',11,'bold'),bg='#f5f7f9',wraplength=760).pack(pady=8)
    tk.Label(w,text='Pega aquí una respuesta XML WSPLANO para conciliar la prueba local:',bg='#f5f7f9').pack()
    txt=tk.Text(w,height=11,width=95,font=('Consolas',10));txt.pack(padx=14,pady=6)
    current={'id':None}
    def crear():
        try:
            n=int(personas.get());p=int(precio.get())
            if not (1<=n<=99999 and 1<=p<=100000000 and n*p<=100000000):raise ValueError()
        except ValueError:
            messagebox.showerror('Valores incorrectos','Ingresa cantidad y precio válidos.',parent=w);return
        ident=str(uuid.uuid4())
        with db() as c:c.execute('INSERT INTO pruebas(id,fecha,tipo,cantidad,total,estado) VALUES(?,?,?,?,?,?)',(ident,datetime.now().isoformat(timespec='seconds'),'Entrada General',n,n*p,'PENDIENTE_CONCILIACION'))
        current['id']=ident;estado.set(f'Prueba local {ident[:8]} · {n} persona(s) · ${n*p:,} · PENDIENTE_CONCILIACION')
    def conciliar():
        if not current['id']:messagebox.showwarning('Falta prueba','Primero crea una prueba local.',parent=w);return
        try:folio=interpretar(txt.get('1.0','end'))
        except Exception as exc:messagebox.showerror('Respuesta no validada',str(exc),parent=w);return
        with db() as c:
            existente=c.execute('SELECT id FROM pruebas WHERE folio=? AND id<>?',(folio,current['id'])).fetchone()
            if existente:messagebox.showerror('Folio duplicado','Este folio ya se vinculó a otra prueba local.',parent=w);return
            anterior=c.execute('SELECT estado,folio FROM pruebas WHERE id=?',(current['id'],)).fetchone()
            if anterior[0]=='CONFIRMADO':messagebox.showinfo('Ya conciliado','La prueba ya está confirmada. No se modificó.',parent=w);return
            c.execute('UPDATE pruebas SET estado=?,folio=?,respuesta=? WHERE id=?',('CONFIRMADO',folio,txt.get('1.0','end').strip(),current['id']))
        estado.set(f'Prueba {current["id"][:8]} · DTE 39 CONFIRMADO · folio {folio} (solo simulación local)')
        messagebox.showinfo('Conciliación correcta',f'Respuesta PLANO validada. Folio: {folio}\nNo se realizó ninguna emisión ni venta real.',parent=w)
    tk.Button(w,text='1 · CREAR VENTA DE PRUEBA LOCAL',command=crear,font=('Arial',12,'bold'),bg='#235c83',fg='white',height=2).pack(fill='x',padx=75,pady=7)
    tk.Button(w,text='2 · VALIDAR RESPUESTA Y VINCULAR FOLIO',command=conciliar,font=('Arial',12,'bold'),bg='#287a5e',fg='white',height=2).pack(fill='x',padx=75,pady=7)
    tk.Label(w,text='Para esta simulación puedes usar el XML de respuesta PLANO ya obtenido.\nNo uses el botón REGISTRAR VENTA del sistema principal para esta prueba.',bg='#f5f7f9',fg='#555').pack(pady=10)
    w.mainloop()
if __name__=='__main__':main()
