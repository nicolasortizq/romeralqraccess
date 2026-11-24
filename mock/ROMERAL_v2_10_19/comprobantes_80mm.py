"""Comprobante interno imprimible de 80 mm; NO es DTE."""
from pathlib import Path
from html import escape
import re

def validar_rut(rut):
    limpio = re.sub(r'[.\s-]', '', str(rut)).upper()
    if not re.fullmatch(r'\d{7,8}[0-9K]', limpio):
        return None
    numero, dv = limpio[:-1], limpio[-1]
    suma = sum(int(d)*factor for d, factor in zip(reversed(numero), [2,3,4,5,6,7]*2))
    calculado = '0123456789K'[11 - (suma % 11)] if 11 - (suma % 11) < 11 else '0'
    if calculado != dv:
        return None
    return f'{int(numero):,}'.replace(',', '.') + '-' + dv

def crear_comprobante_html(venta, carpeta, rut_empresa=None):
    rut = validar_rut(rut_empresa)
    if not rut: raise ValueError('Configura un RUT de empresa válido antes de generar comprobantes')
    if len(venta)!=9: raise ValueError('Venta incompleta')
    vid,fecha,tipo,personas,total,medio,estado,folio,emision=venta
    if estado=='ANULADA_PRUEBA': raise ValueError('Venta anulada')
    ejemplo = vid == 'EJEMPLO' and estado == 'SIMULACIÓN'
    if int(personas)<1 or int(total)<1: raise ValueError('Datos inválidos')
    def e(v): return escape(str(v),quote=True)
    pesos='$'+f'{int(total):,}'.replace(',','.')
    identificador='EJEMPLO' if ejemplo else str(int(vid))
    html=f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>ROMERAL comprobante interno {identificador}</title><style>
@page{{size:80mm auto;margin:3mm}}
body{{font:11px Arial,sans-serif;color:#000;margin:0}}
.ticket{{width:74mm;box-sizing:border-box;padding:2mm;margin:auto}}
h1{{text-align:center;font-size:16px;margin:5px 0 2px}}
.razon{{text-align:center;font-size:12px;font-weight:bold}}
.servicio{{font-size:13px;font-weight:bold}}
.aviso{{border:2px solid #000;text-align:center;font-size:12px;font-weight:bold;padding:4px 2px}}
.linea{{border-top:1px dashed #000;margin:10px 0}}
.fila{{display:flex;justify-content:space-between;gap:6px;margin:7px 0}}
.fila span:last-child{{text-align:right;overflow-wrap:anywhere}}
.total{{font-size:18px;font-weight:bold}}
.pie{{text-align:center;font-size:10px}}
@media screen{{body{{background:#eee;padding:20px}}.ticket{{background:#fff;box-shadow:0 1px 8px #aaa}}}}
</style></head><body><main class="ticket"><h1>VALLE DE ROMERAL SPA</h1><div class="razon">RUT: {e(rut)}</div><p class="pie">Giro: Centro Turístico<br>Puntilla de Romeral s/n - Hijuelas<br>info@vallederomeral.cl</p><p class="pie">ROMERAL · Control de accesos</p>\n{'<div class="aviso">EJEMPLO FICTICIO · SIN VENTA REGISTRADA</div>' if ejemplo else ''}
<div class="aviso">COMPROBANTE INTERNO<br>NO ES BOLETA ELECTRÓNICA<br>NO VÁLIDO COMO DOCUMENTO TRIBUTARIO</div>
<div class="linea"></div>
<div class="fila"><span>Venta</span><span>{identificador}</span></div>
<div class="fila"><span>Fecha</span><span>{e(fecha).replace('T',' ')}</span></div>
<div class="fila"><span>Servicio</span><span class="servicio">{e('Cabañas' if tipo=='Alojamiento' else tipo)}</span></div>
<div class="fila"><span>Personas</span><span>{int(personas)}</span></div>
<div class="fila"><span>Pago</span><span>{e(medio)}</span></div>
<div class="linea"></div>
<div class="fila total"><span>TOTAL</span><span>{pesos}</span></div>
<p class="pie">Monto registrado, IVA incluido.</p>
<div class="linea"></div>
<p class="pie">Estado electrónico: {e(estado)}<br>
No reemplaza la boleta tributaria.<br>Emisión electrónica deshabilitada.</p>
<div style="height:12mm"></div></main></body></html>"""
    carpeta=Path(carpeta);carpeta.mkdir(parents=True,exist_ok=True)
    destino=carpeta/f'ROMERAL_comprobante_interno_{identificador}.html'
    destino.write_text(html,encoding='utf-8')
    return destino
