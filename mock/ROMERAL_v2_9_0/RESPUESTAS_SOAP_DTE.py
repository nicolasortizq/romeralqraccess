"""Interpretación conservadora del XML documentado de Procesar (sin conexiones)."""
import xml.etree.ElementTree as ET

def analizar_respuesta(xml):
    incierta=lambda motivo:{'estado':'INCIERTA','folio':None,'motivo':motivo}
    if not isinstance(xml,str) or len(xml)>1_000_000 or '<!DOCTYPE' in xml.upper() or '<!ENTITY' in xml.upper():
        return incierta('Respuesta inválida')
    try: root=ET.fromstring(xml)
    except ET.ParseError: return incierta('XML no interpretable')
    tag=lambda e:e.tag.rsplit('}',1)[-1].lower() if isinstance(e.tag,str) else ''
    def campo(n,nombre):
        v=[(e.text or '').strip() for e in n if tag(e)==nombre.lower()]
        return v[0] if len(v)==1 else None
    # SOAP puede envolver el documento de resultado; no considerar el sobre
    # como prueba de éxito. Solo aceptar un wsplano inequívoco.
    if tag(root)!='wsplano':
        candidatos=[e for e in root.iter() if tag(e)=='wsplano']
        if len(candidatos)!=1: return incierta('Documento wsplano ausente o ambiguo')
        root=candidatos[0]
    docs=[e for e in root.iter() if tag(e)=='documento']
    if len(docs)!=1: return incierta('Cantidad de documentos distinta de uno')
    doc=docs[0]; global_ok=campo(root,'Resultado'); doc_ok=campo(doc,'Resultado')
    folio=campo(doc,'Folio'); tipo=campo(doc,'TipoDte'); operacion=campo(doc,'Operacion')
    if global_ok and doc_ok and global_ok.lower()=='true' and doc_ok.lower()=='true' and tipo=='39' and folio and folio.isascii() and folio.isdecimal() and int(folio)>0 and (not operacion or operacion.upper() in ('VENTA','BOLETA')):
        return {'estado':'EMITIDA','folio':folio,'motivo':'Confirmación explícita en XML; verificar en portal'}
    if doc_ok and doc_ok.lower()=='false':
        return {'estado':'REVISAR','folio':None,'motivo':'Documento no confirmado; revisar respuesta y portal'}
    return incierta('Falta confirmación inequívoca DTE 39')
