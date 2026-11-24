"""ROMERAL 1.9: diagnóstico conservador de CAF DTE 39, exclusivamente lectura.
Nunca transmite el contenido CAF, no invoca Procesar y no almacena credenciales.
"""
import base64
import json
from datetime import date, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

CONFIG = Path.home() / 'Documents' / 'ROMERAL_Datos' / 'facturacion_produccion.json'
SERVICE = 'ROMERAL_FACTURACION_PRODUCCION'
WSDL = 'https://wss.facturacion.cl/WSDS/wsplano.asmx?wsdl'

def cod(value):
    return base64.b64encode(str(value).encode('utf-8')).decode('ascii')

def _tag(element):
    return element.tag.split('}')[-1].lower() if isinstance(element.tag, str) else ''

def _fecha(value):
    value = (value or '').strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        pass
    for fmt in ('%d/%m/%Y', '%d-%m-%Y', '%Y%m%d'):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None

def analizar_caf(raw, hoy=None):
    """Retorna un resumen sin identificadores ni valores de folios.
    No confunde estructura de respuesta con autenticación aceptada.
    """
    hoy = hoy or date.today()
    if not isinstance(raw, str) or not raw.strip():
        return 'Respuesta vacía. Autenticación NO CONFIRMADA. Emisión BLOQUEADA.'
    if len(raw) > 500_000:
        return 'Respuesta demasiado extensa para analizar. Revisión manual. Emisión BLOQUEADA.'
    try:
        root = ET.fromstring('<romeral_respuesta>' + raw + '</romeral_respuesta>')
    except ET.ParseError:
        return 'Respuesta recibida, XML no interpretable. Autenticación NO CONFIRMADA. Emisión BLOQUEADA.'
    campos = {'idcaf','tipodte','foliodesde','foliohasta','fecha','fechavencimiento','cantidad','foliosiguiente'}
    presentes = sorted({_tag(e) for e in root.iter()} & campos)
    if not presentes:
        return 'Sin campos CAF reconocibles. Autenticación NO CONFIRMADA. Emisión BLOQUEADA.'
    # Cada CAF debe ser un conjunto inequívoco de campos dentro de un mismo elemento padre.
    grupos = []
    for parent in root.iter():
        children = list(parent)
        direct = {_tag(e): (e.text or '').strip() for e in children if _tag(e) in campos}
        if len(direct) >= 3 and any(k in direct for k in ('foliosiguiente','foliodesde','foliohasta')):
            grupos.append(direct)
    # Algunos proveedores devuelven campos directamente bajo la raíz sintética.
    if not grupos:
        direct = {_tag(e): (e.text or '').strip() for e in root if _tag(e) in campos}
        if len(direct) >= 3:
            grupos.append(direct)
    lines = ['Consulta SOAP recibida.', 'Campos CAF detectados: ' + ', '.join(presentes) + '.',
             'Autenticación: NO CONFIRMADA formalmente (requiere criterio oficial del proveedor).']
    if not grupos:
        lines += ['Los campos no forman un registro CAF inequívoco.', 'Disponibilidad de folios: NO VERIFICABLE.']
    elif len(grupos) != 1:
        lines += ['Se detectaron varios registros o estructuras CAF.', 'Disponibilidad de folios: REVISIÓN MANUAL.']
    else:
        g = grupos[0]
        try:
            tipo = int(g.get('tipodte',''))
            desde = int(g.get('foliodesde',''))
            hasta = int(g.get('foliohasta',''))
            siguiente = int(g.get('foliosiguiente',''))
            if tipo != 39 or desde <= 0 or hasta < desde:
                lines.append('Tipo DTE o rango CAF: NO VÁLIDO para DTE 39.')
            elif siguiente < desde or siguiente > hasta:
                lines.append('Siguiente folio: FUERA DEL RANGO indicado.')
            else:
                lines.append('Siguiente folio: DENTRO DEL RANGO informado.')
        except (TypeError, ValueError):
            lines.append('Rango o siguiente folio: NO VERIFICABLE (campos faltantes o no numéricos).')
        venc = _fecha(g.get('fechavencimiento'))
        if venc is None:
            lines.append('Vigencia CAF: NO VERIFICABLE (fecha ausente o no reconocida).')
        elif venc < hoy:
            lines.append('Vigencia CAF: VENCIDA.')
        else:
            lines.append('Vigencia CAF: fecha de vencimiento no superada.')
    lines += ['Esta revisión NO acredita por sí sola folios utilizables ni autenticación aceptada.',
              'Emisión: BLOQUEADA. No se ejecutó Procesar.']
    return '\n'.join(lines)


