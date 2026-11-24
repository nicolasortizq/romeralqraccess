"""Prueba local de impresion, NO genera ni descarga DTE tributarios."""
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from impresion_windows import impresoras_windows, enviar_pdf_windows

DATA = Path.home() / 'Documents' / 'ROMERAL_Datos' / 'pruebas_impresion'

def crear_pdf(ruta, modalidad, personas, total, pago):
    ancho, alto = 80*mm, 120*mm
    c = canvas.Canvas(str(ruta), pagesize=(ancho, alto))
    c.setTitle('ROMERAL - MUESTRA NO TRIBUTARIA')
    def linea(y, texto, size=9, negrita=False):
        c.setFont('Helvetica-Bold' if negrita else 'Helvetica',size)
        c.drawCentredString(ancho/2, y*mm, texto)
    linea(107,'ROMERAL',16,True)
    linea(97,'PRUEBA DE IMPRESION',11,True)
    linea(90,'NO ES BOLETA ELECTRONICA',9,True)
    linea(84,'SIN VALIDEZ TRIBUTARIA',9,True)
    c.line(8*mm,79*mm,72*mm,79*mm)
    linea(70,'Modalidad: '+modalidad)
    linea(62,'Personas: '+str(personas))
    linea(54,'Total de muestra: $'+f'{total:,}'.replace(',','.'))
    linea(46,'Medio: '+pago)
    linea(36,datetime.now().strftime('%d/%m/%Y %H:%M'))
    c.line(8*mm,30*mm,72*mm,30*mm)
    linea(21,'Documento local de prueba',8)
    linea(15,'NO EMITIDO POR FACTURACION.COM',7,True)
    c.showPage(); c.save()

def main():
    app=tk.Tk(); app.title('ROMERAL v2.10.3 | Prueba impresora 80 mm'); app.geometry('620x440')
    tk.Label(app,text='ROMERAL · PRUEBA DE IMPRESION 80 mm',font=('Arial',16,'bold')).pack(pady=(16,6))
    tk.Label(app,text='SOLO MUESTRA · NO EMITE DTE · NO UTILIZA CREDENCIALES',fg='#9b2c2c').pack()
    frame=tk.Frame(app);frame.pack(pady=15)
    tk.Label(frame,text='Impresora Windows:').grid(row=0,column=0,sticky='e',padx=8,pady=5)
    printer=tk.StringVar(); combo=ttk.Combobox(frame,textvariable=printer,width=38,state='readonly');combo.grid(row=0,column=1,pady=5)
    def actualizar():
        try:
            opciones=impresoras_windows();combo['values']=opciones
            sugeridas=[p for p in opciones if any(t in p.lower() for t in ('pos-80','pos80','xp-80','xprinter'))]
            if sugeridas:printer.set(sugeridas[0])
            elif opciones:printer.set(opciones[0])
        except Exception as e:messagebox.showerror('Impresoras',str(e),parent=app)
    tk.Button(frame,text='Actualizar lista',command=actualizar).grid(row=1,column=1,sticky='w')
    tk.Label(frame,text='Modalidad:').grid(row=2,column=0,sticky='e',padx=8,pady=5)
    mod=tk.StringVar(value='Camping');ttk.Combobox(frame,textvariable=mod,values=['Entrada General','Piscina Temperada','Cabañas','Camping'],state='readonly',width=25).grid(row=2,column=1,sticky='w')
    tk.Label(frame,text='Personas:').grid(row=3,column=0,sticky='e',padx=8,pady=5)
    n=tk.StringVar(value='3');tk.Entry(frame,textvariable=n,width=12).grid(row=3,column=1,sticky='w')
    tk.Label(frame,text='Total muestra ($):').grid(row=4,column=0,sticky='e',padx=8,pady=5)
    total=tk.StringVar(value='30000');tk.Entry(frame,textvariable=total,width=12).grid(row=4,column=1,sticky='w')
    tk.Label(frame,text='Medio de pago:').grid(row=5,column=0,sticky='e',padx=8,pady=5)
    pago=tk.StringVar(value='Webpay');ttk.Combobox(frame,textvariable=pago,values=['Efectivo','Webpay','Tarjeta'],state='readonly',width=25).grid(row=5,column=1,sticky='w')
    def generar(imprimir=False):
        try:
            personas=int(n.get());importe=int(total.get())
            if not (1<=personas<=1000 and 1<=importe<=100000000):raise ValueError('Cantidad o importe fuera de rango')
            DATA.mkdir(parents=True,exist_ok=True)
            ruta=DATA/'MUESTRA_NO_TRIBUTARIA_80mm.pdf'
            crear_pdf(ruta,mod.get(),personas,importe,pago.get())
            if imprimir:
                if not printer.get():raise ValueError('Selecciona una impresora')
                if not messagebox.askyesno('Confirmar impresion','Se enviara una MUESTRA NO TRIBUTARIA a '+printer.get()+'. ¿Continuar?',parent=app):return
                resultado=enviar_pdf_windows(ruta,printer.get())
                messagebox.showinfo('Impresion solicitada',resultado+'\n\nPDF: '+str(ruta),parent=app)
            else:messagebox.showinfo('PDF de muestra creado','Archivo: '+str(ruta)+'\n\nPuedes abrirlo y revisarlo antes de imprimir.',parent=app)
        except Exception as e:messagebox.showerror('Prueba',str(e),parent=app)
    tk.Button(app,text='1 · GENERAR PDF DE MUESTRA',command=generar,bg='#2571a8',fg='white',height=2,width=45).pack(pady=5)
    tk.Button(app,text='2 · IMPRIMIR MUESTRA EN 80 mm',command=lambda:generar(True),bg='#33857d',fg='white',height=2,width=45).pack(pady=5)
    app.after(100,actualizar);app.mainloop()

if __name__=='__main__':main()
