"""Reportes de cierres guardados: no modifica la base de datos."""
from pathlib import Path
from html import escape
import json
from datetime import date

def _clp(n):
    return '$'+f'{int(n):,}'.replace(',','.')

def generar_reporte_cierre(r,carpeta):
    if len(r)!=11: raise ValueError('Registro incompleto')
    fecha,creado,esperado,contado,diferencia,webpay,tarjeta,total,personas,ventas,desglose=r
    date.fromisoformat(fecha)
    detalle=json.loads(desglose)
    filas=[]
    for tipo,v in sorted(detalle.items()):
        filas.append(f'<tr><td>{escape(str(tipo))}</td><td>{int(v["personas"])}</td><td>{int(v["ventas"])}</td><td>{_clp(v["total"])}</td></tr>')
    tabla=''.join(filas) or '<tr><td colspan="4">Sin ventas activas al momento del cierre</td></tr>'
    html=f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>ROMERAL cierre histórico {fecha}</title>
<style>body{{font:14px Arial,sans-serif;max-width:780px;margin:28px auto;padding:12px;color:#123}}
table{{border-collapse:collapse;width:100%}}th,td{{padding:9px;border-bottom:1px solid #bbb;text-align:left}}
h1{{font-size:24px}}.aviso{{margin-top:25px;font-size:12px}}
@media print{{body{{margin:10mm}}}}</style></head><body>
<h1>VALLE DE ROMERAL SPA</h1><p>RUT: 78.180.502-5<br>
Cierre interno de caja · {escape(fecha)}<br>Registrado: {escape(str(creado))}</p><hr>
<p>Ventas: {int(ventas)} · Personas: {int(personas)} · Recaudación: <b>{_clp(total)}</b></p>
<table><tr><th>Medio</th><th>CLP</th></tr>
<tr><td>Efectivo esperado</td><td>{_clp(esperado)}</td></tr>
<tr><td>Efectivo contado</td><td>{_clp(contado)}</td></tr>
<tr><td>Diferencia (contado - esperado)</td><td>{_clp(diferencia)}</td></tr>
<tr><td>Webpay</td><td>{_clp(webpay)}</td></tr>
<tr><td>Tarjeta</td><td>{_clp(tarjeta)}</td></tr></table>
<h2>Por tipo de entrada</h2><table><tr><th>Servicio</th><th>Personas</th><th>Ventas</th><th>Total</th></tr>
{tabla}</table><p class="aviso">Reporte histórico de control interno.
No es documento tributario ni confirma emisión de DTE.
Los valores corresponden al momento en que se guardó el cierre.</p>
</body></html>"""
    carpeta=Path(carpeta);carpeta.mkdir(parents=True,exist_ok=True)
    ruta=carpeta/f'ROMERAL_cierre_{fecha}.html'
    ruta.write_text(html,encoding='utf-8')
    return ruta