def diagnostico_estructura(raw):
    """Solo etiquetas permitidas, presencia y clases de valores; nunca datos de CAF."""
    import re
    if not isinstance(raw, str) or not raw.strip():
        return 'Estructura: respuesta vacía.'
    if len(raw) > 500_000:
        return 'Estructura: respuesta demasiado extensa.'
    try:
        root = ET.fromstring('<romeral_respuesta>' + raw + '</romeral_respuesta>')
    except ET.ParseError:
        return 'Estructura: XML no interpretable; consultar al proveedor.'
    allowed = ('idcaf','tipodte','foliodesde','foliohasta','fecha','fechavencimiento','cantidad','foliosiguiente')
    status = ('resultado','estado','error','mensaje','descripcion','codigo','fault','faultstring','success','respuesta')
    nodes = list(root.iter())
    def classification(v):
        v = (v or '').strip()
        if not v: return 'vacío'
        if re.fullmatch(r'[0-9]+', v): return 'numérico'
        if _fecha(v): return 'fecha reconocible'
        if v.lower() in ('true','false','ok','error','success','fail','failed'): return 'indicador de estado'
        if v.startswith('<') or v.startswith('&lt;'): return 'posible XML anidado'
        if re.fullmatch(r'[A-Za-z0-9+/=]{32,}',v): return 'texto codificado o identificador'
        return 'texto no interpretado'
    lines = ['DIAGNÓSTICO ESTRUCTURAL (sin valores privados)']
    lines.append('Elementos XML detectados: '+str(len(nodes)-1))
    for name in allowed:
        matches=[n for n in nodes if _tag(n)==name]
        if matches:
            classes=sorted({classification(n.text) for n in matches})
            lines.append(name+': '+str(len(matches))+' campo(s), '+', '.join(classes))
        else:
            lines.append(name+': ausente')
    indicators=sorted({_tag(n) for n in nodes if _tag(n) in status})
    lines.append('Etiquetas de estado/error presentes: '+(', '.join(indicators) if indicators else 'ninguna reconocida'))
    # No inferir autenticación a partir de etiquetas o de un estado no documentado.
    lines.append('Interpretación oficial de autenticación: PENDIENTE.')
    lines.append('Para resolverlo, solicitar a Facturacion.com esquema y ejemplo anonimizado de ConsultarCAF DTE 39.')
    lines.append('Emisión: BLOQUEADA; operación Procesar NO invocada.')
    return '\n'.join(lines)

def consultar_caf_seguro():
    import keyring
    from requests import Session
    from zeep import Client
    from zeep.transports import Transport
    data = json.loads(CONFIG.read_text(encoding='utf-8'))
    if data.get('ambiente') != 'produccion' or not data.get('rut') or not data.get('usuario'):
        return 'Configuración de producción incompleta. Emisión BLOQUEADA.'
    password = keyring.get_password(SERVICE, 'clave')
    if not password:
        return 'Contraseña de producción no disponible en llavero. Emisión BLOQUEADA.'
    puerto = str(data.get('puerto','0'))
    session = Session()
    session.verify = True
    client = Client(WSDL, transport=Transport(session=session, timeout=20, operation_timeout=20))
    port = client.bind('wsplano','wsplanoSoap')
    login = {'Usuario':cod(data['usuario']), 'Rut':cod(data['rut']),
             'Clave':cod(password), 'Puerto':cod(puerto), 'IncluyeLink':'0'}
    # Una sola consulta autorizada, sin reintentos ni emisión.
    result = port.ConsultarCAF(login=login, tipoDTE=cod('39'))
    return analizar_caf(str(result or '')) + '\n\n' + diagnostico_estructura(str(result or ''))
