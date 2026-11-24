"""ROMERAL v2.10.7: auditoría local PREVIA a emisión. No conecta ni emite."""
import json
import sqlite3
from pathlib import Path

DATA = Path.home() / 'Documents' / 'ROMERAL_Datos'
CONFIG = DATA / 'facturacion_produccion.json'
DB = DATA / 'romeral.sqlite3'

def main():
    print('ROMERAL v2.10.7 | AUDITORIA LOCAL DE SEGURIDAD (SIN EMISION)')
    print('No se consulta Facturacion.com ni se emiten boletas.')
    fallas = []
    if not CONFIG.is_file():
        fallas.append('Falta configuracion de produccion')
    else:
        try:
            cfg = json.loads(CONFIG.read_text(encoding='utf-8'))
            print('Ambiente produccion:', cfg.get('ambiente') == 'produccion')
            print('Identificacion presente:', bool(cfg.get('rut') and cfg.get('usuario')))
            print('Emision habilitada:', cfg.get('emision_habilitada') is True)
            if cfg.get('ambiente') != 'produccion' or not cfg.get('rut') or not cfg.get('usuario'):
                fallas.append('Configuracion productiva incompleta')
            if cfg.get('emision_habilitada') is True:
                print('ADVERTENCIA: emision real habilitada; NO pulse Registrar hasta autorizar venta real')
        except (OSError, ValueError, TypeError) as exc:
            fallas.append('Configuracion no interpretable: '+type(exc).__name__)
    for modulo in ('keyring','requests','zeep'):
        try:
            __import__(modulo)
            print('Dependencia '+modulo+': OK')
        except ImportError:
            fallas.append('Falta dependencia '+modulo)
    try:
        import keyring
        from validacion_produccion import SERVICE
        print('Credencial guardada:', bool(keyring.get_password(SERVICE, 'clave')))
        if not keyring.get_password(SERVICE, 'clave'):
            fallas.append('Credencial de produccion no disponible')
    except Exception as exc:
        fallas.append('Acceso a credenciales: '+type(exc).__name__)
    if not DB.is_file():
        fallas.append('No se encontro la base de datos ROMERAL')
    else:
        try:
            # Abrir en modo read-only, sin crear ni modificar base.
            con=sqlite3.connect(DB.as_uri()+'?mode=ro',uri=True)
            try:
                tablas={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {'ventas','control_emision'}.issubset(tablas):
                    fallas.append('Faltan tablas de control DTE')
                else:
                    pendientes=con.execute("SELECT count(*) FROM control_emision WHERE estado IN ('RESERVADA','INCIERTA','REVISAR')").fetchone()[0]
                    print('Operaciones reservadas/inciertas/a revisar:',pendientes)
                    if pendientes: fallas.append('Existen operaciones que requieren conciliacion manual')
                if 'intentos_soap_dte' in tablas:
                    intentos=con.execute("SELECT count(*) FROM intentos_soap_dte WHERE estado IN ('PREPARADO','ENVIO_INICIADO','INCIERTO')").fetchone()[0]
                    print('Intentos SOAP pendientes o inciertos:',intentos)
                    if intentos: fallas.append('Existen intentos SOAP sin confirmacion')
            finally: con.close()
        except (sqlite3.Error,OSError) as exc:
            fallas.append('No se pudo revisar base: '+type(exc).__name__)
    print('\nRESULTADO:', 'REVISAR: '+ ' | '.join(fallas) if fallas else 'REVISION_LOCAL_OK')
    print('IMPORTANTE: este resultado NO demuestra permiso para Procesar ni autoriza una venta real.')
    return 1 if fallas else 0

if __name__=='__main__':
    raise SystemExit(main())
