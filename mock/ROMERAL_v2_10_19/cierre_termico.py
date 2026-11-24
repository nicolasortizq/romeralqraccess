"""Comprobante interno de cierre/resumen, no tributario. PDF 80 mm y cola POS.
No altera PDF oficial ni emite documentos tributarios.
"""
from pathlib import Path
from datetime import datetime
import json
import subprocess
import sys
import os


def _clp(n):
    return '$' + f'{int(n):,}'.replace(',', '.')


def _datos(conn, fecha, preliminar):
    cerrado = conn.execute('SELECT fecha,creado,efectivo_esperado,efectivo_contado,diferencia,webpay,tarjeta,total,personas,ventas,desglose_json FROM cierres_caja WHERE fecha=?', (fecha,)).fetchone()
    if not preliminar and not cerrado:
        raise ValueError('No existe un cierre guardado para esta fecha.')
    if cerrado:
        _,creado,esperado,contado,diferencia,webpay,tarjeta,total,personas,ventas,detalle = cerrado
        tipos=json.loads(detalle)
        return creado, esperado, contado, diferencia, webpay, tarjeta, total, personas, ventas, tipos, True
    rows=conn.execute("SELECT tipo,medio,cantidad,total FROM ventas WHERE substr(fecha,1,10)=? AND estado_boleta != 'ANULADA_PRUEBA'",(fecha,)).fetchall()
    medios={m:sum(int(r[3]) for r in rows if r[1]==m) for m in ('Efectivo','Webpay','Tarjeta')}
    tipos={}
    for tipo,medio,cantidad,monto in rows:
        tipo='Cabañas' if tipo=='Alojamiento' else tipo
        x=tipos.setdefault(tipo,{'personas':0,'ventas':0,'total':0})
        x['personas']+=int(cantidad);x['ventas']+=1;x['total']+=int(monto)
    return datetime.now().isoformat(timespec='seconds'),medios['Efectivo'],None,None,medios['Webpay'],medios['Tarjeta'],sum(r[3] for r in rows),sum(r[2] for r in rows),len(rows),tipos,False


def crear_pdf_cierre(conn, fecha, carpeta, preliminar=False):
    import fitz  # PyMuPDF, ya utilizado para la impresión de boletas en ROMERAL.
    creado,esperado,contado,diferencia,webpay,tarjeta,total,personas,ventas,tipos,cerrado=_datos(conn,fecha,preliminar)
    lineas=[
      ('VALLE DE ROMERAL SpA',True),('CENTRO TURISTICO',False),
      ('CIERRE DIARIO DE CAJA' if cerrado else 'RESUMEN PROVISORIO',True),
      ('DOCUMENTO INTERNO - NO TRIBUTARIO',False),
      ('-'*34,False),('Jornada: '+fecha,False),('Registrado: '+str(creado).replace('T',' '),False),
      ('-'*34,False),('VENTAS: '+str(ventas),True),('PERSONAS: '+str(personas),True),
      ('RECAUDACION: '+_clp(total),True),('-'*34,False),('MEDIOS DE PAGO',True),
      ('Efectivo esperado: '+_clp(esperado),False),
      ('Webpay: '+_clp(webpay),False),('Tarjeta: '+_clp(tarjeta),False),
    ]
    if cerrado:
        lineas += [('Efectivo contado: '+_clp(contado),False),('Diferencia: '+_clp(diferencia),True)]
    lineas += [('-'*34,False),('VISITANTES POR MODALIDAD',True)]
    for tipo,d in sorted(tipos.items()):
        lineas.extend([(str(tipo)[:31],True),('  '+str(d['personas'])+' personas / '+str(d['ventas'])+' ventas',False),('  '+_clp(d['total']),False)])
    lineas += [('-'*34,False),('Registro definitivo' if cerrado else 'SIN CIERRE - SOLO CONSULTA',True),('No reemplaza boleta electronica',False)]
    # PDF de ancho real 80 mm; líneas adaptadas al papel, sin cabecera/pie de navegador.
    ancho=80*72/25.4
    alto=max(170,len(lineas)*14+35)
    doc=fitz.open()
    pagina=doc.new_page(width=ancho,height=alto)
    y=18
    for texto,negrita in lineas:
        fuente='hebo' if negrita else 'helv'
        tam=9 if negrita else 8
        # Limitar texto para evitar recortes en 80 mm.
        while fitz.get_text_length(texto,fontname=fuente,fontsize=tam)>ancho-18 and tam>6:
            tam-=0.5
        pagina.insert_text((9,y),texto,fontname=fuente,fontsize=tam,color=(0,0,0))
        y+=14
    carpeta=Path(carpeta);carpeta.mkdir(parents=True,exist_ok=True)
    ruta=carpeta/('ROMERAL_'+('cierre_' if cerrado else 'resumen_')+fecha+'.pdf')
    if not cerrado:
        ruta=carpeta/('ROMERAL_resumen_'+fecha+'_'+datetime.now().strftime('%H%M%S')+'.pdf')
    doc.save(str(ruta),garbage=3,deflate=True)
    doc.close()
    return ruta


def enviar_pdf_termico(ruta, impresora=None):
    ruta=Path(ruta)
    if sys.platform=='darwin' or sys.platform.startswith('linux'):
        from impresion_oficial import _impresora_pos80
        destino=_impresora_pos80(impresora)
        r=subprocess.run(['lp','-d',destino,'-o','fit-to-page',str(ruta)],capture_output=True,text=True,timeout=25)
        if r.returncode:raise RuntimeError((r.stderr or r.stdout).strip() or 'Error de cola de impresión')
        return 'Trabajo enviado a '+destino+'. Verifica que se imprima físicamente.'
    if os.name=='nt':
        from impresion_windows import enviar_pdf_windows
        return enviar_pdf_windows(ruta, impresora)
    raise RuntimeError('Impresión automática no configurada para este sistema operativo.')
