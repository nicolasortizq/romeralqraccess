"""Consulta de CAF DTE39 de solo lectura; no invoca Procesar ni reserva folios."""
import json, time, base64, re
from collections import Counter
from pathlib import Path
from datetime import datetime
from xml.etree import ElementTree as ET
from validacion_produccion import CONFIG, SERVICE, WSDL, cod

DATA_DIR=Path.home()/'Documents'/'ROMERAL_Datos'
LOG=DATA_DIR/'romeral_consultas_folios.jsonl'

def _tag(e): return e.tag.split('}')[-1].lower()
def _int(v):
    if not re.fullmatch(r'\d{1,12}',str(v or '').strip()): raise ValueError('Número CAF inválido')
    return int(v)
def interpretar(raw):
    """Interpreta CAF DTE 39, sin confundir el rango autorizado con saldo certificado."""
    if not isinstance(raw,str) or not raw.strip() or len(raw)>500000:
        raise ValueError('Respuesta CAF vacía o demasiado extensa')
    try:
        root=ET.fromstring('<respuesta>'+raw+'</respuesta>')
    except ET.ParseError as e:
        raise ValueError('XML CAF no interpretable') from e
    registros=[]
    for padre in root.iter():
        # El servicio devuelve RangoDesde/RangoHasta (confirmado por diagnóstico).
        # Aceptar también los nombres antiguos, pero no mezclar campos de CAF distintos.
        d={_tag(e):(e.text or '').strip() for e in padre}
        if 'tipodte' not in d or 'foliosiguiente' not in d:
            continue
        desde_txt=d.get('rangodesde') or d.get('foliodesde')
        hasta_txt=d.get('rangohasta') or d.get('foliohasta')
        if not desde_txt or not hasta_txt:
            continue
        tipo=_int(d['tipodte'])
        if tipo!=39:
            continue
        desde=_int(desde_txt); hasta=_int(hasta_txt); sig=_int(d['foliosiguiente'])
        if desde<1 or hasta<desde or sig<desde or sig>hasta+1:
            raise ValueError('Rango CAF inconsistente')
        # Cantidad no se interpreta como saldo: puede ser tamaño del CAF.
        registros.append({'desde':desde,'hasta':hasta,'siguiente':sig,
                          'estimado':max(0,hasta-sig+1),
                          'vencimiento':d.get('fechavencimiento','')})
    if not registros:
        raise ValueError('Sin rango CAF DTE39 verificable en respuesta')
    intervalos=sorted((r['desde'],r['hasta']) for r in registros)
    if len(set(intervalos))!=len(intervalos) or any(intervalos[i][0]<=intervalos[i-1][1] for i in range(1,len(intervalos))):
        raise ValueError('Rangos CAF repetidos o superpuestos')
    return {'estado':'ESTIMADO_CAF','cantidad':sum(r['estimado'] for r in registros),
            'rangos':registros,
            'advertencia':'Estimación según rango CAF y FolioSiguiente informados por Facturacion.com; no certifica saldo utilizable ni reservas/emisiones externas.'}

def consultar():
    import keyring
    from requests import Session
    from zeep import Client
    from zeep.transports import Transport
    cfg=json.loads(CONFIG.read_text(encoding='utf-8'))
    if cfg.get('ambiente')!='produccion' or not cfg.get('rut') or not cfg.get('usuario'): raise ValueError('Configuración producción incompleta')
    clave=keyring.get_password(SERVICE,'clave')
    if not clave: raise ValueError('Credencial de producción no disponible en llavero')
    session=Session();session.verify=True
    cliente=Client(WSDL,transport=Transport(session=session,timeout=15,operation_timeout=15))
    port=cliente.bind('wsplano','wsplanoSoap')
    login={'Usuario':cod(cfg['usuario']),'Rut':cod(cfg['rut']),'Clave':cod(clave),
           'Puerto':cod(cfg.get('puerto','0')),'IncluyeLink':'0'}
    result=port.ConsultarCAF(login=login,tipoDTE=cod('39'))
    respuesta=str(result or '')
    try:
        return interpretar(respuesta)
    except ValueError as exc:
        # Diagnóstico mínimo: estructura y nombres de etiquetas, nunca valores ni credenciales.
        resumen=diagnosticar_estructura(respuesta)
        guardar_diagnostico(resumen)
        raise ValueError(f'{exc}. Diagnóstico seguro guardado en romeral_diagnostico_caf.jsonl') from exc

def guardar(resultado):
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    registro={'fecha':datetime.now().isoformat(timespec='seconds'),**resultado}
    # Nunca almacenar la respuesta SOAP ni credenciales.
    with LOG.open('a',encoding='utf-8') as f: f.write(json.dumps(registro,ensure_ascii=False)+'\n')
    return registro

def ultimo():
    try:
        with LOG.open(encoding='utf-8') as f:
            lineas=f.readlines()
        return json.loads(lineas[-1]) if lineas else None
    except (OSError,ValueError,IndexError): return None


def diagnosticar_estructura(respuesta):
    """Inspección sin valores de la respuesta del proveedor; no emite DTE."""
    import hashlib
    datos={'longitud_respuesta':len(respuesta),'sha256_respuesta':hashlib.sha256(respuesta.encode('utf-8')).hexdigest(),
           'tipo_respuesta':'texto','etiquetas':{},'xml_valido':False}
    try:
        raiz=ET.fromstring('<raiz>'+respuesta+'</raiz>')
        datos['xml_valido']=True
        # Solo nombres de elementos que no parecen contener credenciales.
        etiquetas=Counter(_tag(n) for n in raiz.iter())
        prohibidas=('clave','password','pass','token','secret','usuario','rut','auth','firma','cert','apikey','session')
        datos['etiquetas']={k:v for k,v in etiquetas.most_common(50) if not any(x in k for x in prohibidas)}
    except ET.ParseError:
        datos['xml_valido']=False
    return datos

def guardar_diagnostico(datos):
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    ruta=DATA_DIR/'romeral_diagnostico_caf.jsonl'
    with ruta.open('a',encoding='utf-8') as f:
        f.write(json.dumps({'fecha':datetime.now().isoformat(timespec='seconds'),**datos},ensure_ascii=False)+'\n')
