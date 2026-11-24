"""Verificación local sin abrir la caja, sin tocar ventas ni consultar Facturacion.com."""
from pathlib import Path
import ast
import importlib.util
import sys
BASE=Path(__file__).resolve().parent
FILES=('romeral.py','comprobantes_80mm.py','integracion_facturacion.py','validacion_produccion.py','reportes_cierre.py')
print('ROMERAL 2.0 RC1 - comprobación local')
fallos=0
for nombre in FILES:
 try:
  ast.parse((BASE/nombre).read_text(encoding='utf-8'))
  print('[OK]',nombre)
 except (OSError,SyntaxError) as exc:
  fallos+=1
  print('[ERROR]',nombre,type(exc).__name__)
try:
 import tkinter
 print('[OK] Tkinter')
except ImportError:
 fallos+=1
 print('[ERROR] Tkinter no disponible')
print('Datos existentes: NO consultados ni modificados')
print('Emisión tributaria: NO ejecutada')
sys.exit(1 if fallos else 0)
