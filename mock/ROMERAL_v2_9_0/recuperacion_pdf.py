"""Recuperación SOLO LECTURA de PDF oficial. Nunca llama Procesar."""
import base64
import hashlib
import ipaddress
import json
import os
import re
import sqlite3
import socket
from pathlib import Path
from urllib.parse import urlparse
from html import unescape
from datetime import datetime
from xml.etree import ElementTree as ET
from validacion_produccion import CONFIG, SERVICE, WSDL, cod

DATA=Path.home()/'Documents'/'ROMERAL_Datos'

def _n(tag): return tag.split('}')[-1].lower()
def _decode(v):
    """Decode provider URL, including base64 HTTP legacy links.

    Upgrade only the known official provider hostname to HTTPS; never transmit
    document download tokens over plain HTTP.
    """
    v=(v or '').strip()
    if v.startswith(('https://','http://')):
        candidate=v
    else:
        try:
            candidate=base64.b64decode(v,validate=True).decode('utf-8').strip()
        except (ValueError,UnicodeDecodeError,base64.binascii.Error):
            return None
    try:
        p=urlparse(candidate)
        if p.hostname not in ('www.facturacion.cl','facturacion.cl'):
            return None
        if p.username or p.password or p.port not in (None,80,443):
            return None
        if p.scheme=='http':
            # Provider supplies legacy HTTP links; use encrypted transport only.
            return p._replace(scheme='https',netloc=p.hostname).geturl()
        if p.scheme=='https':return candidate
    except ValueError:
        return None
    return None

def _urls(xml):
    """Accept URL, encoded URL, escaped XML and SOAP XML (no unsafe guessing)."""
    raw=str(xml or '').strip()
    candidates=[raw,unescape(raw)]
    for value in list(candidates):
        try:
            root=ET.fromstring(value)
        except ET.ParseError:
            try: root=ET.fromstring('<root>'+value+'</root>')
            except ET.ParseError: continue
        for node in root.iter():
            if node.text and node.text.strip(): candidates.append(node.text.strip())
            if node.tail and node.tail.strip(): candidates.append(node.tail.strip())
    urls=[]
    for value in candidates:
        u=_decode(value)
        if u and u not in urls: urls.append(u)
    return urls

def _diagnostico(venta_id, response, metodo):
    """Store only structural response data, never URLs, credentials or document contents."""
    raw=str(response or '')
    try:
        root=ET.fromstring(raw)
        tags=sorted({_n(x.tag) for x in root.iter() if isinstance(x.tag,str)})[:30]
    except ET.ParseError:
        tags=[]
    # The provider returns <wsplano><mensaje>...</mensaje></wsplano> on failure.
    # Retain a locally inspectable, redacted diagnostic, not full SOAP payloads.
    messages=[]
    try:
        for node in ET.fromstring(raw).iter():
            if isinstance(node.tag,str) and _n(node.tag)=='mensaje':
                msg=' '.join(''.join(node.itertext()).split())
                if msg:
                    msg=re.sub(r'(?i)(clave|password|contraseña|token|apikey|api_key)\s*[:=]\s*[^\s,;]+',r'\1=[OCULTO]',msg)
                    msg=re.sub(r'(?i)https?://[^\s<>]+','[ENLACE OCULTO]',msg)
                    msg=re.sub(r'(?<!\d)\d{7,8}-[0-9kK](?!\d)','[RUT OCULTO]',msg)
                    msg=re.sub(r'(?i)\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b','[CORREO OCULTO]',msg)
                    messages.append(msg[:400])
    except ET.ParseError:
        pass
    info={'fecha':datetime.now().isoformat(timespec='seconds'),
          'venta':int(venta_id),'metodo':metodo,
          'tipo_respuesta':type(response).__name__,
          'longitud':len(raw),'parece_xml':raw.lstrip().startswith('<'),
          'parece_url':raw.lstrip().startswith('https://'),
          'etiquetas_xml':tags,
          'contiene_pdf_base64':raw.startswith('JVBERi0'),
          'mensaje_proveedor_revisar_antes_de_compartir':messages[:3],
          'sha256_respuesta':hashlib.sha256(raw.encode('utf-8')).hexdigest()}
    path=DATA/f'romeral_diagnostico_pdf_venta_{int(venta_id)}.json'
    path.write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    return path

