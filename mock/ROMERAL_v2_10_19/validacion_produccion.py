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
    """Interpretación conservadora: no adivina fechas ambiguas."""
    import re
    value = str(value or '').strip()
    if not value:
        return None
    # Formatos ISO, incluyendo hora, zona horaria y fracciones.
    iso = re.fullmatch(r'(\d{4}-\d{2}-\d{2})(?:[Tt ]\d{2}:\d{2}(?::\d{2}(?:[.,]\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?', value)
    if iso:
        try:
            return date.fromisoformat(iso.group(1))
        except ValueError:
            return None
    # Fecha compacta inequívoca AAAAMMDD.
    if re.fullmatch(r'\d{8}', value):
        try:
            return datetime.strptime(value, '%Y%m%d').date()
        except ValueError:
            return None
    # DD/MM/AAAA o DD-MM-AAAA (convención chilena).
    for fmt in ('%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y'):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    # Variantes con hora al final; no interpretar números sueltos como fechas.
    m = re.fullmatch(r'(\d{2}[./-]\d{2}[./-]\d{4})[ T]\d{1,2}:\d{2}(?::\d{2}(?:[.,]\d+)?)?(?:\s*(?:AM|PM))?', value, re.I)
    if m:
        return _fecha(m.group(1))
    # /Date(UnixMilliseconds)/ es el formato JSON de fechas Microsoft.
    m = re.fullmatch(r'/Date\((-?\d{11,14})(?:[+-]\d{4})?\)/', value)
    if m:
        try:
            return datetime.fromtimestamp(int(m.group(1)) / 1000).date()
        except (ValueError, OverflowError, OSError):
            return None
    return None

def _sin_vencimiento(value):
    """Reconoce solo variantes textuales inequívocas de NO VENCE."""
    import re
    import unicodedata
    v = unicodedata.normalize('NFKC', str(value or '')).strip().upper()
    v = re.sub(r'\s+', ' ', v)
    v = v.rstrip(' .')
    return v == 'NO VENCE'

def _patron_privado(value):
    """Perfil de caracteres sin publicar el contenido del campo."""
    import unicodedata
    v = str(value or '').strip()
    groups = []
    for c in v:
        cat = unicodedata.category(c)
        code = 'L' if cat.startswith('L') else 'D' if cat.startswith('N') else 'E' if c.isspace() else 'P' if cat.startswith('P') else 'S'
        if groups and groups[-1][0] == code:
            groups[-1] = (code, groups[-1][1] + 1)
        else:
            groups.append((code, 1))
    return ' '.join(f'{k}{n}' for k,n in groups) or 'vacío'

def _perfil_fecha(value):
    """Describe el formato sin exponer su contenido."""
    import re
    v = str(value or '').strip()
    if not v:
        return 'vacío'
    if re.fullmatch(r'\d{1,14}', v):
        return f'solo dígitos ({len(v)} caracteres; no inferir unidad)'
    if re.fullmatch(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}.*', v):
        return 'año primero, con sufijo'
    if re.fullmatch(r'\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}.*', v):
        return 'día/mes o mes/día, con sufijo'
    if v.startswith('/Date('):
        return 'fecha serializada estilo Microsoft'
    return f'otro formato ({len(v)} caracteres)'

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
    campos = {'idcaf','tipodte','foliodesde','foliohasta','rangodesde','rangohasta','fecha','fechavencimiento','cantidad','foliosiguiente'}
    presentes = sorted({_tag(e) for e in root.iter()} & campos)
    if not presentes:
        return 'Sin campos CAF reconocibles. Autenticación NO CONFIRMADA. Emisión BLOQUEADA.'
    # Cada CAF debe ser un conjunto inequívoco de campos dentro de un mismo elemento padre.
    grupos = []
    for parent in root.iter():
        children = list(parent)
        direct = {_tag(e): (e.text or '').strip() for e in children if _tag(e) in campos}
        if len(direct) >= 3 and any(k in direct for k in ('foliosiguiente','foliodesde','foliohasta','rangodesde','rangohasta')):
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
            desde = int(g.get('rangodesde') or g.get('foliodesde',''))
            hasta = int(g.get('rangohasta') or g.get('foliohasta',''))
            siguiente = int(g.get('foliosiguiente',''))
            if tipo != 39 or desde <= 0 or hasta < desde:
                lines.append('Tipo DTE o rango CAF: NO VÁLIDO para DTE 39.')
            elif siguiente < desde or siguiente > hasta + 1:
                lines.append('Siguiente folio: FUERA DEL RANGO indicado.')
            else:
                lines.append('Rango CAF: coherente con DTE 39.')
                if siguiente == hasta + 1:
                    lines.append('Siguiente folio: después del último del rango; saldo estimado 0.')
                else:
                    lines.append('Siguiente folio: DENTRO DEL RANGO informado.')
                    lines.append('Folios restantes estimados en este rango: ' + str(hasta - siguiente + 1) + ' (no certificados).')
        except (TypeError, ValueError):
            lines.append('Rango o siguiente folio: NO VERIFICABLE (campos faltantes o no numéricos).')
        venc = _fecha(g.get('fechavencimiento'))
        if _sin_vencimiento(g.get('fechavencimiento')):
            lines.append('Vencimiento informado por proveedor: NO VENCE (etiqueta textual; no es validación independiente).')
            lines.append('Estado actual de CAF: requiere confirmación del proveedor; emisión BLOQUEADA.')
        elif venc is None:
            lines.append('Vigencia CAF: NO VERIFICABLE (fecha ausente o no reconocida).')
            lines.append('Formato de vencimiento (sin revelar valor): ' + _perfil_fecha(g.get('fechavencimiento')) + '; patrón ' + _patron_privado(g.get('fechavencimiento')) + '.')
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
    allowed = ('idcaf','tipodte','foliodesde','foliohasta','rangodesde','rangohasta','fecha','fechavencimiento','cantidad','foliosiguiente')
    status = ('resultado','estado','error','mensaje','descripcion','codigo','fault','faultstring','success','respuesta')
    nodes = list(root.iter())
    def classification(v):
        v = (v or '').strip()
        if not v: return 'vacío'
        if re.fullmatch(r'[0-9]+', v): return 'numérico'
        if _sin_vencimiento(v): return 'etiqueta NO VENCE (proveedor)'
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
            if name == 'fechavencimiento' and 'fecha reconocible' not in classes and 'etiqueta NO VENCE (proveedor)' not in classes:
                lines.append('fechavencimiento formato (sin valor): ' + ', '.join(sorted({_perfil_fecha(n.text) + '; patrón ' + _patron_privado(n.text) for n in matches})))
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
