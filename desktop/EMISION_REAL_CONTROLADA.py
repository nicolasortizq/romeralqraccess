"""Emisión manual única DTE39 de una venta EXISTENTE de ROMERAL.
No se invoca desde el botón de caja. No reintentos. Una venta por operación.
"""
import base64
import hashlib
import json
import os
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path
from tkinter import Tk, Label, Button, Entry, StringVar, messagebox
from integracion_facturacion import VentaBoleta
from VALIDACION_DTE39 import validar
from validacion_produccion import CONFIG, SERVICE, WSDL, cod
from conciliacion_dte import reservar
from registro_intentos_soap import crear_tabla, preparar_intento, marcar_inicio_envio
from RESPUESTAS_SOAP_DTE import analizar_respuesta
from control_folios import es_agotamiento_explicito
from puente_soap_dte import conciliar_respuesta

DATA=Path.home()/'Documents'/'ROMERAL_Datos'
DB=DATA/'romeral.sqlite3'


def extraer_xml(respuesta):
    if isinstance(respuesta,str): return respuesta
    if isinstance(respuesta,bytes): return respuesta.decode('utf-8')
    # zeep devuelve string en el servicio wsplano; otros tipos son ambiguos.
    raise ValueError('Respuesta SOAP de tipo no reconocido; verificar en portal')