def _safe_url(url):
    p=urlparse(url)
    if p.scheme!='https' or p.hostname not in ('www.facturacion.cl','facturacion.cl') or p.username or p.password or p.port not in (None,443):
        raise RuntimeError('Enlace PDF inseguro o no HTTPS')
    if p.hostname.lower() in ('localhost',) or p.hostname.endswith(('.local','.internal')):
        raise RuntimeError('Enlace PDF no público')
    for item in socket.getaddrinfo(p.hostname,443,type=socket.SOCK_STREAM):
        ip=ipaddress.ip_address(item[4][0])
        if not ip.is_global:raise RuntimeError('Enlace PDF apunta a una red privada')

def recuperar(venta_id):
    """Solo ventas emitidas y conciliadas. Retorna ruta PDF oficial, sin imprimir."""
    import keyring
    import requests
    from zeep import Client
    from zeep.transports import Transport
    with sqlite3.connect(DATA/'romeral.sqlite3') as db:
        row=db.execute("SELECT estado_boleta,folio_dte,tipo_dte FROM ventas WHERE id=?",(venta_id,)).fetchone()
        if not row or row[0]!='EMITIDA' or not row[1] or row[2]!=39:
            raise RuntimeError('Venta sin DTE 39 confirmado; no se descargará documento')
        folio=str(row[1])
    folder=DATA/'boletas_oficiales';folder.mkdir(exist_ok=True)
    dest=folder/f'ROMERAL_DTE39_{folio}_venta_{venta_id}.pdf'
    if dest.exists() and dest.read_bytes()[:5]==b'%PDF-':return dest
    urls=[]
    evidencia=DATA/f'romeral_soap_respuesta_venta_{venta_id}.xml'
    if evidencia.is_file():urls=_urls(evidencia.read_text(encoding='utf-8'))
    if not urls:
        cfg=json.loads(CONFIG.read_text(encoding='utf-8'))
        password=keyring.get_password(SERVICE,'clave')
        if not password:raise RuntimeError('Faltan credenciales del llavero')
        session=requests.Session();session.verify=True
        client=Client(WSDL,transport=Transport(session=session,timeout=20,operation_timeout=30))
        port=client.bind('wsplano','wsplanoSoap')
        login={'Usuario':cod(cfg['usuario']),'Rut':cod(cfg['rut']),'Clave':cod(password),
               'Puerto':cod(str(cfg.get('puerto','0'))),'IncluyeLink':'1'}
        response=port.ObtenerLink(login=login,tpomov=cod('B'),folio=cod(folio),tipo=cod('39'),cedible=cod('False'))
        urls=_urls(response)
        if not urls:
            diag=_diagnostico(venta_id,response,'ObtenerLink')
            raise RuntimeError('ObtenerLink no devolvió una URL HTTPS reconocible. '
                               f'Diagnóstico sin datos sensibles: {diag.name}. '
                               'No se emitió otra boleta.')
    if not urls:raise RuntimeError('El proveedor no entregó un enlace PDF válido. No se reemitió la boleta.')
    url=urls[0]
    _safe_url(url)
    with requests.Session() as s:
        s.trust_env=True
        r=s.get(url,timeout=35,allow_redirects=False)
        if r.status_code!=200:raise RuntimeError(f'Descarga PDF: HTTP {r.status_code}')
        content=r.content
    if not content.startswith(b'%PDF-') or len(content)>10_000_000:
        raise RuntimeError('El enlace no devolvió un PDF oficial válido')
    tmp=dest.with_suffix('.tmp')
    with open(tmp,'wb') as f:
        f.write(content);f.flush();os.fsync(f.fileno())
    os.replace(tmp,dest)
    return dest
