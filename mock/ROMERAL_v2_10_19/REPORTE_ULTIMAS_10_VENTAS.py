"""Solo lectura, sin red ni emisión."""
import json
from pathlib import Path
from collections import defaultdict
from statistics import mean
DATA=Path.home()/'Documents'/'ROMERAL_Datos'
archivo=DATA/'romeral_diagnostico_etapas.jsonl'
ventas=defaultdict(dict)
if archivo.exists():
    for linea in archivo.open(encoding='utf-8'):
        try:
            r=json.loads(linea); vid=int(r['venta'])
            if isinstance(r.get('segundos'),(int,float)):ventas[vid][r.get('etapa','?')]=r['segundos']
            if isinstance(r.get('total_desde_inicio'),(int,float)):ventas[vid]['TOTAL_HASTA_COLA_IMPRESION']=r['total_desde_inicio']
        except (ValueError,TypeError,KeyError):pass
completas=[(i,v) for i,v in sorted(ventas.items()) if 'TOTAL_HASTA_COLA_IMPRESION' in v][-10:]
print('Ventas recientes con impresión enviada a cola:',len(completas))
for i,v in completas:print('Venta',i,':',round(v['TOTAL_HASTA_COLA_IMPRESION'],2),'segundos')
if completas:print('Promedio reciente:',round(mean(v['TOTAL_HASTA_COLA_IMPRESION'] for _,v in completas),2),'segundos')
pdf=DATA/'romeral_latencia_pdf.jsonl'; filas=[]
if pdf.exists():
    for linea in pdf.open(encoding='utf-8'):
        try:filas.append(json.loads(linea))
        except ValueError:pass
filas=filas[-10:]
if filas:
    print('Desglose PDF, últimas',len(filas),'descargas:')
    for campo in ('segundos_hasta_link','segundos_validacion','segundos_descarga','segundos_total'):
        valores=[r[campo] for r in filas if campo in r]
        if valores:print(campo,':',round(mean(valores),2),'segundos')
print('No mide la salida física del papel.')
