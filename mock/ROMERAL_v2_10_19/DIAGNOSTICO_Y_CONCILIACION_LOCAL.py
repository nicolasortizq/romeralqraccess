"""Auditoría local sin red, sin emitir DTE, sin cambiar folios.
Solo corrige estado del intento si venta/control YA confirman el mismo folio
que una respuesta SOAP guardada y verificada.
"""
from pathlib import Path
import sqlite3, json, hashlib
from RESPUESTAS_SOAP_DTE import analizar_respuesta
DATA=Path.home()/"Documents"/"ROMERAL_Datos"
DB=DATA/"romeral.sqlite3"
def main():
    if not DB.exists():
        print("ERROR: no existe base de datos ROMERAL_Datos")
        return
    with sqlite3.connect(DB,timeout=15) as db:
        pendientes=db.execute("""SELECT i.venta_id,i.estado,v.estado_boleta,v.folio_dte,c.estado,c.folio,v.total
          FROM intentos_soap_dte i JOIN ventas v ON v.id=i.venta_id
          JOIN control_emision c ON c.venta_id=v.id
          WHERE i.estado IN ('ENVIO_INICIADO','INCIERTO') ORDER BY i.id""").fetchall()
        print("Intentos pendientes:",len(pendientes))
        for vid,estado,estado_venta,folio_venta,estado_control,folio_control,total in pendientes:
            print("Venta",vid,"Intento",estado,"Venta",estado_venta,"Control",estado_control,"Folio venta",folio_venta,"Folio control",folio_control,"Total",total)
            evidencia=DATA/f"romeral_soap_respuesta_venta_{vid}.xml"
            if not evidencia.exists():
                print("SIN XML de respuesta local: requiere conciliación manual; NO REINTENTAR")
                continue
            xml=evidencia.read_text(encoding="utf-8")
            try: resultado=analizar_respuesta(xml)
            except Exception as exc:
                print("No se pudo validar XML:",type(exc).__name__);continue
            folio=str(resultado.get('folio') or '')
            if (resultado.get('estado')=='EMITIDA' and estado_venta=='EMITIDA' and estado_control=='EMITIDA'
                and folio and str(folio_venta)==folio and str(folio_control)==folio):
                print("CONCILIACION SEGURA POSIBLE: folio",folio)
                if input("¿Actualizar SOLO el estado de intento a CONFIRMADO? [escribir CONFIRMAR]: ").strip()!='CONFIRMAR':
                    print("Sin cambios");continue
                respaldo=DATA/f"romeral_respaldo_conciliacion_venta_{vid}.sqlite3"
                if respaldo.exists():
                    print("Respaldo ya existe; no se modifica la base");continue
                with sqlite3.connect(respaldo) as copia: db.backup(copia)
                digest=hashlib.sha256(xml.encode('utf-8')).hexdigest()
                with db:
                    db.execute("""UPDATE intentos_soap_dte SET estado='CONFIRMADO',sha256_respuesta=?,folio=?
                      WHERE venta_id=? AND estado=?""",(digest,folio,vid,estado))
                print("Conciliado localmente. NO se emitió ningún DTE.")
            else:
                print("DATOS NO COINCIDENTES O INCOMPLETOS: no se cambia nada; requiere revisión manual")
if __name__=='__main__': main()
