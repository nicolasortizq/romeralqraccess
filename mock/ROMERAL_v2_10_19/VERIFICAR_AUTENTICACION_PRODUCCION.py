"""Consulta SOAP de solo lectura con un folio ya emitido. Nunca invoca Procesar."""
import json
from pathlib import Path
from validacion_produccion import CONFIG, SERVICE, WSDL, cod

FOLIO_EXISTENTE = '26185'  # Folio real ya verificado por el operador; no se emite otro.

def main():
    print('ROMERAL - VERIFICACION DE ACCESO PRODUCTIVO (SOLO LECTURA)')
    print('Operacion: ObtenerLink, DTE 39, folio existente '+FOLIO_EXISTENTE)
    print('NO emite boletas, NO modifica configuracion, NO consume folios.')
    if not CONFIG.is_file():
        print('RESULTADO: FALTA_CONFIGURACION');return 2
    config=json.loads(CONFIG.read_text(encoding='utf-8'))
    if config.get('ambiente')!='produccion' or not config.get('rut') or not config.get('usuario'):
        print('RESULTADO: CONFIGURACION_PRODUCTIVA_INCOMPLETA');return 2
    try:
        import keyring
        clave=keyring.get_password(SERVICE,'clave')
    except Exception as exc:
        print('RESULTADO: ERROR_ALMACEN_CREDENCIALES: '+type(exc).__name__);return 2
    if not clave:
        print('RESULTADO: SIN_CLAVE_EN_ALMACEN');return 2
    try:
        from requests import Session
        from zeep import Client
        from zeep.transports import Transport
        session=Session();session.verify=True
        client=Client(WSDL,transport=Transport(session=session,timeout=15,operation_timeout=25))
        port=client.bind('wsplano','wsplanoSoap')
        login={'Usuario':cod(config['usuario']),'Rut':cod(config['rut']),
               'Clave':cod(clave),'Puerto':cod(str(config.get('puerto','0'))),
               'IncluyeLink':'0'}
        response=port.ObtenerLink(login=login,tpomov=cod('B'),folio=cod(FOLIO_EXISTENTE),tipo=cod('39'),cedible=cod('False'))
        # Do not print response: may contain document links, identifiers or private data.
        raw=str(response or '')
        from recuperacion_pdf import _urls
        if _urls(raw):
            print('RESULTADO: CONSULTA_DOCUMENTO_EXISTENTE_EXITOSA')
            print('Credenciales aceptadas para ObtenerLink. NO demuestra permiso para Procesar.')
            return 0
        print('RESULTADO: RESPUESTA_SIN_ENLACE_RECONOCIBLE')
        print('No se puede concluir si la autenticacion es valida; revisar en portal/proveedor.')
        return 1
    except Exception as exc:
        print('RESULTADO: CONSULTA_NO_CONFIRMADA')
        print('Tipo de error: '+type(exc).__name__)
        print('No se muestra detalle para proteger datos privados.');return 1

if __name__=='__main__':
    raise SystemExit(main())
