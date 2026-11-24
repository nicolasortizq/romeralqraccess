"""Analiza tiempos locales de ROMERAL. No usa red ni emite documentos."""
import json
import statistics
from pathlib import Path
from collections import defaultdict

DATA=Path.home()/"Documents"/"ROMERAL_Datos"
archivo=DATA/"romeral_diagnostico_etapas.jsonl"
impresion=DATA/"romeral_tiempos_impresion.jsonl"
if not archivo.exists():
    print("No existe diagnóstico de etapas todavía:", archivo)
else:
    por_etapa=defaultdict(list)
    ventas=set()
    for linea in archivo.read_text(encoding="utf-8").splitlines():
        try:
            r=json.loads(linea)
            if "segundos" in r and isinstance(r["segundos"],(int,float)) and r["segundos"]>=0:
                por_etapa[r.get("etapa","?")].append(r["segundos"])
                ventas.add(r.get("venta"))
            if "total_desde_inicio" in r and isinstance(r["total_desde_inicio"],(int,float)):
                por_etapa["TOTAL_HASTA_COLA_IMPRESION"].append(r["total_desde_inicio"])
        except (ValueError,TypeError,KeyError):
            continue
    print("Ventas con mediciones:",len(ventas))
    for etapa, valores in sorted(por_etapa.items()):
        print(f"{etapa}: n={len(valores)}, promedio={statistics.mean(valores):.2f}s, máximo={max(valores):.2f}s")
if impresion.exists():
    intentos=0
    for linea in impresion.read_text(encoding="utf-8").splitlines():
        try:
            if json.loads(linea).get("estado")=="PDF_NO_DISPONIBLE":intentos+=1
        except ValueError:pass
    print("Consultas PDF con espera:",intentos)
print("Nota: la cola de Windows no confirma el fin de la impresión física.")