def operacion(venta_id, confirmacion, autorizacion_unica=False):
    if not isinstance(venta_id, int) or venta_id <= 0:
        raise ValueError('ID inválido')
    if not DB.is_file() or not CONFIG.is_file():
        raise RuntimeError('Falta base de datos o configuración de producción')
    # Dependencias se cargan ANTES de marcar un envío como iniciado.
    import keyring
    from requests import Session
    from zeep import Client
    from zeep.transports import Transport
    from zeep.cache import SqliteCache
    data=json.loads(CONFIG.read_text(encoding='utf-8'))
    # Interruptor de seguridad: solo el booleano JSON true habilita producción.
    # Validar ANTES de abrir la base, reservar la venta o llamar al SOAP.
    # Una autorización excepcional permite SOLO la venta de control registrada
    # en SQLite, sin desbloquear la caja ni cambiar la configuración global.
    if data.get('emision_habilitada') is not True and not autorizacion_unica:
        raise RuntimeError('EMISIÓN BLOQUEADA: emision_habilitada debe ser true en configuración de producción. No se envió DTE.')
    if data.get('ambiente') != 'produccion' or not data.get('rut') or not data.get('usuario'):
        raise RuntimeError('Configuración de producción incompleta')
    clave=keyring.get_password(SERVICE,'clave')
    if not clave: raise RuntimeError('Clave no disponible en llavero')
    conn=sqlite3.connect(DB,timeout=15)
    try:
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA busy_timeout=15000')
        venta=conn.execute('''SELECT v.id,v.fecha,v.tipo,v.cantidad,v.total,v.medio,v.estado_boleta,
             v.referencia_venta,v.folio_dte,c.estado FROM ventas v JOIN control_emision c ON c.venta_id=v.id
             WHERE v.id=?''',(venta_id,)).fetchone()
        if not venta: raise RuntimeError('Venta inexistente o sin control DTE')
        vid,fecha,tipo,cantidad,total,medio,estado,referencia,folio,control=venta
        if autorizacion_unica:
            permiso=conn.execute("SELECT venta_id,estado FROM autorizacion_emision_unica WHERE id=1").fetchone()
            if (not permiso or permiso != (vid,'AUTORIZADA') or
                tipo != 'Entrada General' or cantidad != 1 or total != 12000 or medio != 'Efectivo' or
                data.get('ambiente') != 'produccion'):
                raise RuntimeError('La venta no coincide con la autorización única de $12.000 en efectivo.')
        if not isinstance(total,int) or total <= 0 or estado!='PENDIENTE_INTEGRACION' or control!='PENDIENTE_INTEGRACION' or folio:
            raise RuntimeError('Venta no elegible: requiere monto positivo, pendiente y sin folio')
        if confirmacion != f'EMITIR {venta_id} {total}':
            raise ValueError('Confirmación no coincide con la venta y su monto')
        if fecha[:10]!=date.today().isoformat():
            raise RuntimeError('La venta debe ser de hoy')
        txt=validar(VentaBoleta(referencia,tipo,cantidad,total,medio,fecha[:10]))
        # No emitir si hubo cualquier intento anterior, incluso fallido o preparado.
        crear_tabla(conn)
        if conn.execute('SELECT 1 FROM intentos_soap_dte WHERE venta_id=?',(vid,)).fetchone():
            raise RuntimeError('Ya existe un intento: NO reenviar')
        # Preparar el cliente y WSDL sin emitir antes de reservar.
        session=Session();session.verify=True
        client=Client(WSDL,transport=Transport(session=session,cache=SqliteCache(path=str(DATA / "romeral_wsdl_cache.sqlite"),timeout=3600),timeout=20,operation_timeout=30))
        port=client.bind('wsplano','wsplanoSoap')
        login={'Usuario':cod(data['usuario']),'Rut':cod(data['rut']),
               'Clave':cod(clave),'Puerto':cod(str(data.get('puerto','0'))),'IncluyeLink':'1'}
        # Respaldo SQLite consistente antes de la primera modificación.
        respaldo=DATA/('romeral_antes_emision_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.sqlite3')
        with sqlite3.connect(respaldo) as backup: conn.backup(backup)
        reservar(conn,vid,'OPERACION_UNICA_AUTORIZADA_'+str(total))
        preparar_intento(conn,vid,txt)
        if autorizacion_unica:
            with conn:
                updated=conn.execute("UPDATE autorizacion_emision_unica SET estado='CONSUMIDA' WHERE id=1 AND venta_id=? AND estado='AUTORIZADA'",(vid,))
                if updated.rowcount != 1: raise RuntimeError('Autorización única ya utilizada')
        marcar_inicio_envio(conn,vid)  # Confirmado en disco ANTES de la red.
        try:
            respuesta=extraer_xml(port.Procesar(login=login,file=cod(txt),formato=1))
        except Exception:
            with conn:
                conn.execute("UPDATE intentos_soap_dte SET estado='INCIERTO' WHERE venta_id=? AND estado='ENVIO_INICIADO'",(vid,))
            try:
                from conciliacion_dte import marcar_incierta
                marcar_incierta(conn,vid,'SOAP:RESPUESTA_NO_RECIBIDA')
            except Exception: pass
            raise RuntimeError('RESULTADO INCIERTO. NO REPETIR. Revisar portal Facturacion.com antes de cualquier acción.') from None
        # La respuesta se guarda de manera durable ANTES de conciliar.
        # Si falla la escritura, el intento permanece bloqueado.
        evidencia=DATA/f'romeral_soap_respuesta_venta_{vid}.xml'
        temporal=DATA/f'.romeral_soap_respuesta_venta_{vid}.tmp'
        with open(temporal,'x',encoding='utf-8') as archivo:
            archivo.write(respuesta)
            archivo.flush()
            os.fsync(archivo.fileno())
        os.replace(temporal,evidencia)
        digest=hashlib.sha256(respuesta.encode('utf-8')).hexdigest()
        resultado=analizar_respuesta(respuesta)
        try:
            conciliado=conciliar_respuesta(conn,vid,respuesta)
            nuevo=conciliado['estado']
        except Exception:
            nuevo='INCIERTA'
            try:
                from conciliacion_dte import marcar_incierta
                marcar_incierta(conn,vid,'SOAP:CONCILIACION_FALLIDA:'+digest)
            except Exception:
                pass
        confirmado=conn.execute('SELECT c.estado,c.folio,v.estado_boleta,v.folio_dte FROM control_emision c JOIN ventas v ON v.id=c.venta_id WHERE c.venta_id=?',(vid,)).fetchone()
        confirmado_ok=(nuevo=='EMITIDA' and confirmado is not None and
            confirmado[0]=='EMITIDA' and confirmado[2]=='EMITIDA' and
            confirmado[1] and confirmado[1]==confirmado[3] and
            str(confirmado[1])==str(resultado.get('folio')))
        with conn:
            conn.execute("UPDATE intentos_soap_dte SET estado=?,sha256_respuesta=?,folio=? WHERE venta_id=? AND estado='ENVIO_INICIADO'",
                ('CONFIRMADO' if confirmado_ok else 'INCIERTO',digest,
                 str(confirmado[1]) if confirmado_ok else None,vid))
        if confirmado_ok:
            return f'RESPUESTA SOAP CONFIRMADA: DTE 39, folio {confirmado[1]}. Verificar en portal antes de imprimir. Evidencia: {evidencia}'
        # Sólo propagar el aviso de folios si el XML del proveedor lo expresa.
        # No usar una respuesta ambigua como prueba de no emisión.
        aviso_folios=''
        try:
            import xml.etree.ElementTree as ET
            raiz=ET.fromstring(respuesta)
            fragmentos=[(n.text or '').strip() for n in raiz.iter()
                        if n.text and len((n.text or ''))<500]
            hallazgos=[t for t in fragmentos if es_agotamiento_explicito(t)]
            if hallazgos:aviso_folios=' AVISO PROVEEDOR: '+hallazgos[0][:350]
        except ET.ParseError:
            pass
        return f'RESPUESTA NO CONFIRMADA. NO REINTENTAR. Revisar portal y evidencia: {evidencia}'+aviso_folios

    finally:
        conn.close()


