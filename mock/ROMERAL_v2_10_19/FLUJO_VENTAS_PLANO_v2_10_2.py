"""Prueba integrada PLANO, aislada de la caja y sin reintentos automaticos."""
import base64, hashlib, json, os, sqlite3, uuid
from datetime import datetime, date
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from xml.etree import ElementTree as ET
from integracion_facturacion import VentaBoleta
from VALIDACION_DTE39 import validar

DATA=Path.home()/'Documents'/'ROMERAL_Datos'
DB=DATA/'pruebas_integradas_plano_v2_10_2.sqlite3'
CONFIG=DATA/'facturacion_plano.json'
SERVICE='ROMERAL_FACTURACION_PLANO'
WSDL='https://wss.facturacion.cl/WSDS/wsplano.asmx?wsdl'

def db():
    DATA.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(DB,timeout=15)
    c.execute('CREATE TABLE IF NOT EXISTS pruebas (id TEXT PRIMARY KEY, fecha TEXT NOT NULL, cantidad INTEGER NOT NULL, unitario INTEGER NOT NULL, total INTEGER NOT NULL, estado TEXT NOT NULL, folio TEXT UNIQUE, respuesta TEXT, error TEXT, txt_sha256 TEXT, modalidad TEXT NOT NULL, medio TEXT NOT NULL)')
    c.commit()
    return c

def cod(s):return base64.b64encode(str(s).encode('utf-8')).decode('ascii')

def documento(ident,modalidad,n,total,medio):
    return validar(VentaBoleta('PLANO-'+ident[:12],modalidad,n,total,medio,date.today().isoformat()))

def interpretar(xml):
    root=ET.fromstring(xml.strip())
    if root.tag!='WSPLANO':raise ValueError('Respuesta no corresponde a WSPLANO')
    if (root.findtext('Resultado') or '').strip().lower()!='true':raise ValueError('Proveedor no confirma exito: '+(root.findtext('Mensaje') or 'sin detalle'))
    docs=root.findall('./Detalle/Documento')
    if len(docs)!=1:raise ValueError('Cantidad de documentos inesperada; verificar manualmente')
    doc=docs[0]
    if (doc.findtext('Resultado') or '').strip().lower()!='true' or (doc.findtext('TipoDte') or '').strip()!='39':raise ValueError('DTE 39 no confirmado')
    folio=(doc.findtext('Folio') or '').strip()
    if not folio.isdigit() or int(folio)<=0:raise ValueError('Folio invalido')
    return folio

