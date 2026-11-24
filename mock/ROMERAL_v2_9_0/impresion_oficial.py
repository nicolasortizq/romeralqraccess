"""Impresión térmica del PDF oficial SIN alterar el archivo tributario original.
La copia rasterizada conserva proporciones y elimina bandas verticales vacías.
"""
import os
import subprocess
import sys
import time
from diagnostico_tiempos import registrar_tiempo
from pathlib import Path


def preparar_pdf_80mm(ruta):
    """Crea una copia compacta de 80 mm para imprimir; nunca sobrescribe el DTE."""
    try:
        import fitz
        import numpy as np
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError('Falta PyMuPDF, Pillow o numpy. Instala dependencias con: python3 -m pip install pymupdf pillow numpy') from exc
    origen=Path(ruta).expanduser().resolve()
    if not origen.is_file() or origen.read_bytes()[:5]!=b'%PDF-':
        raise ValueError('No se encontró un PDF oficial válido.')
    destino=origen.with_name(origen.stem+'_TERMICA_80mm.pdf')
    if destino.exists() and destino.stat().st_mtime>=origen.stat().st_mtime:
        return destino
    dpi=240
    margen_px=round(4*dpi/25.4)
    ancho_util=round(72*dpi/25.4)
    espacio_px=round(3*dpi/25.4)
    # Conservamos toda la tinta, incluyendo timbre, textos, líneas y logotipos.
    trozos=[]
    doc=fitz.open(str(origen))
    if doc.page_count>8:
        raise RuntimeError('El PDF tiene demasiadas páginas para una boleta térmica; revisa el documento.')
    for page in doc:
        pix=page.get_pixmap(matrix=fitz.Matrix(dpi/72,dpi/72),colorspace=fitz.csRGB,alpha=False)
        im=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
        a=np.asarray(im)
        tinta=np.any(a<238,axis=2)
        filas=np.flatnonzero(np.any(tinta,axis=1))
        if len(filas)==0:continue
        # Secciona únicamente espacios grandes totalmente blancos; no corta el timbre.
        cortes=np.flatnonzero(np.diff(filas)>round(12*dpi/25.4))
        inicios=np.r_[0,cortes+1]; finales=np.r_[cortes,len(filas)-1]
        for ini,fin in zip(inicios,finales):
            y0=max(0,int(filas[ini])-round(2*dpi/25.4))
            y1=min(im.height,int(filas[fin])+round(2*dpi/25.4)+1)
            segmento=im.crop((0,y0,im.width,y1))
            sa=np.asarray(segmento)
            cols=np.flatnonzero(np.any(np.any(sa<238,axis=2),axis=0))
            if len(cols)==0:continue
            x0=max(0,int(cols[0])-round(2*dpi/25.4))
            x1=min(im.width,int(cols[-1])+round(2*dpi/25.4)+1)
            segmento=segmento.crop((x0,0,x1,segmento.height))
            # Escala uniforme: jamás estirar el timbre ni los textos.
            factor=min(1.0,ancho_util/segmento.width)
            if factor!=1:
                segmento=segmento.resize((max(1,round(segmento.width*factor)),max(1,round(segmento.height*factor))),Image.Resampling.LANCZOS)
            trozos.append(segmento)
    doc.close()
    if not trozos:raise RuntimeError('El PDF oficial no contiene contenido visible para imprimir.')
    ancho=round(80*dpi/25.4)
    alto=sum(t.height for t in trozos)+2*margen_px+espacio_px*(len(trozos)-1)
    if alto>round(1800*dpi/25.4):
        raise RuntimeError('La boleta resultante es demasiado larga; revisa el PDF antes de imprimir.')
    salida=Image.new('RGB',(ancho,alto),'white')
    y=margen_px
    for t in trozos:
        salida.paste(t,((ancho-t.width)//2,y))
        y+=t.height+espacio_px
    pdf=fitz.open()
    # Una sola página de ancho 80 mm; longitud exacta de la boleta.
    from io import BytesIO
    buf=BytesIO();salida.save(buf,format='PNG',compress_level=3)
    w=80*72/25.4;h=alto*72/dpi
    page=pdf.new_page(width=w,height=h)
    page.insert_image(fitz.Rect(0,0,w,h),stream=buf.getvalue())
    pdf.save(str(destino),garbage=3,deflate=True)
    pdf.close()
    return destino


def _impresora_pos80(impresora=None):
    """Busca la cola CUPS por nombre, sin depender del idioma de lpstat."""
    import re
    res = subprocess.run(['lpstat', '-p'], capture_output=True, text=True, timeout=10)
    if res.returncode != 0:
        raise RuntimeError('No se pudo consultar CUPS: ' + (res.stderr or '').strip())
    # lpstat cambia su encabezado según LANG: 'printer X' o 'la impresora X'.
    # Los nombres de cola CUPS no contienen espacios.
    nombres = []
    for linea in res.stdout.splitlines():
        m = re.match(r'^\s*(?:printer|la impresora|impresora)\s+(\S+)\s+', linea, re.I)
        if m:
            nombres.append(m.group(1))
    if impresora:
        if impresora not in nombres:
            raise RuntimeError('La impresora configurada no está registrada en CUPS: ' + impresora)
        return impresora
    # Nombre exacto comprobado en el Mac del usuario; no enviar a otra impresora.
    if 'Printer_POS_80' in nombres:
        return 'Printer_POS_80'
    candidatas = [n for n in nombres if any(x in n.lower() for x in ('pos-80', 'pos_80', '3nstar'))]
    if len(candidatas) != 1:
        raise RuntimeError('No se encontró una única impresora POS-80. Detectadas: ' + ', '.join(nombres))
    return candidatas[0]


def imprimir_pdf_oficial(ruta, impresora=None, venta_id=None):
    origen=Path(ruta).expanduser().resolve()
    if not origen.is_file() or origen.suffix.lower()!='.pdf' or origen.read_bytes()[:5]!=b'%PDF-':
        raise ValueError('Selecciona un PDF oficial válido.')
    inicio_render=time.monotonic()
    if venta_id is not None:
        from boleta_termica_romeral import crear_boleta_termica
        termico=crear_boleta_termica(origen, venta_id)
    else:
        termico=preparar_pdf_80mm(origen)
    if venta_id is not None:
        registrar_tiempo(venta_id,'PDF_TERMICO_PREPARADO',segundos=round(time.monotonic()-inicio_render,3))
    if sys.platform=='darwin' or sys.platform.startswith('linux'):
        inicio_cups=time.monotonic()
        destino=_impresora_pos80(impresora)
        comando=['lp','-d',destino,'-o','fit-to-page',str(termico)]
        res=subprocess.run(comando,capture_output=True,text=True,timeout=25)
        if res.returncode!=0:
            raise RuntimeError((res.stderr or res.stdout).strip() or 'No se pudo enviar a la impresora.')
        if venta_id is not None:
            registrar_tiempo(venta_id,'CUPS_ACEPTO_TRABAJO',segundos=round(time.monotonic()-inicio_cups,3))
        return f'Formato térmico 80 mm enviado a {destino}.\n'+(res.stdout or '').strip()+'\nComprueba la salida física y legibilidad del timbre.'
    if os.name=='nt':
        raise RuntimeError('La impresión automática en Windows requiere configurar el controlador térmico; PDF adaptado guardado en '+str(termico))
    raise RuntimeError('Sistema operativo sin soporte de impresión configurado.')