def main():
    root=Tk();root.title('ROMERAL | Emisión real única DTE 39');root.geometry('660x350')
    Label(root,text='EMISIÓN REAL · PRODUCCIÓN',font=('Arial',17,'bold')).pack(pady=14)
    Label(root,text='Una venta existente de HOY. No crea ventas ni reintenta.').pack(pady=5)
    Label(root,text='Cierra ROMERAL antes de emitir. Cada emisión tiene validez tributaria.',fg='#9a4b00').pack(pady=5)
    Label(root,text='ID de venta (visible en Control DTE):').pack()
    vid=StringVar();Entry(root,textvariable=vid,width=15).pack(pady=5)
    Label(root,text='Confirmación exacta: EMITIR [ID] [MONTO]').pack()
    frase=StringVar();Entry(root,textvariable=frase,width=35).pack(pady=5)
    def enviar():
        try: n=int(vid.get())
        except ValueError: messagebox.showerror('Venta','ID numérico requerido');return
        if not messagebox.askyesno('ÚLTIMA CONFIRMACIÓN',f'¿Emitir una boleta REAL asociada a la venta {n}?\nEsta acción puede consumir un folio y NO se repetirá automáticamente.'):
            return
        btn.config(state='disabled');root.update_idletasks()
        try: messagebox.showinfo('Resultado',operacion(n,frase.get()))
        except Exception as exc: messagebox.showerror('Emisión detenida',str(exc))
    btn=Button(root,text='EMITIR UNA VEZ EN PRODUCCIÓN',command=enviar,bg='#b45309',fg='white',font=('Arial',12,'bold'))
    btn.pack(pady=16)
    root.mainloop()

if __name__=='__main__':
    if len(sys.argv)==4 and sys.argv[1]=='--venta':
        try:
            print(operacion(int(sys.argv[2]), sys.argv[3]),flush=True)
        except Exception as exc:
            print('EMISIÓN DETENIDA: '+str(exc),flush=True,file=sys.stderr)
            sys.exit(2)
    else:
        main()

