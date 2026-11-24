"""Validación estructural local basada en el manual TXT de Facturacion.cl.
No valida aceptación remota ni ejecuta Procesar.
"""
from integracion_facturacion import VentaBoleta, generar_txt

def validar(venta):
    txt=generar_txt(venta)
    lineas=txt.splitlines()
    if len(lineas)!=6: raise ValueError('Número de líneas inesperado')
    etiquetas=['->Boleta<-','->BoletaTotales<-','->BoletaDetalle<-']
    for i,etiqueta in enumerate(etiquetas):
        if lineas[2*i]!=etiqueta: raise ValueError('Etiqueta u orden inválido')
    campos=[lineas[i].split(';') for i in (1,3,5)]
    if any(c[-1]!='' for c in campos): raise ValueError('Falta terminador de campo')
    if [len(c)-1 for c in campos] != [16,8,13]: raise ValueError('Cantidad de campos incorrecta')
    b,t,d=[c[:-1] for c in campos]
    if b[0]!='39' or b[1]!='0' or b[3]!='3' or b[4]!='0': raise ValueError('Encabezado DTE incorrecto')
    if t[0] or t[2] or t[3]!=str(venta.total) or t[5]!=str(venta.total) or t[7]!=str(venta.total): raise ValueError('Totales incompatibles')
    if d[0]!='1' or d[3]!='0' or d[4]!='1' or d[5]!=str(venta.total) or d[7]!=str(venta.total): raise ValueError('Detalle incompatible')
    if '\n\n' in txt: raise ValueError('Líneas en blanco')
    return txt
