"""Representación térmica complementaria de un DTE real.

No emite, no reemplaza ni modifica el PDF oficial. El timbre se extrae
sin reconstrucción de la imagen embebida en el PDF del proveedor.
"""
from pathlib import Path
from datetime import datetime
import re
import sqlite3

MM = 72 / 25.4
DATA = Path.home() / 'Documents' / 'ROMERAL_Datos'


def _pesos(n):
    return '$' + f'{int(n):,}'.replace(',', '.')


def _venta(venta_id, data_dir=DATA):
    with sqlite3.connect(Path(data_dir) / 'romeral.sqlite3') as db:
        row = db.execute('''SELECT fecha,tipo,cantidad,total,medio,estado_boleta,folio_dte,tipo_dte
                            FROM ventas WHERE id=?''', (int(venta_id),)).fetchone()
    if not row or row[5] != 'EMITIDA' or int(row[7] or 0) != 39 or not row[6]:
        raise RuntimeError('No se encontró una venta con DTE 39 emitido y folio confirmado.')
    return row


def crear_boleta_termica(pdf_oficial, venta_id, data_dir=DATA):
    import fitz
    src = Path(pdf_oficial).expanduser().resolve()
    if not src.is_file() or src.read_bytes()[:5] != b'%PDF-':
        raise RuntimeError('Falta el PDF oficial de Facturacion.com.')
    fecha, tipo, cantidad, total, medio, estado, folio, _ = _venta(venta_id, data_dir)
    original = fitz.open(str(src))
    try:
        if original.page_count != 1:
            raise RuntimeError('El PDF oficial no tiene una sola página; revisar manualmente.')
        page = original[0]
        contenido = page.get_text(sort=True)
        # Comprobar identidad del DTE antes de tomar su timbre.
        if not re.search(r'(?:N[°ºo.]?\s*|FOLIO\s*)' + re.escape(str(folio)) + r'\b', contenido, re.I):
            raise RuntimeError('El folio del PDF no coincide con la venta; impresión bloqueada.')
        if '78.180.502-5' not in contenido or 'BOLETA ELECTRONICA' not in contenido.upper():
            raise RuntimeError('No se verificaron los datos tributarios de Valle Romeral en el PDF oficial.')
        if _pesos(total).replace('$','') not in contenido:
            raise RuntimeError('El total no se reconoce en el PDF oficial; revisar antes de imprimir.')
        imgs = []
        for item in page.get_images(full=True):
            rects = page.get_image_rects(item[0])
            if not rects:
                continue
            # PDF417 original: imagen apaisada de proporción > 1.5, en mitad inferior.
            for rect in rects:
                if rect.width > 130 and rect.width / max(rect.height, 1) > 1.5 and rect.y0 > page.rect.height * .45:
                    imgs.append((rect.width * rect.height, item[0]))
        if len(imgs) != 1:
            raise RuntimeError('No se pudo identificar de manera única el timbre oficial; no se imprimirá una copia sin timbre.')
        timbre = original.extract_image(imgs[0][1])['image']
    finally:
        original.close()
    try:
        ingreso = datetime.fromisoformat(fecha)
    except (TypeError, ValueError):
        raise RuntimeError('La venta no tiene fecha/hora de ingreso válida.')
    # El comprobante complementario conserva los datos del PDF original.
    ancho = 80 * MM
    alto = 167 * MM
    doc = fitz.open()
    pg = doc.new_page(width=ancho, height=alto)
    normal = 'helv'
    negrita = 'hebo'
    def linea(txt, y, size=9, bold=False, centrado=False):
        txt = str(txt)
        font = negrita if bold else normal
        if centrado:
            w = fitz.get_text_length(txt, fontname=font, fontsize=size)
            x = max(6, (ancho - w) / 2)
        else:
            x = 12
        pg.insert_text((x, y * MM), txt, fontname=font, fontsize=size, color=(0,0,0))
    def raya(y):
        pg.draw_line((8, y*MM),(ancho-8,y*MM),color=(0,0,0),width=.6)
    linea('VALLE ROMERAL SPA', 11, 12, True, True)
    linea('RUT 78.180.502-5', 17, 9, True, True)
    linea('CENTRO TURISTICO / RESTAURANTE', 22, 8, False, True)
    linea('LA PUNTILLA DE ROMERAL S/N', 27, 8, False, True)
    linea('HIJUELAS', 32, 8, False, True)
    raya(35)
    linea('BOLETA ELECTRONICA', 42, 12, True, True)
    linea('DTE 39 - FOLIO ' + str(folio), 49, 11, True, True)
    linea(ingreso.strftime('%d/%m/%Y'), 55, 9, False, True)
    linea('S.I.I. - QUILLOTA', 61, 9, False, True)
    raya(65)
    nombres = {'Entrada General':'Entrada General', 'Piscina Temperada':'Piscina Temperada',
               'Cabañas':'Cabanas', 'Camping':'Camping'}
    servicio = nombres.get(tipo, str(tipo))
    linea(servicio[:32], 72, 11, True)
    linea('Cantidad: ' + str(cantidad) + (' persona' if cantidad == 1 else ' personas'), 78)
    linea('Total pagado: ' + _pesos(total), 84, 10)
    linea('Medio de pago: ' + str(medio)[:22], 90, 8)
    raya(94)
    linea('TOTAL: ' + _pesos(total), 102, 12, True, True)
    raya(106)
    linea('Hora de ingreso: ' + ingreso.strftime('%H:%M:%S'), 112, 9, True, True)
    linea('Hora de venta registrada por ROMERAL', 117, 7, False, True)
    linea('TIMBRE ELECTRONICO S.I.I.', 123, 8, True, True)
    # El PDF417 se inserta como imagen original, sin decodificar ni regenerar.
    pg.insert_image(fitz.Rect(8, 126*MM, ancho-8, 144*MM), stream=timbre, keep_proportion=True)
    linea('Resolucion Nro. 80 del 22-08-2014', 150, 7, False, True)
    linea('www.facturacion.cl/vallederomeralspa/boleta', 155, 7, False, True)
    linea('Copia termica - conserve el PDF oficial', 162, 7, False, True)
    dest = src.with_name(src.stem + '_ROMERAL_80mm.pdf')
    doc.save(str(dest), garbage=3, deflate=True)
    doc.close()
    return dest
