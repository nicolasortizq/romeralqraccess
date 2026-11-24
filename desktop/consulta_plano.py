"""ROMERAL: consulta CAF DTE 39 de PLANO, estrictamente solo lectura.
No llama Procesar, no guarda respuestas SOAP ni modifica ventas o producción.
"""
import json
from pathlib import Path

CONFIG=Path.home()/'Documents'/'ROMERAL_Datos'/'facturacion_plano.json'
SERVICE='ROMERAL_FACTURACION_PLANO'
# Endpoint que utiliza la integración existente. La aceptación de credenciales
# PLANO por este servicio debe verificarse en el equipo del usuario.
WSDL='https://wss.facturacion.cl/WSDS/wsplano.asmx?wsdl'

def consultar_caf_plano():
    import keyring
    from requests import Session
    from zeep import Client
    from zeep.transports import Transport
    from validacion_produccion import cod
    from monitor_folios import interpretar
    try:
        cfg=json.loads(CONFIG.read_text(encoding='utf-8'))
    except (OSError,ValueError):
        return 'No se encontró configuración PLANO válida. Guarda las credenciales primero.'
    if cfg.get('ambiente')!='plano' or not cfg.get('rut') or not cfg.get('usuario'):
        return 'Configuración PLANO incompleta. No se realizó conexión.'
    clave=keyring.get_password(SERVICE,'clave')
    if not clave:
        return 'No se encontró la clave PLANO en el llavero de Windows.'
    session=Session();session.verify=True
    client=Client(WSDL,transport=Transport(session=session,timeout=20,operation_timeout=20))
    port=client.bind('wsplano','wsplanoSoap')
    login={'Usuario':cod(cfg['usuario']),'Rut':cod(cfg['rut']),
           'Clave':cod(clave),'Puerto':cod(str(cfg.get('puerto','0'))),'IncluyeLink':'0'}
    respuesta=str(port.ConsultarCAF(login=login,tipoDTE=cod('39')) or '')
    if not respuesta.strip():
        return 'El servicio respondió vacío. No se pudo confirmar CAF de prueba.'
    try:
        caf=interpretar(respuesta)
    except ValueError:
        return ('El servicio respondió, pero no se pudo verificar un rango CAF DTE 39.\n'
                'Esto NO confirma autorización para emitir. No se guardó la respuesta.')
    return ('Consulta CAF PLANO recibida y rango DTE 39 coherente.\n'
            'Rangos encontrados: '+str(len(caf['rangos']))+'\n'
            'Folios estimados según rango: '+str(caf['cantidad'])+'\n'
            'Solo lectura: NO se emitió ni reservó ningún folio.\n'
            'Este resultado no valida aún el formato TXT ni Procesar.')