def main():
    app=tk.Tk();app.title('ROMERAL v2.10.2 | Cuatro modalidades PLANO');app.geometry('850x690');app.configure(bg='#f5f7f9')
    tk.Label(app,text='ROMERAL · EMISION INTEGRADA PLANO',font=('Arial',19,'bold'),bg='#f5f7f9').pack(pady=(16,4))
    tk.Label(app,text='SOLO PRUEBAS · No registra caja real, no imprime, no utiliza produccion',font=('Arial',11),bg='#f5f7f9',fg='#a02e25').pack()
    f=tk.Frame(app,bg='#f5f7f9');f.pack(pady=10)
    modalidad=tk.StringVar(value='Entrada General')
    medio=tk.StringVar(value='Efectivo')
    tk.Label(f,text='Modalidad:',bg='#f5f7f9').grid(row=0,column=0,padx=5,pady=4)
    opciones=('Entrada General','Piscina Temperada','Cabañas','Camping')
    tk.OptionMenu(f,modalidad,*opciones).grid(row=0,column=1,columnspan=2,sticky='ew')
    tk.Label(f,text='Medio de pago:',bg='#f5f7f9').grid(row=0,column=3,padx=5)
    tk.OptionMenu(f,medio,'Efectivo','Webpay','Tarjeta').grid(row=0,column=4,sticky='ew')
    tk.Label(f,text='Personas:',bg='#f5f7f9').grid(row=1,column=0,padx=5,pady=5)
    cantidad=tk.StringVar(value='1');tk.Entry(f,textvariable=cantidad,width=9).grid(row=1,column=1)
    etiqueta_precio=tk.StringVar(value='Valor unitario ($):')
    tk.Label(f,textvariable=etiqueta_precio,bg='#f5f7f9').grid(row=1,column=2,padx=5)
    precio=tk.StringVar(value='1000');tk.Entry(f,textvariable=precio,width=12).grid(row=1,column=3)
    tk.Label(f,text='Cabañas y Camping: ingresar monto TOTAL manual, no unitario.',bg='#f5f7f9',fg='#6b4b15').grid(row=2,column=0,columnspan=5,pady=2)
    def ajustar_modalidad(*_):
        etiqueta_precio.set('Monto TOTAL ($):' if modalidad.get() in ('Cabañas','Camping') else 'Valor unitario ($):')
    modalidad.trace_add('write',ajustar_modalidad)
    estado=tk.StringVar(value='Sin prueba creada');tk.Label(app,textvariable=estado,bg='#f5f7f9',font=('Arial',11,'bold'),wraplength=780).pack(pady=8)
    tk.Label(app,text='Vista previa del TXT a enviar:',bg='#f5f7f9').pack()
    txt=tk.Text(app,width=100,height=12,font=('Consolas',9));txt.pack(padx=12,pady=5)
    current={'id':None,'txt':None}
    def set_status(ident):
        with db() as c: r=c.execute('SELECT estado,folio,error FROM pruebas WHERE id=?',(ident,)).fetchone()
        estado.set('Prueba '+ident[:8]+' · '+r[0]+(' · Folio '+r[1] if r[1] else '')+(' · '+r[2] if r[2] else ''))
    def crear():
        if current['id']:
            messagebox.showwarning('Prueba existente','Ya hay una prueba en esta ventana. Para otra prueba, cierra y vuelve a abrir.',parent=app);return
        try:
            n=int(cantidad.get());p=int(precio.get())
            mod=modalidad.get();pay=medio.get()
            total=p if mod in ('Cabañas','Camping') else n*p
            if n<1 or n>1000 or p<1 or total>100000000:raise ValueError()
            ident=str(uuid.uuid4());doc=documento(ident,mod,n,total,pay)
        except Exception as e:
            messagebox.showerror('Datos no validos','Revisa cantidad y valor, o el TXT: '+str(e),parent=app);return
        with db() as c:c.execute('INSERT INTO pruebas(id,fecha,cantidad,unitario,total,estado,txt_sha256,modalidad,medio) VALUES(?,?,?,?,?,?,?,?,?)',(ident,datetime.now().isoformat(timespec='seconds'),n,p,total,'PREPARADA',hashlib.sha256(doc.encode()).hexdigest(),mod,pay))
        current.update(id=ident,txt=doc)
        txt.delete('1.0','end');txt.insert('1.0',doc);txt.configure(state='disabled')
        set_status(ident)
    def enviar():
        ident=current['id']
        if not ident:messagebox.showwarning('Falta prueba','Primero prepara una prueba.',parent=app);return
        with db() as c:r=c.execute('SELECT estado,cantidad,unitario,total,modalidad,medio FROM pruebas WHERE id=?',(ident,)).fetchone()
        if r[0]!='PREPARADA':messagebox.showwarning('Envio bloqueado','Estado '+r[0]+'. NO repetir envios.',parent=app);return
        if not messagebox.askyesno('Confirmar prueba',f'Se enviara UNA boleta de PRUEBA PLANO DTE39 por ${r[3]:,} para {r[1]} persona(s).\nModalidad: {r[4]} · Pago: {r[5]}. No se registra caja real. ¿Continuar?',parent=app):return
        if not messagebox.askyesno('Confirmacion final','Se transmitira al servicio PLANO de Facturacion.com. Ante cualquier error NO reintentar. ¿Enviar?',parent=app):return
        boton_enviar.configure(state='disabled');app.update_idletasks()
        try:
            cfg=json.loads(CONFIG.read_text(encoding='utf-8'))
            if cfg.get('ambiente')!='plano' or cfg.get('rut')!='1-9':raise ValueError('Credenciales PLANO no validas. No se envio.')
            import keyring
            clave=keyring.get_password(SERVICE,'clave')
            if not clave or not cfg.get('usuario'):raise ValueError('Credenciales PLANO incompletas. No se envio.')
            from requests import Session
            from zeep import Client
            from zeep.transports import Transport
            ses=Session();ses.verify=True
            client=Client(WSDL,transport=Transport(session=ses,timeout=20,operation_timeout=30))
            port=client.bind('wsplano','wsplanoSoap')
            login={'Usuario':cod(cfg['usuario']),'Rut':cod(cfg['rut']),'Clave':cod(clave),'Puerto':cod(str(cfg.get('puerto','0'))),'IncluyeLink':'0'}
        except Exception as e:
            messagebox.showerror('Preparacion detenida',str(e),parent=app);boton_enviar.configure(state='normal');return
        # Transicion persistida ANTES de llamar a la red; sin reintentos incluso ante timeout.
        with db() as c:
            updated=c.execute("UPDATE pruebas SET estado='ENVIO_INICIADO' WHERE id=? AND estado='PREPARADA'",(ident,)).rowcount
        if updated!=1:messagebox.showerror('Bloqueado','El intento ya no esta disponible.',parent=app);return
        set_status(ident)
        try:
            respuesta=str(port.Procesar(login=login,file=cod(current['txt']),formato=1) or '')
        except Exception as e:
            with db() as c:c.execute('UPDATE pruebas SET estado=?,error=? WHERE id=?',('RESULTADO_INCIERTO',type(e).__name__,ident))
            set_status(ident);messagebox.showerror('Resultado incierto','NO REINTENTAR. Consulta el portal PLANO para comprobar si se emitio el documento.',parent=app);return
        # Guardar respuesta ANTES de intentar interpretarla.
        with db() as c:c.execute('UPDATE pruebas SET estado=?,respuesta=? WHERE id=?',('RESPUESTA_PENDIENTE',respuesta,ident))
        try:
            folio=interpretar(respuesta)
            with db() as c:c.execute('UPDATE pruebas SET estado=?,folio=? WHERE id=?',('CONFIRMADO',folio,ident))
            set_status(ident);messagebox.showinfo('DTE39 PLANO confirmado',f'Folio asignado: {folio}\nPrueba guardada localmente. No se registro venta real ni se imprimio.',parent=app)
        except Exception as e:
            with db() as c:c.execute('UPDATE pruebas SET estado=?,error=? WHERE id=?',('REVISAR_RESPUESTA',str(e)[:400],ident))
            set_status(ident);messagebox.showwarning('Revisar respuesta','La respuesta fue guardada, pero NO se confirmo el folio. NO REINTENTAR. Revisar en portal PLANO.',parent=app)
    tk.Button(app,text='1 · PREPARAR VENTA DE PRUEBA',command=crear,font=('Arial',12,'bold'),bg='#245e86',fg='white',height=2).pack(fill='x',padx=70,pady=8)
    boton_enviar=tk.Button(app,text='2 · ENVIAR UNA VEZ A PLANO Y GUARDAR FOLIO',command=enviar,font=('Arial',12,'bold'),bg='#28775a',fg='white',height=2)
    boton_enviar.pack(fill='x',padx=70,pady=8)
    tk.Label(app,text='ATENCION: La confirmacion de una prueba anterior NO debe reutilizarse.\nNo utilizar REGISTRAR VENTA del sistema principal para estas pruebas.',bg='#f5f7f9',fg='#a02e25').pack(pady=10)
    app.mainloop()
if __name__=='__main__':main()
