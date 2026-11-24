"""Generación de boletas TXT tipo 39 y cliente SOAP de pruebas (sin emisión automática).
Documentación: facturacion.cl/manualintegracion/{archivoboletaelectronica,integracionservicioweb}.php
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
import base64
import os
import xml.etree.ElementTree as ET

WSDL = 'https://wss.facturacion.cl/WSDS/wsplano.asmx?wsdl'
TIPO_DTE = 39

@dataclass(frozen=True)
class VentaBoleta:
    referencia: str
    tipo: str
    personas: int
    total: int
    medio: str
    fecha: str = ''

    def validar(self):
        if self.tipo not in ('Entrada General', 'Cabañas', 'Camping', 'Piscina Temperada'):
            raise ValueError('Modalidad no válida')
        if not isinstance(self.personas, int) or self.personas < 1:
            raise ValueError('Cantidad de personas inválida')
        if not isinstance(self.total, int) or self.total < 1:
            raise ValueError('Monto final inválido')
        if self.medio not in ('Efectivo', 'Webpay', 'Tarjeta'):
            raise ValueError('Medio de pago inválido')
        if not self.referencia or any(c in self.referencia for c in ';\r\n'):
            raise ValueError('Referencia inválida')


def _etiqueta(nombre, campos):
    return f'->{nombre}<-\n' + ';'.join(map(str, campos)) + ';\n'


def generar_txt(venta: VentaBoleta):
    """Documento de una línea, en monto bruto. Folio=0 solicita autoasignación al proveedor.
    Para montos manuales se usa 1 unidad de servicio y se indican personas en la descripción,
    evitando precios fraccionarios o diferencias de redondeo.
    """
    venta.validar()
    fecha = venta.fecha or date.today().isoformat()
    date.fromisoformat(fecha)
    # Una línea de servicio por el importe íntegro evita diferencias por redondeo.
    # El número de personas queda expresado en la descripción.
    descripcion = f'{venta.tipo} - {venta.personas} persona(s)'
    if len(descripcion) > 80:
        raise ValueError('Descripción demasiado larga')
    if any(c in descripcion for c in ';\r\n'):
        raise ValueError('Descripción incompatible con TXT')
    encabezado = [39, 0, fecha, 3, 0, '', '', '', '66666666-6', '', 'CLIENTE GENERICO', '', '', '', '', '']
    # Para montos brutos, Neto e IVA no se informan (manual del proveedor).
    totales = ['', 0, '', venta.total, 0, venta.total, 0, venta.total]
    detalle = [1, 'ROMERAL', descripcion, 0, 1, venta.total, 0,
               venta.total, 'INT1', 'UN', f'Referencia ROMERAL {venta.referencia}', '', '']
    # El manual de Boleta TXT define las etiquetas Boleta, BoletaTotales y
    # BoletaDetalle; no incluye FormaPagoBoleta en su estructura documentada.
    return (_etiqueta('Boleta', encabezado) + _etiqueta('BoletaTotales', totales)
            + _etiqueta('BoletaDetalle', detalle))


def preparar_archivo(venta, ruta):
    """Exportación local para inspección; NO transmite ni emite."""
    destino = Path(ruta)
    destino.write_text(generar_txt(venta), encoding='utf-8')
    return destino


class IntegracionNoHabilitada(RuntimeError):
    pass


class ClienteSOAPPruebas:
    """Conector opt-in, nunca invocado por el botón de caja.
    Credenciales solo de entorno local, sin incrustarlas ni registrar respuestas con secretos.
    Requiere pip install zeep. No reintentar si el resultado es incierto.
    """
    def __init__(self):
        self.usuario = os.environ.get('ROMERAL_TEST_USUARIO', '')
        self.rut = os.environ.get('ROMERAL_TEST_RUT', '')
        self.clave = os.environ.get('ROMERAL_TEST_CLAVE', '')

    def _cliente(self):
        try:
            from zeep import Client
        except ImportError as exc:
            raise IntegracionNoHabilitada('Instalar zeep en entorno de pruebas') from exc
        return Client(WSDL)

    def online(self):
        return self._cliente().service.Online()

    def procesar_una_vez(self, venta, autorizacion_explicita=False):
        if not autorizacion_explicita:
            raise IntegracionNoHabilitada('Transmisión bloqueada sin autorización explícita')
        if not all((self.usuario, self.rut, self.clave)):
            raise IntegracionNoHabilitada('Faltan credenciales de PRUEBAS en variables de entorno')
        if self.rut != '1-9':
            raise IntegracionNoHabilitada('Solo se admite RUT de pruebas 1-9; producción bloqueada')
        cod = lambda x: base64.b64encode(str(x).encode('utf-8')).decode('ascii')
        login = {'Usuario':cod(self.usuario), 'Rut':cod(self.rut),
                 'Clave':cod(self.clave), 'Puerto':cod('0'), 'IncluyeLink':'1'}
        contenido = cod(generar_txt(venta))
        # NO existe reintento automático: ante timeout, estado indeterminado hasta conciliación.
        return self._cliente().service.Procesar(login=login, file=contenido, formato=1)


def interpretar_resultado(xml_respuesta):
    """Solo confirmar folio cuando éxito global y del documento sean explícitos."""
    if not isinstance(xml_respuesta, str):
        raise ValueError('Respuesta inesperada; revisión manual requerida')
    raiz = ET.fromstring(xml_respuesta)
    def buscar(nodo, etiqueta):
        for e in nodo.iter():
            if e.tag.split('}')[-1].lower() == etiqueta.lower():
                return (e.text or '').strip()
        return ''
    global_ok = buscar(raiz, 'Resultado').lower() == 'true'
    documentos = [e for e in raiz.iter() if e.tag.split('}')[-1].lower() == 'documento']
    if not global_ok or len(documentos) != 1:
        return {'confirmado': False, 'folio': None, 'estado': 'REVISAR'}
    doc = documentos[0]
    folio = buscar(doc, 'Folio')
    confirmado = (buscar(doc, 'Resultado').lower() == 'true' and
                  buscar(doc, 'TipoDte') == '39' and folio.isdigit() and int(folio) > 0)
    return {'confirmado': confirmado, 'folio': folio if confirmado else None,
            'estado': 'EMITIDA' if confirmado else 'REVISAR'}
