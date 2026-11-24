"""Pruebas locales sin conexión, sin emisión ni consumo de folios."""
from monitor_folios import interpretar

def probar():
    xml='<CAF><IdCAF>12</IdCAF><TipoDTE>39</TipoDTE><Fecha>2026-11-17</Fecha><FechaVencimiento>2027-11-17</FechaVencimiento><RangoDesde>26000</RangoDesde><RangoHasta>27000</RangoHasta><Cantidad>1001</Cantidad><FolioSiguiente>26187</FolioSiguiente></CAF>'
    resultado=interpretar(xml)
    assert resultado['cantidad']==814,resultado
    assert interpretar(xml.replace('RangoDesde','FolioDesde').replace('RangoHasta','FolioHasta'))['cantidad']==814
    assert interpretar(xml.replace('26187','27001'))['cantidad']==0
    try:
        interpretar(xml.replace('<TipoDTE>39</TipoDTE>','<TipoDTE>33</TipoDTE>'))
    except ValueError:pass
    else:raise AssertionError('No debe aceptar DTE33')
    try:
        interpretar(xml.replace('26187','28000'))
    except ValueError:pass
    else:raise AssertionError('No debe aceptar folio fuera de rango')
    print('OK: 5 pruebas de interpretación CAF, sin conexión ni emisión')

if __name__=='__main__':probar()
