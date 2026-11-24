"""Prueba manual aislada de DTE39 PLANO; no modifica ventas ni producción."""
import base64, hashlib, json, os, uuid
from pathlib import Path
from datetime import date, datetime
import tkinter as tk
from tkinter import messagebox
from integracion_facturacion import VentaBoleta
from VALIDACION_DTE39 import validar

DATA=Path.home()/'Documents'/'ROMERAL_Datos'
CONFIG=DATA/'facturacion_plano.json'
SERVICE='ROMERAL_FACTURACION_PLANO'
WSDL='https://wss.facturacion.cl/WSDS/wsplano.asmx?wsdl'
LOG=DATA/'prueba_dte39_plano_intento.json'
def cod(s): return base64.b64encode(str(s).encode('utf-8')).decode('ascii')
def documento():
    return validar(VentaBoleta('PRUEBA-PLANO-'+date.today().strftime('%Y%m%d'),'Entrada General',1,1000,'Efectivo',date.today().isoformat()))
def enviar():
    if LOG.exists(): raise RuntimeError('Ya existe un intento de prueba registrado. NO repetir. Revisar portal de Facturacion.com y el registro local.')
    cfg=json.loads(CONFIG.read_text(encoding='utf-8'))
    if cfg.get('ambiente')!='plano' or cfg.get('rut')!='1-9': raise RuntimeError('Bloqueado: se requiere ambiente PLANO y RUT de pruebas 1-9.')
    import keyring
    clave=keyring.get_password(SERVICE,'clave')
    if not clave or not cfg.get('usuario'): raise RuntimeError('Credenciales PLANO incompletas.')
    from requests import Session
    from zeep import Client
    from zeep.transports import Transport
    txt=documento()
    ses=Session();ses.verify=True
    client=Client(WSDL,transport=Transport(session=ses,timeout=20,operation_timeout=30))
    port=client.bind('wsplano','wsplanoSoap')
    login={'Usuario':cod(cfg['usuario']),'Rut':cod(cfg['rut']),'Clave':cod(clave),'Puerto':cod(str(cfg.get('puerto','0'))),'IncluyeLink':'0'}
    DATA.mkdir(parents=True,exist_ok=True)
    record={'ambiente':'PLANO','rut_prueba':'1-9','tipo_dte':39,'monto':1000,'fecha':datetime.now().isoformat(),'estado':'ENVIO_INICIADO','sha256_txt':hashlib.sha256(txt.encode()).hexdigest(),'id':str(uuid.uuid4())}
    # Registro exclusivo y persistente antes de la red: incluso ante timeout, no se reenvía.
    with LOG.open('x',encoding='utf-8') as f:
        json.dump(record,f,indent=2);f.flush();os.fsync(f.fileno())
    try:
        respuesta=port.Procesar(login=login,file=cod(txt),formato=1)
    except Exception as e:
        record['estado']='INCIERTO';record['error_tipo']=type(e).__name__
        LOG.write_text(json.dumps(record,indent=2),encoding='utf-8')
        raise RuntimeError('Resultado incierto. NO REINTENTAR. Verificar en portal Facturacion.com antes de continuar.') from None
    raw=str(respuesta or '')
    record['estado']='RESPUESTA_RECIBIDA_SIN_CONCILIAR';record['sha256_respuesta']=hashlib.sha256(raw.encode()).hexdigest()
    LOG.write_text(json.dumps(record,indent=2),encoding='utf-8')
    # Respuesta aislada en disco para inspección; podría incluir datos del documento, no contraseñas.
    (DATA/'prueba_dte39_plano_respuesta.txt').write_text(raw,encoding='utf-8')
    return 'Respuesta recibida, pendiente de validación. NO repetir. Revisar el archivo prueba_dte39_plano_respuesta.txt y el portal de pruebas.'
def main():
    app=tk.Tk();app.title('ROMERAL | DTE 39 PLANO - prueba aislada');app.geometry('740x490');app.configure(bg='#f3f6fa')
    tk.Label(app,text='PRUEBA DTE 39 · SOLO AMBIENTE PLANO',font=('Arial',17,'bold'),bg='#f3f6fa').pack(pady=18)
    tk.Label(app,text='Documento de prueba: Entrada General · 1 persona · $1.000 · folio 0',font=('Arial',12),bg='#f3f6fa').pack()
    tk.Label(app,text='NO registra venta, NO imprime y NO utiliza credenciales de producción.',bg='#f3f6fa').pack(pady=8)
    txt=tk.Text(app,width=85,height=10,font=('Consolas',9));txt.pack(padx=14,pady=8)
    try: txt.insert('1.0',documento())
    except Exception as e: txt.insert('1.0','ERROR EN VALIDACION LOCAL: '+str(e))
    txt.configure(state='disabled')
    def click():
        if not messagebox.askyesno('Confirmación de transmisión','Se enviará UNA boleta DTE39 de PRUEBA por $1.000 al ambiente PLANO. No se reintentará automáticamente. ¿Confirmas?',parent=app): return
        if not messagebox.askyesno('Última confirmación','¿Enviar ahora mediante Procesar al servicio PLANO? No es una boleta real de producción.',parent=app): return
        btn.configure(state='disabled');app.update_idletasks()
        try: messagebox.showinfo('Resultado',enviar(),parent=app)
        except Exception as e: messagebox.showerror('Prueba detenida',str(e),parent=app)
    btn=tk.Button(app,text='ENVIAR UNA SOLA PRUEBA A PLANO',command=click,bg='#276f55',fg='white',font=('Arial',12,'bold'),height=2);btn.pack(pady=8)
    if LOG.exists(): btn.configure(state='disabled');tk.Label(app,text='Existe intento anterior: envío bloqueado para evitar duplicados.',fg='#a22',bg='#f3f6fa').pack()
    app.mainloop()
if __name__=='__main__':main()
