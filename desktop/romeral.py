"""ROMERAL v2.9.1 - pruebas Windows y QR preintegrado."""
import csv
import uuid
import hashlib
import hmac
import secrets
import os
import sqlite3
import shutil
import sys
import json
import subprocess
import threading
import time
from diagnostico_tiempos import registrar_tiempo
from control_folios import leer_estado, registrar_alerta, mensaje_alerta
from monitor_folios import consultar as consultar_saldo_caf, guardar as guardar_consulta_caf, ultimo as ultima_consulta_caf
from comprobantes_80mm import crear_comprobante_html, validar_rut
from impresion_oficial import imprimir_pdf_oficial
from recuperacion_pdf import recuperar
from recuperacion_automatica import recuperar_con_espera
from registro_dte import crear_tabla as crear_control_emision, registrar_venta as registrar_control_emision
from conciliacion_dte import preparar as preparar_conciliacion
import ventas_online
from canje_online import CanjeOnlineController
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

APP_DIR = Path.home() / 'Documents' / 'ROMERAL_Datos'
APP_DIR.mkdir(parents=True, exist_ok=True)
DB = APP_DIR / 'romeral.sqlite3'
PAYMENTS = ('Efectivo', 'Webpay', 'Tarjeta')
MANUALES = ('Cabañas', 'Camping')
def nombre_visible(tipo): return 'Cabañas' if tipo == 'Alojamiento' else tipo

conn = sqlite3.connect(DB)
conn.execute('PRAGMA journal_mode=WAL')
conn.execute('''CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL)''')
conn.execute('''CREATE TABLE IF NOT EXISTS ventas (
 id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT NOT NULL,
 cantidad INTEGER NOT NULL CHECK(cantidad > 0), precio INTEGER NOT NULL,
 total INTEGER NOT NULL, medio TEXT NOT NULL,
 estado_boleta TEXT NOT NULL DEFAULT 'PENDIENTE_INTEGRACION'
)''')
conn.execute('''CREATE TABLE IF NOT EXISTS auditoria_precios_tipos (
 id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT NOT NULL, tipo TEXT NOT NULL,
 precio_anterior INTEGER NOT NULL, precio_nuevo INTEGER NOT NULL
)''')
conn.execute('''CREATE TABLE IF NOT EXISTS auditoria_precios (
 id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT NOT NULL,
 precio_anterior INTEGER NOT NULL, precio_nuevo INTEGER NOT NULL
)''')
# Migración compatible con la base de datos de versiones anteriores.
cols = {r[1] for r in conn.execute('PRAGMA table_info(ventas)')}
if 'tipo' not in cols:
 conn.execute("ALTER TABLE ventas ADD COLUMN tipo TEXT NOT NULL DEFAULT 'Entrada General'")
# Marca el origen de la venta: 'PRESENCIAL' (caja) u 'ONLINE' (canje de entrada
# QR comprada en la web). Las filas históricas quedan como 'PRESENCIAL' por el
# DEFAULT; el cierre de caja (Task 20) filtra por esta columna para mostrar
# los canjes online en su propia línea, sin sumarlos al efectivo esperado.
if 'origen' not in cols:
 conn.execute("ALTER TABLE ventas ADD COLUMN origen TEXT NOT NULL DEFAULT 'PRESENCIAL'")
# Campos de seguimiento tributario: nunca se inventa un folio.
for nombre, definicion in (
 ('referencia_venta', 'TEXT'),
 ('folio_dte', 'TEXT'),
 ('tipo_dte', 'INTEGER'),
 ('fecha_emision', 'TEXT'),
 ('respuesta_emision', 'TEXT'),
 ('ultimo_error_emision', 'TEXT')
):
 if nombre not in cols:
  conn.execute(f'ALTER TABLE ventas ADD COLUMN {nombre} {definicion}')
conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS ux_ventas_referencia ON ventas(referencia_venta)')
crear_control_emision(conn)
preparar_conciliacion(conn)
conn.execute("CREATE TABLE IF NOT EXISTS eventos_dte (id INTEGER PRIMARY KEY AUTOINCREMENT, venta_id INTEGER NOT NULL, fecha TEXT NOT NULL, evento TEXT NOT NULL, detalle TEXT, FOREIGN KEY(venta_id) REFERENCES ventas(id))")
# Los registros históricos siguen sin folio ni emisión.

conn.execute('''CREATE TABLE IF NOT EXISTS cierres_caja (fecha TEXT PRIMARY KEY, creado TEXT NOT NULL, efectivo_esperado INTEGER NOT NULL, efectivo_contado INTEGER NOT NULL, diferencia INTEGER NOT NULL, webpay INTEGER NOT NULL, tarjeta INTEGER NOT NULL, total INTEGER NOT NULL, personas INTEGER NOT NULL, ventas INTEGER NOT NULL, desglose_json TEXT NOT NULL, nota TEXT NOT NULL DEFAULT '')''')
conn.execute('''CREATE TABLE IF NOT EXISTS cierre_operaciones (
 fecha_cierre TEXT NOT NULL, venta_id INTEGER NOT NULL, fecha_venta TEXT NOT NULL,
 tipo TEXT NOT NULL, cantidad INTEGER NOT NULL, medio TEXT NOT NULL,
 total INTEGER NOT NULL, estado_boleta TEXT NOT NULL, folio_dte TEXT,
 PRIMARY KEY(fecha_cierre, venta_id), FOREIGN KEY(fecha_cierre) REFERENCES cierres_caja(fecha))''')
conn.execute("INSERT OR IGNORE INTO config VALUES ('precio','12000')")
conn.execute("INSERT OR IGNORE INTO config VALUES ('precio_temperada','12000')")
conn.execute("INSERT OR IGNORE INTO config VALUES ('rut_empresa','78.180.502-5')")
conn.commit()

def pesos(n): return '$' + f'{int(n):,}'.replace(',', '.')
def config(key):
 row=conn.execute('SELECT value FROM config WHERE key=?',(key,)).fetchone()
 return row[0] if row else None

def hash_clave(clave,salt=None):
 salt=salt or secrets.token_hex(16)
 digest=hashlib.pbkdf2_hmac('sha256',clave.encode('utf-8'),bytes.fromhex(salt),260000)
 return salt+':'+digest.hex()

def validar_clave(clave,guardada):
 try:
  salt,_=guardada.split(':',1)
  return hmac.compare_digest(hash_clave(clave,salt),guardada)
 except (ValueError,TypeError):return False


class Romeral(tk.Tk):
 def __init__(self):
  super().__init__()
  self.title('ROMERAL v2.10.19 | Windows táctil 1024x768')
  self.update_idletasks()
  self.modo_compacto = self.winfo_screenwidth() <= 1100 or self.winfo_screenheight() <= 800
  if self.modo_compacto:
   self.geometry(f'{min(1024,self.winfo_screenwidth())}x{min(728,self.winfo_screenheight()-40)}+0+0')
   self.minsize(900,650)
  else:
   self.geometry('1440x900'); self.minsize(1150,740)
  self.configure(bg='#edf3fa')
  self.precio = int(config('precio'))
  self.precio_temperada = int(config('precio_temperada'))
  self.cantidad = tk.StringVar(value='0')
  self.medio = tk.StringVar(value='')
  self.tipo = tk.StringVar(value='Entrada General')
  self.monto_alojamiento = tk.StringVar(value='0')
  self.monto_visible = tk.StringVar(value='$0')
  self.reloj = tk.StringVar(value='')
  self.campo_activo = 'cantidad'
  self.total = tk.StringVar(value='$0')
  self.resumen = tk.StringVar()
  self.estado = tk.StringVar(value='Emisión DTE 39 disponible con confirmación individual; no hay reintentos automáticos')
  self.emision_en_curso=False
  self.consulta_folios_en_curso=False
  self.estado_folios=tk.StringVar(value='Folios DTE39: sin consultar')
  self.payment_widgets = {}
  self.intentos_clave = 0
  # Identifican esta terminal ante el backend al canjear una entrada online
  # (docs/api/openapi.yaml: redeem toma terminal + redeemed_by por separado).
  self.terminal_nombre = config('acceso_terminal_nombre') or 'acceso-1'
  self.operador_actual = config('acceso_terminal_operador') or os.environ.get('USERNAME') or os.environ.get('USER') or 'operador'
  self._aviso_cierre_fecha = None
  self.cantidad.trace_add('write', lambda *_: self.actualizar_total())
  self.monto_alojamiento.trace_add('write', lambda *_: self.actualizar_total())
  self.bind('<Return>', self.accion_enter)
  self.bind('<KP_Enter>', self.accion_enter)
  self.bind('<Escape>', lambda e: self.limpiar())
  self.crear_ui(); self.actualizar_total(); self.actualizar_resumen(); self.actualizar_reloj(); self.after(3000,self.actualizar_folios_background)

 def boton(self, parent, texto, accion, bg='#ffffff', fg='#10294c', size=17, **kw):
  return tk.Button(parent, text=texto, command=accion, bg=bg, fg=fg, font=('Arial',size,'bold'),
   relief='flat', activebackground='#c7d9ef', cursor='hand2', padx=10, pady=12, **kw)

 def boton_color(self,parent,texto,accion,color,size=12,alto=54,fg='white'):
  """Botón táctil redondeado: Canvas evita las limitaciones de tk.Button en macOS."""
  fondo=parent.cget('bg')
  canvas=tk.Canvas(parent,bg=fondo,highlightthickness=0,bd=0,height=alto,cursor='hand2',takefocus=1)
  canvas._romeral_texto=texto
  canvas._romeral_color=color
  canvas._romeral_fg=fg
  def dibujar(event=None):
   w=max(canvas.winfo_width(),80);h=max(canvas.winfo_height(),30)
   r=min(16,h//3,w//5)
   canvas.delete('all')
   # Arcos y rectángulos: radios reales sin bordes cuadrados.
   canvas.create_rectangle(r,1,w-r,h-1,fill=canvas._romeral_color,outline='')
   canvas.create_rectangle(1,r,w-1,h-r,fill=canvas._romeral_color,outline='')
   for x0,y0,x1,y1,start in [(1,1,2*r+1,2*r+1,90),(w-2*r-1,1,w-1,2*r+1,0),(w-2*r-1,h-2*r-1,w-1,h-1,270),(1,h-2*r-1,2*r+1,h-1,180)]:
    canvas.create_arc(x0,y0,x1,y1,start=start,extent=90,style='pieslice',fill=canvas._romeral_color,outline='')
   canvas.create_text(w/2,h/2,text=canvas._romeral_texto,fill=canvas._romeral_fg,font=('Arial',size,'bold'),width=max(50,w-22),justify='center')
  canvas.bind('<Configure>',dibujar)
  canvas.bind('<Button-1>',lambda e:accion())
  canvas.bind('<Return>',lambda e:accion())
  canvas.bind('<space>',lambda e:accion())
  canvas.redibujar=dibujar
  return canvas

 def menu_administracion(self):
  menu=tk.Menu(self,tearoff=0)
  for nombre,accion in [('Control DTE',self.panel_control_dte),('Emitir DTE',self.panel_emitir_dte),('Reimprimir boleta por folio',self.reimprimir_dte),('Imprimir PDF oficial',self.abrir_pdf_oficial),('Facturación',self.panel_facturacion),('Credenciales PLANO (pruebas)',self.panel_credenciales_plano),('Exportar CSV',self.exportar),('Historial cierres',self.historial_cierres),('Anular pruebas',self.anular_pruebas)]:
   menu.add_command(label=nombre,command=accion)
  menu.tk_popup(self.winfo_pointerx(),self.winfo_pointery())
  menu.grab_release()

 def panel_credenciales_plano(self):
  """Solo configuración local. No conecta, consulta ni emite documentos."""
  if not self.autorizar_supervisor():return
  from pathlib import Path
  import json
  try:
   import keyring
  except ImportError:
   messagebox.showerror('Dependencia faltante','Instala las dependencias con INSTALAR_WINDOWS.bat. Se requiere keyring.',parent=self)
   return
  carpeta=Path.home()/'Documents'/'ROMERAL_Datos'
  archivo=carpeta/'facturacion_plano.json'
  servicio='ROMERAL_FACTURACION_PLANO'
  try:
   anterior=json.loads(archivo.read_text(encoding='utf-8')) if archivo.exists() else {}
  except (OSError,ValueError):
   messagebox.showerror('Configuración','No se puede leer la configuración existente; no se modificó.',parent=self)
   return
  win=tk.Toplevel(self);win.title('ROMERAL | Credenciales de PRUEBA · PLANO')
  win.geometry('670x510');win.configure(bg='#f1f6fc');win.transient(self);win.grab_set()
  tk.Label(win,text='FACTURACIÓN · AMBIENTE PLANO',font=('Arial',17,'bold'),bg='#f1f6fc',fg='#123455').pack(pady=(16,6))
  tk.Label(win,text='Consulta CAF opcional y solo lectura. NO emite documentos.',bg='#f1f6fc',fg='#854800').pack(pady=(0,15))
  variables={}
  for nombre,campo in [('RUT Empresa','rut'),('Usuario','usuario'),('Puerto (si aplica)','puerto'),('Clave de prueba','clave')]:
   fila=tk.Frame(win,bg='#f1f6fc');fila.pack(fill='x',padx=35,pady=7)
   tk.Label(fila,text=nombre,width=22,anchor='w',bg='#f1f6fc').pack(side='left')
   var=tk.StringVar(value='' if campo=='clave' else str(anterior.get(campo,'0' if campo=='puerto' else '')))
   variables[campo]=var
   tk.Entry(fila,textvariable=var,width=35,show='*' if campo=='clave' else '').pack(side='left',fill='x',expand=True)
  tk.Label(win,text='Deja la clave en blanco para conservar la ya guardada. Nunca se muestra.',bg='#f1f6fc',fg='#41536b').pack(pady=7)
  def guardar():
   rut=variables['rut'].get().strip();usuario=variables['usuario'].get().strip()
   puerto=variables['puerto'].get().strip() or '0';clave=variables['clave'].get()
   if not rut or not usuario or not puerto.isdigit():
    messagebox.showerror('Datos incompletos','Ingresa RUT, usuario y puerto numérico.',parent=win);return
   try:
    if clave:keyring.set_password(servicio,'clave',clave)
    elif not keyring.get_password(servicio,'clave'):
     messagebox.showerror('Clave faltante','Ingresa la clave de PRUEBAS para guardar.',parent=win);return
    carpeta.mkdir(parents=True,exist_ok=True)
    import os
    tmp=archivo.with_suffix('.json.tmp')
    tmp.write_text(json.dumps({'ambiente':'plano','rut':rut,'usuario':usuario,'puerto':puerto},indent=2,ensure_ascii=False),encoding='utf-8')
    os.replace(tmp,archivo)
   except Exception as exc:
    messagebox.showerror('No se guardó',f'Error del llavero o del archivo: {type(exc).__name__}',parent=win);return
   variables['clave'].set('')
   messagebox.showinfo('Configuración guardada','Credenciales de PLANO guardadas localmente. Producción no fue modificada. No se realizó conexión ni emisión.',parent=win)
   win.destroy()
  tk.Button(win,text='GUARDAR CREDENCIALES DE PRUEBA',command=guardar,bg='#176B87',fg='white',font=('Arial',12,'bold'),height=2).pack(fill='x',padx=35,pady=(12,6))
  def probar_conexion():
   if not messagebox.askyesno('Consultar CAF de PRUEBAS',
     'Se enviarán las credenciales guardadas de PLANO a Facturacion.com por HTTPS.\n\nSolo se ejecutará ConsultarCAF para DTE 39. NO se emitirá ninguna boleta.\n\n¿Continuar?',parent=win):return
   estado.set('Consultando CAF de pruebas... (solo lectura)')
   boton_consulta.configure(state='disabled')
   import threading
   def tarea():
    try:
     from consulta_plano import consultar_caf_plano
     resultado=consultar_caf_plano()
    except Exception as exc:
     resultado='No se completó la consulta ('+type(exc).__name__+').\nNo se emitió ninguna boleta.'
    def mostrar():
     if not win.winfo_exists():return
     estado.set(resultado);boton_consulta.configure(state='normal')
    try:self.after(0,mostrar)
    except RuntimeError:pass
   threading.Thread(target=tarea,daemon=True).start()
  estado=tk.StringVar(value='La consulta requiere conexión y autorización expresa. No emite boletas.')
  boton_consulta=tk.Button(win,text='CONSULTAR CAF PLANO · SOLO LECTURA',command=probar_conexion,bg='#276f55',fg='white',font=('Arial',11,'bold'),height=2)
  boton_consulta.pack(fill='x',padx=35,pady=(6,3))
  tk.Label(win,textvariable=estado,bg='#f1f6fc',fg='#17385c',wraplength=610,justify='left').pack(padx=35,pady=3)
  tk.Button(win,text='CANCELAR',command=win.destroy).pack(pady=5)

 def solicitar_folios(self):
  # La consulta CAF es de solo lectura. Nunca simular una solicitud electrónica.
  if not self.autorizar_supervisor():return
  messagebox.showinfo('Solicitar folios DTE 39',
   'La solicitud de nuevos folios debe gestionarse mediante el procedimiento autorizado de Facturacion.com y/o SII.\n\n'
   'ROMERAL todavía no dispone de un método API verificado para solicitar o cargar CAF automáticamente.\n\n'
   'Contacta a Facturacion.com para solicitar la reposición de DTE 39. Luego usa «Consultar ahora» para verificar el nuevo rango.\n\n'
   'Esta opción NO envía una solicitud ni modifica folios.',parent=self)

 def pedir_clave(self,titulo):
  return simpledialog.askstring(titulo,'Clave de supervisor:',show='*',parent=self)

 def autorizar_supervisor(self):
  guardada=config('clave_supervisor')
  if not guardada:
   messagebox.showinfo('Configurar supervisor','Primera configuración: crea una clave de supervisor de al menos 6 caracteres. No utilices claves de facturación.')
   clave=self.pedir_clave('Crear clave de supervisor')
   if clave is None:return False
   if len(clave)<6:
    messagebox.showwarning('Clave demasiado corta','Usa al menos 6 caracteres.');return False
   confirmacion=self.pedir_clave('Confirmar clave de supervisor')
   if clave!=confirmacion:
    messagebox.showerror('No coincide','Las claves no coinciden.');return False
   with conn:conn.execute('INSERT OR REPLACE INTO config(key,value) VALUES (?,?)',('clave_supervisor',hash_clave(clave)))
   messagebox.showinfo('Clave creada','La clave de supervisor quedó configurada.')
   return True
  if self.intentos_clave>=5:
   messagebox.showerror('Acceso bloqueado','Demasiados intentos incorrectos. Cierra y vuelve a abrir el programa para intentarlo de nuevo.');return False
  clave=self.pedir_clave('Autorización de supervisor')
  if clave is None:return False
  if not validar_clave(clave,guardada):
   self.intentos_clave+=1
   messagebox.showerror('Acceso denegado',f'Clave incorrecta. Intentos restantes: {5-self.intentos_clave}')
   return False
  self.intentos_clave=0
  return True

 def crear_ui(self):
  if self.modo_compacto:
   return self.crear_ui_compacta()
  NAVY='#102F52';INK='#17385C';BG='#EDF3F8';WHITE='#FFFFFF'
  header=tk.Frame(self,bg=NAVY);header.pack(fill='x')
  titulo=tk.Frame(header,bg=NAVY);titulo.pack(fill='x',padx=22,pady=(12,7))
  tk.Label(titulo,text='ROMERAL',bg=NAVY,fg=WHITE,font=('Arial',26,'bold')).pack(side='left')
  tk.Label(titulo,text='CENTRO TURÍSTICO · v2.9.0',bg=NAVY,fg='#BED1E4',font=('Arial',11,'bold')).pack(side='left',padx=14)
  tk.Label(titulo,textvariable=self.reloj,bg=NAVY,fg=WHITE,font=('Arial',12,'bold')).pack(side='right')
  barra=tk.Frame(header,bg=NAVY);barra.pack(fill='x',padx=20,pady=(0,12))
  folios=tk.Frame(barra,bg='#1B4264',padx=16,pady=10)
  folios.pack(side='left',fill='x',expand=True,padx=(0,12))
  tk.Label(folios,text='FOLIOS ELECTRÓNICOS · DTE 39',bg='#1B4264',fg='#BFD8E9',font=('Arial',9,'bold'),anchor='w').pack(fill='x')
  datos_folios=tk.Frame(folios,bg='#1B4264');datos_folios.pack(fill='x',pady=(4,2))
  columna_sig=tk.Frame(datos_folios,bg='#244D70',padx=12,pady=5);columna_sig.pack(side='left',fill='x',expand=True,padx=(0,5))
  tk.Label(columna_sig,text='PRÓXIMO FOLIO INFORMADO',bg='#244D70',fg='#D4E5F2',font=('Arial',8,'bold'),anchor='w').pack(fill='x')
  self.folio_siguiente_visible=tk.StringVar(value='—')
  tk.Label(columna_sig,textvariable=self.folio_siguiente_visible,bg='#244D70',fg='white',font=('Arial',18,'bold'),anchor='w').pack(fill='x')
  columna_saldo=tk.Frame(datos_folios,bg='#244D70',padx=12,pady=5);columna_saldo.pack(side='left',fill='x',expand=True,padx=(5,0))
  tk.Label(columna_saldo,text='RESTANTES ESTIMADOS',bg='#244D70',fg='#D4E5F2',font=('Arial',8,'bold'),anchor='w').pack(fill='x')
  self.folios_restantes_visible=tk.StringVar(value='—')
  tk.Label(columna_saldo,textvariable=self.folios_restantes_visible,bg='#244D70',fg='#A7E2BA',font=('Arial',18,'bold'),anchor='w').pack(fill='x')
  tk.Label(folios,textvariable=self.estado_folios,bg='#1B4264',fg='#D4E5F2',font=('Arial',9,'bold'),anchor='w',wraplength=520).pack(fill='x',pady=(3,0))
  for texto,accion,color in [('Folios DTE',self.panel_folios,'#986019'),('Historial',self.historial,'#286381'),('Cierre caja',self.panel_cierre,'#286381'),('Ventas Online QR',self.panel_qr_online,'#19705B'),('Más opciones',self.menu_administracion,'#41536B')]:
   boton=self.boton_color(barra,texto,accion,color,size=10,alto=54)
   boton.pack(side='left',padx=4)
   boton.configure(width=132 if texto=='Ventas Online QR' else 110)
  body=tk.Frame(self,bg=BG);body.pack(fill='both',expand=True,padx=14,pady=14)
  for col,weight in enumerate((46,29,25)):body.grid_columnconfigure(col,weight=weight,uniform='panel')
  body.grid_rowconfigure(0,weight=1)
  left=tk.Frame(body,bg=WHITE,padx=17,pady=16);left.grid(row=0,column=0,sticky='nsew',padx=5)
  mid=tk.Frame(body,bg=WHITE,padx=17,pady=16);mid.grid(row=0,column=1,sticky='nsew',padx=5)
  right=tk.Frame(body,bg=WHITE,padx=15,pady=16);right.grid(row=0,column=2,sticky='nsew',padx=5)
  tk.Label(left,text='Nueva venta',bg=WHITE,fg=INK,font=('Arial',20,'bold')).pack(anchor='w')
  tk.Label(left,text='Selecciona una modalidad',bg=WHITE,fg='#70839A',font=('Arial',10)).pack(anchor='w',pady=(0,8))
  modos=tk.Frame(left,bg=WHITE);modos.pack(fill='x',pady=(2,12))
  self.botones_tipo={}
  self.colores_tipo={'Entrada General':'#23815B','Cabañas':'#C17B31','Piscina Temperada':'#2873AC','Camping':'#7555A0'}
  for fila in (('Entrada General','Piscina Temperada'),('Cabañas','Camping')):
   linea=tk.Frame(modos,bg=WHITE);linea.pack(fill='x',pady=3)
   for nombre in fila:
    b=self.boton_color(linea,nombre,lambda t=nombre:self.cambiar_tipo(t),self.colores_tipo[nombre],size=11,alto=64)
    b.pack(side='left',fill='x',expand=True,padx=3)
    self.botones_tipo[nombre]=b
  self.tipo_label=tk.Label(left,text='Entrada General',bg=WHITE,fg=INK,font=('Arial',16,'bold'))
  self.tipo_label.pack(anchor='w')
  pricebar=tk.Frame(left,bg=WHITE);pricebar.pack(fill='x',pady=(5,10))
  self.price_label=tk.Label(pricebar,text=pesos(self.precio),bg=WHITE,fg='#0954ac',font=('Arial',22,'bold'));self.price_label.pack(side='left')
  self.boton_cambiar=self.boton_color(pricebar,'Cambiar',self.cambiar_precio,'#526A85',size=10,alto=40)
  self.boton_cambiar.pack(side='right');self.boton_cambiar.configure(width=105)
  tk.Label(left,text='Cantidad de personas',bg=WHITE,fg=INK,font=('Arial',13,'bold')).pack(anchor='w',pady=(5,4))
  self.campo_cantidad=tk.Entry(left,textvariable=self.cantidad,justify='center',font=('Arial',29,'bold'),bd=1,relief='solid',width=8,bg='#FFF3C9',fg='#B42332',insertbackground='#B42332',highlightthickness=2,highlightbackground='#E7D9A5',highlightcolor='#E4A31B')
  self.campo_cantidad.pack(fill='x',pady=(0,9),ipady=6);self.campo_cantidad.focus_set()
  self.ayuda_alojamiento=tk.Label(left,text='Valor por persona de Cabañas (CLP)',bg=WHITE,fg=INK,font=('Arial',11,'bold'))
  self.campo_alojamiento=tk.Entry(left,textvariable=self.monto_visible,justify='center',font=('Arial',22,'bold'),bd=1,relief='solid',bg='#FFF3C9',fg='#B42332',insertbackground='#B42332',highlightthickness=2,highlightbackground='#E7D9A5',highlightcolor='#E4A31B')
  self.campo_alojamiento.bind('<KeyRelease>',self.editar_monto_visible)
  self.campo_alojamiento.bind('<<Paste>>',lambda e:self.after(10,self.editar_monto_visible))
  self.campo_alojamiento.bind('<FocusOut>',self.editar_monto_visible)
  self.campo_cantidad.bind('<FocusIn>',lambda e:self.definir_campo('cantidad'))
  self.campo_alojamiento.bind('<FocusIn>',lambda e:self.definir_campo('monto'))
  pad=tk.Frame(left,bg=WHITE);pad.pack(fill='both',expand=True)
  for row,nums in enumerate((('7','8','9'),('4','5','6'),('1','2','3'),('C','0','⌫'))):
   pad.grid_rowconfigure(row,weight=1)
   for col,key in enumerate(nums):
    pad.grid_columnconfigure(col,weight=1)
    color='#F7DDE0' if key=='C' else '#E8F0F9'
    fg='#A52835' if key=='C' else INK
    b=self.boton_color(pad,key,lambda k=key:self.tecla(k),color,size=19,alto=54,fg=fg)
    b.grid(row=row,column=col,sticky='nsew',padx=4,pady=4)
  tk.Label(mid,text='Total a pagar',bg=WHITE,fg=INK,font=('Arial',19,'bold')).pack(anchor='w')
  tk.Label(mid,textvariable=self.total,bg='#E8F2FF',fg='#06499A',font=('Arial',31,'bold'),height=2).pack(fill='x',pady=(12,20))
  tk.Label(mid,text='Medio de pago',bg=WHITE,fg=INK,font=('Arial',16,'bold')).pack(anchor='w',pady=(0,10))
  colors={'Efectivo':('#23815B','#E8F5EE'),'Webpay':('#2873AC','#EAF2FF'),'Tarjeta':('#7555A0','#F2ECFA')}
  self.payment_colors=colors
  for m in PAYMENTS:
   frame=tk.Frame(mid,bg=WHITE,height=60)
   frame.pack(fill='x',pady=4);frame.pack_propagate(False)
   canvas=self.boton_color(frame,m.upper(),lambda method=m:self.seleccionar_pago(method),colors[m][1],size=14,alto=58,fg=colors[m][0])
   canvas.pack(fill='both',expand=True)
   self.payment_widgets[m]=(frame,canvas)
  self.pago_confirmado=tk.StringVar(value='SELECCIONA UN MEDIO DE PAGO')
  tk.Label(mid,textvariable=self.pago_confirmado,bg=WHITE,fg=INK,font=('Arial',10,'bold'),wraplength=250).pack(fill='x',pady=8)
  self.actualizar_pagos()
  enter_frame=tk.Frame(mid,bg=WHITE)
  enter_frame.pack(fill='x',side='bottom',pady=(10,3))
  enter_label=self.boton_color(enter_frame,'REGISTRAR VENTA',self.registrar,'#D9781F',size=15,alto=76)
  enter_label.pack(fill='x')
  self.enter_frame=enter_frame;self.enter_label=enter_label
  tk.Label(right,text='Resumen del día',bg=WHITE,fg=INK,font=('Arial',18,'bold')).pack(anchor='w')
  tk.Label(right,text=datetime.now().strftime('%d/%m/%Y'),bg=WHITE,fg='#66778B',font=('Arial',11)).pack(anchor='w',pady=(2,10))
  self.resumen_label=tk.Label(right,textvariable=self.resumen,bg='#F1F6FC',fg=INK,justify='left',anchor='nw',font=('Arial',12),padx=12,pady=14)
  self.resumen_label.pack(fill='both',expand=True)
  self.resumen_label.bind('<Configure>',lambda e:self.resumen_label.configure(wraplength=max(140,e.width-30)))
  self.boton_color(right,'Actualizar resumen',self.actualizar_resumen,'#176B87',size=11,alto=54).pack(fill='x',pady=(10,0))
  self.actualizar_modo()
  tk.Label(self,textvariable=self.estado,bg='#FFF0CF',fg='#744300',font=('Arial',10,'bold'),anchor='w',padx=16,pady=8).pack(fill='x')

 def crear_ui_compacta(self):
  """Pantalla principal compacta para equipos POS 1024x768 (sin desplazamiento)."""
  NAVY='#102F52'; INK='#17385C'; WHITE='#FFFFFF'; BG='#EDF3F8'
  head=tk.Frame(self,bg=NAVY);head.pack(fill='x')
  top=tk.Frame(head,bg=NAVY);top.pack(fill='x',padx=12,pady=(5,3))
  tk.Label(top,text='ROMERAL',bg=NAVY,fg=WHITE,font=('Arial',19,'bold')).pack(side='left')
  tk.Label(top,text='v2.10.19 · WINDOWS TÁCTIL',bg=NAVY,fg='#BED1E4',font=('Arial',9,'bold')).pack(side='left',padx=12)
  tk.Label(top,textvariable=self.reloj,bg=NAVY,fg=WHITE,font=('Arial',10,'bold')).pack(side='right')
  nav=tk.Frame(head,bg=NAVY);nav.pack(fill='x',padx=10,pady=(0,6))
  fol=tk.Frame(nav,bg='#1B4264',padx=8,pady=3);fol.pack(side='left',fill='both',expand=True,padx=(0,5))
  tk.Label(fol,text='DTE 39 · Próximo folio / Restantes',bg='#1B4264',fg='#BFD8E9',font=('Arial',8,'bold')).pack(anchor='w')
  self.folio_siguiente_visible=tk.StringVar(value='—')
  self.folios_restantes_visible=tk.StringVar(value='—')
  values=tk.Frame(fol,bg='#1B4264');values.pack(fill='x')
  tk.Label(values,textvariable=self.folio_siguiente_visible,bg='#1B4264',fg='white',font=('Arial',13,'bold')).pack(side='left')
  tk.Label(values,text=' / ',bg='#1B4264',fg='white',font=('Arial',12)).pack(side='left')
  tk.Label(values,textvariable=self.folios_restantes_visible,bg='#1B4264',fg='#A7E2BA',font=('Arial',13,'bold')).pack(side='left')
  tk.Label(fol,textvariable=self.estado_folios,bg='#1B4264',fg='#D4E5F2',font=('Arial',8),anchor='w').pack(fill='x')
  actions=[('Folios',self.panel_folios,'#986019'),('Historial',self.historial,'#286381'),('Cierre caja',self.panel_cierre,'#286381'),('Ventas QR',self.panel_qr_online,'#19705B'),('Opciones',self.menu_administracion,'#41536B')]
  for name,callback,color in actions:
   frame=tk.Frame(nav,bg=NAVY,width=94,height=53);frame.pack(side='left',padx=2);frame.pack_propagate(False)
   self.boton_color(frame,name,callback,color,size=9,alto=48).pack(fill='both',expand=True)
  body=tk.Frame(self,bg=BG);body.pack(fill='both',expand=True,padx=7,pady=5)
  body.grid_columnconfigure(0,weight=55,uniform='main');body.grid_columnconfigure(1,weight=45,uniform='main')
  body.grid_rowconfigure(0,weight=1)
  left=tk.Frame(body,bg=WHITE,padx=10,pady=7);left.grid(row=0,column=0,sticky='nsew',padx=(0,4))
  mid=tk.Frame(body,bg=WHITE,padx=10,pady=7);mid.grid(row=0,column=1,sticky='nsew',padx=(4,0))
  tk.Label(left,text='Nueva venta',bg=WHITE,fg=INK,font=('Arial',16,'bold')).pack(anchor='w')
  modos=tk.Frame(left,bg=WHITE);modos.pack(fill='x',pady=(4,5))
  modos.grid_columnconfigure(0,weight=1,uniform='modos');modos.grid_columnconfigure(1,weight=1,uniform='modos')
  self.botones_tipo={}
  self.colores_tipo={'Entrada General':'#23815B','Cabañas':'#C17B31','Piscina Temperada':'#2873AC','Camping':'#7555A0'}
  for r,fila in enumerate((('Entrada General','Piscina Temperada'),('Cabañas','Camping'))):
   for c,nombre in enumerate(fila):
    b=self.boton_color(modos,nombre,lambda t=nombre:self.cambiar_tipo(t),self.colores_tipo[nombre],size=10,alto=43)
    b.grid(row=r,column=c,sticky='ew',padx=3,pady=2)
    self.botones_tipo[nombre]=b
  details=tk.Frame(left,bg=WHITE);details.pack(fill='x')
  self.tipo_label=tk.Label(details,text='Entrada General',bg=WHITE,fg=INK,font=('Arial',13,'bold'));self.tipo_label.pack(side='left')
  pricebar=tk.Frame(left,bg=WHITE);pricebar.pack(fill='x',pady=(1,2))
  self.price_label=tk.Label(pricebar,text=pesos(self.precio),bg=WHITE,fg='#0954ac',font=('Arial',18,'bold'));self.price_label.pack(side='left')
  self.boton_cambiar=self.boton_color(pricebar,'Cambiar',self.cambiar_precio,'#526A85',size=9,alto=30)
  self.boton_cambiar.pack(side='right');self.boton_cambiar.configure(width=85)
  tk.Label(left,text='Cantidad de personas',bg=WHITE,fg=INK,font=('Arial',10,'bold')).pack(anchor='w')
  self.campo_cantidad=tk.Entry(left,textvariable=self.cantidad,justify='center',font=('Arial',22,'bold'),bd=1,relief='solid',bg='#FFF3C9',fg='#B42332',highlightthickness=1,highlightbackground='#E7D9A5')
  self.campo_cantidad.pack(fill='x',pady=(2,4),ipady=2);self.campo_cantidad.focus_set()
  self.ayuda_alojamiento=tk.Label(left,text='Valor por persona de Cabañas (CLP)',bg=WHITE,fg=INK,font=('Arial',9,'bold'))
  self.campo_alojamiento=tk.Entry(left,textvariable=self.monto_visible,justify='center',font=('Arial',17,'bold'),bd=1,relief='solid',bg='#FFF3C9',fg='#B42332',highlightthickness=1,highlightbackground='#E7D9A5')
  self.campo_alojamiento.bind('<KeyRelease>',self.editar_monto_visible)
  self.campo_alojamiento.bind('<<Paste>>',lambda e:self.after(10,self.editar_monto_visible))
  self.campo_alojamiento.bind('<FocusOut>',self.editar_monto_visible)
  self.campo_cantidad.bind('<FocusIn>',lambda e:self.definir_campo('cantidad'))
  self.campo_alojamiento.bind('<FocusIn>',lambda e:self.definir_campo('monto'))
  pad=tk.Frame(left,bg=WHITE);pad.pack(fill='both',expand=True)
  for r,nums in enumerate((('7','8','9'),('4','5','6'),('1','2','3'),('C','0','⌫'))):
   pad.grid_rowconfigure(r,weight=1)
   for c,key in enumerate(nums):
    pad.grid_columnconfigure(c,weight=1)
    b=self.boton_color(pad,key,lambda k=key:self.tecla(k),'#F7DDE0' if key=='C' else '#E8F0F9',size=16,alto=39,fg='#A52835' if key=='C' else INK)
    b.grid(row=r,column=c,sticky='nsew',padx=3,pady=2)
  tk.Label(mid,text='Total a pagar',bg=WHITE,fg=INK,font=('Arial',16,'bold')).pack(anchor='w')
  tk.Label(mid,textvariable=self.total,bg='#E8F2FF',fg='#06499A',font=('Arial',27,'bold'),height=2).pack(fill='x',pady=(5,7))
  tk.Label(mid,text='Medio de pago',bg=WHITE,fg=INK,font=('Arial',13,'bold')).pack(anchor='w',pady=(0,3))
  colors={'Efectivo':('#23815B','#E8F5EE'),'Webpay':('#2873AC','#EAF2FF'),'Tarjeta':('#7555A0','#F2ECFA')}
  self.payment_colors=colors
  for m in PAYMENTS:
   frame=tk.Frame(mid,bg=WHITE,height=44);frame.pack(fill='x',pady=2);frame.pack_propagate(False)
   canvas=self.boton_color(frame,m.upper(),lambda method=m:self.seleccionar_pago(method),colors[m][1],size=12,alto=42,fg=colors[m][0])
   canvas.pack(fill='both',expand=True);self.payment_widgets[m]=(frame,canvas)
  self.pago_confirmado=tk.StringVar(value='SELECCIONA UN MEDIO DE PAGO')
  tk.Label(mid,textvariable=self.pago_confirmado,bg=WHITE,fg=INK,font=('Arial',9,'bold')).pack(fill='x',pady=3)
  self.enter_frame=tk.Frame(mid,bg=WHITE)
  self.enter_frame.pack(side='bottom',fill='x',pady=(4,1))
  self.enter_label=self.boton_color(self.enter_frame,'REGISTRAR VENTA',self.registrar,'#D9781F',size=14,alto=60)
  self.enter_label.pack(fill='x')
  summary=tk.Frame(mid,bg='#F1F6FC',padx=8,pady=4);summary.pack(fill='both',expand=True,pady=(4,2))
  tk.Label(summary,text='Resumen del día',bg='#F1F6FC',fg=INK,font=('Arial',11,'bold')).pack(anchor='w')
  self.resumen_label=tk.Label(summary,textvariable=self.resumen,bg='#F1F6FC',fg=INK,justify='left',anchor='nw',font=('Arial',9))
  self.resumen_label.pack(fill='both',expand=True)
  self.resumen_label.bind('<Configure>',lambda e:self.resumen_label.configure(wraplength=max(150,e.width-12)))
  self.boton_color(mid,'Actualizar resumen',self.actualizar_resumen,'#176B87',size=9,alto=32).pack(fill='x',pady=(1,0))
  self.actualizar_modo();self.actualizar_pagos()
  tk.Label(self,textvariable=self.estado,bg='#FFF0CF',fg='#744300',font=('Arial',9,'bold'),anchor='w',padx=10,pady=4).pack(fill='x')

 def actualizar_reloj(self):
  if not self.winfo_exists():return
  self.reloj.set(datetime.now().strftime('%d/%m/%Y  ·  %H:%M:%S'))
  if datetime.now().second % 10 == 0:
   self.comprobar_jornada(avisar=False)
  self.after(1000,self.actualizar_reloj)

 def editar_monto_visible(self,event=None):
  texto=self.monto_visible.get()
  digitos=''.join(c for c in texto if c.isdecimal())[:9]
  numero=int(digitos or '0')
  if self.monto_alojamiento.get()!=str(numero):self.monto_alojamiento.set(str(numero))
  formateado=pesos(numero)
  if texto!=formateado:self.monto_visible.set(formateado)
  if event is not None and event.type==tk.EventType.KeyRelease:
   self.campo_alojamiento.icursor('end')

 def reiniciar_pago(self):
  self.medio.set('')
  self.actualizar_pagos()

 def actualizar_folios_background(self):
  """Consulta en segundo plano cada 15 minutos; nunca bloquea la caja."""
  if self.consulta_folios_en_curso:return
  self.consulta_folios_en_curso=True
  def trabajo():
   try: dato=guardar_consulta_caf(consultar_saldo_caf())
   except Exception as exc: dato=guardar_consulta_caf({'estado':'NO_DISPONIBLE','error':str(exc)[:160]})
   def finalizar():
    self.consulta_folios_en_curso=False
    if dato['estado']=='ESTIMADO_CAF':
     n=dato['cantidad']
     rangos=[r for r in dato.get('rangos',[]) if isinstance(r,dict) and isinstance(r.get('siguiente'),int) and isinstance(r.get('hasta'),int) and r['siguiente']<=r['hasta']]
     siguiente=min((r['siguiente'] for r in rangos),default=None)
     self.folio_siguiente_visible.set(f'{siguiente:,}'.replace(',','.') if siguiente is not None else '—')
     self.folios_restantes_visible.set(f'{n:,}'.replace(',','.'))
     aviso='CRÍTICO · Solicitar folios' if n<=100 else ('STOCK BAJO · Solicitar folios' if n<=500 else 'Normal')
     self.estado_folios.set(f"Sincronizado {dato['fecha'][11:19]} · {aviso} · Saldo CAF estimado")
    else:
     self.folio_siguiente_visible.set('—')
     self.folios_restantes_visible.set('—')
     self.estado_folios.set('Sin sincronización · Revisar panel de folios')
    self.after(900000,self.actualizar_folios_background)
   try:self.after(0,finalizar)
   except RuntimeError:pass
  threading.Thread(target=trabajo,daemon=True).start()

 def panel_folios(self):
  if not self.autorizar_supervisor():return
  win=tk.Toplevel(self);win.title('ROMERAL · Folios DTE 39');win.geometry('740x540');win.configure(bg='#f2f6fb')
  area=tk.Text(win,font=('Arial',12),wrap='word',bg='white',fg='#183553',padx=18,pady=18)
  area.pack(fill='both',expand=True,padx=15,pady=15)
  def mostrar():
   d=ultima_consulta_caf()
   if not d: txt='Sin consultas realizadas todavía.'
   elif d['estado']=='ESTIMADO_CAF':
    n=d['cantidad']
    txt=(f"CONSULTA CAF · DTE 39\nFecha: {d['fecha']}\n\nFOLIOS RESTANTES ESTIMADOS: {n:,}\n\n".replace(',','.')+
      ('ALERTA CRÍTICA: solicitar folios urgentemente.\n' if n<=100 else 'ALERTA PREVENTIVA: solicitar folios.\n' if n<=500 else 'Sin alerta por umbral.\n')+
      '\n'+d['advertencia']+'\n\nRangos informados:\n'+
      '\n'.join(f"{r['desde']}–{r['hasta']} · siguiente {r['siguiente']} · estimado {r['estimado']}" for r in d['rangos']))
   else:txt=f"CONSULTA NO DISPONIBLE\nFecha: {d['fecha']}\n{d.get('error','Error desconocido')}\n\nNo interpretar como cero folios."
   txt+='\n\nHISTORIAL: ~/Documents/ROMERAL_Datos/romeral_consultas_folios.jsonl\nDIAGNÓSTICO: ~/Documents/ROMERAL_Datos/romeral_diagnostico_caf.jsonl'
   area.config(state='normal');area.delete('1.0','end');area.insert('1.0',txt);area.config(state='disabled')
  def consultar_ahora():
   if self.consulta_folios_en_curso:
    win.after(1500,mostrar);return
   self.actualizar_folios_background()
   win.after(2500,mostrar)
   win.after(6000,mostrar)
   win.after(12000,mostrar)
  self.boton_color(win,'CONSULTAR AHORA · SOLO LECTURA',consultar_ahora,'#176B87',size=13).pack(fill='x',padx=18,pady=(0,5))
  self.boton_color(win,'SOLICITAR NUEVOS FOLIOS DTE 39',self.solicitar_folios,'#986019',size=12).pack(fill='x',padx=18,pady=(0,12))
  mostrar()

 def cambiar_tipo(self,tipo):
  self.tipo.set(tipo)
  self.cantidad.set('0')
  self.monto_alojamiento.set('0')
  self.monto_visible.set('$0')
  self.campo_activo='cantidad'
  self.actualizar_modo()
  self.actualizar_total()

 def definir_campo(self,campo):
  self.campo_activo=campo

 def accion_enter(self,event=None):
  if self.tipo.get() in MANUALES and self.focus_get()==self.campo_cantidad:
   self.campo_alojamiento.focus_set()
   self.campo_alojamiento.select_range(0,'end')
   return 'break'
  if self.focus_get() in (self.campo_cantidad,self.campo_alojamiento):
   self.registrar()
   return 'break'
  self.registrar()
  return 'break'

 def actualizar_modo(self):
  tipo=self.tipo.get()
  alojamiento=tipo in MANUALES
  self.tipo_label.configure(text=tipo)
  valor=self.precio_temperada if tipo=='Piscina Temperada' else self.precio
  self.price_label.configure(text='Valor por persona' if alojamiento else pesos(valor),font=('Arial',13 if alojamiento else 18,'bold') if self.modo_compacto else ('Arial',17 if alojamiento else 23,'bold'))
  if alojamiento:
   self.boton_cambiar.configure(cursor='arrow')
   # Cabañas y Camping: cantidad de personas y monto TOTAL manual.
   self.ayuda_alojamiento.configure(text=f'Valor por persona de {tipo} (CLP)')
   self.ayuda_alojamiento.pack(fill='x',pady=(2,3),after=self.campo_cantidad)
   self.campo_alojamiento.pack(fill='x',pady=(0,8),after=self.ayuda_alojamiento)
  else:
   self.ayuda_alojamiento.pack_forget()
   self.campo_alojamiento.pack_forget()
   self.boton_cambiar.configure(cursor='hand2')
  for nombre,canvas in self.botones_tipo.items():
   selected=nombre==tipo
   canvas._romeral_color='#C62828' if selected else self.colores_tipo[nombre]
   canvas._romeral_texto=('✓  ' if selected else '')+nombre
   canvas.redibujar()
  self.campo_cantidad.focus_set()

 def seleccionar_pago(self,medio):
  self.medio.set(medio)
  self.actualizar_pagos()

 def actualizar_pagos(self):
  for medio,(frame,canvas) in self.payment_widgets.items():
   selected=self.medio.get()==medio
   color,soft=self.payment_colors[medio]
   canvas._romeral_texto=('✓  ' if selected else '○  ')+medio.upper()
   canvas._romeral_color=color if selected else soft
   canvas._romeral_fg='white' if selected else color
   canvas.redibujar()
  elegido=self.medio.get()
  self.pago_confirmado.set('PAGO: '+elegido.upper() if elegido else 'SELECCIONA UN MEDIO DE PAGO')
  if hasattr(self,'enter_label'):
   self.enter_label._romeral_color='#D9781F' if elegido else '#A7B5C4'
   self.enter_label.redibujar()

 def tecla(self,k):
  objetivo=self.monto_alojamiento if self.tipo.get() in MANUALES and self.campo_activo=='monto' else self.cantidad
  v=objetivo.get()
  if k=='C':objetivo.set('0')
  elif k=='⌫':objetivo.set(v[:-1] or '0')
  else:objetivo.set(k if v=='0' else (v+k)[:9])
  if objetivo is self.monto_alojamiento:self.monto_visible.set(pesos(int(objetivo.get() or 0)))
 def limpiar(self):self.cantidad.set('0')
 def actualizar_total(self):
  try:n=max(0,int(self.cantidad.get()))
  except ValueError:n=0
  try:manual=int(self.monto_alojamiento.get())
  except ValueError:manual=0
  unitario=self.precio_temperada if self.tipo.get()=='Piscina Temperada' else self.precio
  self.total.set(pesos(n*max(0,manual) if self.tipo.get() in MANUALES else n*unitario))
 def cambiar_precio(self):
  tipo=self.tipo.get()
  if tipo in MANUALES:return
  if not self.autorizar_supervisor():return
  temporada=tipo=='Piscina Temperada'
  anterior=self.precio_temperada if temporada else self.precio
  n=simpledialog.askinteger('Precio '+tipo,'Nuevo precio en pesos chilenos:',initialvalue=anterior,minvalue=1,maxvalue=10000000,parent=self)
  if n is not None and n!=anterior:
   clave='precio_temperada' if temporada else 'precio'
   with conn:
    conn.execute('INSERT OR REPLACE INTO config(key,value) VALUES (?,?)',(clave,str(n)))
    conn.execute('INSERT INTO auditoria_precios(fecha,precio_anterior,precio_nuevo) VALUES (?,?,?)',(datetime.now().isoformat(timespec='seconds'),anterior,n))
    conn.execute('INSERT INTO auditoria_precios_tipos(fecha,tipo,precio_anterior,precio_nuevo) VALUES (?,?,?,?)',(datetime.now().isoformat(timespec='seconds'),tipo,anterior,n))
   if temporada:self.precio_temperada=n
   else:self.precio=n
   self.price_label.configure(text=pesos(n));self.actualizar_total()

 def cierre_pendiente(self):
  hoy=datetime.now().date().isoformat()
  # Una jornada sin ventas no necesita cierre: no bloquear días sin operación.
  return conn.execute("""SELECT substr(v.fecha,1,10) FROM ventas v
   WHERE substr(v.fecha,1,10) < ? AND NOT EXISTS
   (SELECT 1 FROM cierres_caja c WHERE c.fecha=substr(v.fecha,1,10))
   GROUP BY substr(v.fecha,1,10) ORDER BY substr(v.fecha,1,10) LIMIT 1""",(hoy,)).fetchone()

 def comprobar_jornada(self, avisar=True):
  pendiente=self.cierre_pendiente()
  if pendiente:
   fecha=pendiente[0]
   if avisar and self._aviso_cierre_fecha != fecha:
    self._aviso_cierre_fecha=fecha
    messagebox.showwarning('CIERRE OBLIGATORIO',f'La jornada {fecha} tiene ventas sin cierre.\nNo se pueden registrar nuevas ventas hasta cerrarla.\n\nAbre «Cierre caja» y completa el cierre con clave de supervisor.',parent=self)
   self.estado.set(f'BLOQUEO DE VENTAS · Cierre pendiente: {fecha} · Solicita al supervisor')
   return False
  hoy=datetime.now().date().isoformat()
  if conn.execute('SELECT 1 FROM cierres_caja WHERE fecha=?',(hoy,)).fetchone():
   if avisar:messagebox.showwarning('Jornada cerrada','La jornada de hoy ya está cerrada. No se admiten nuevas ventas.',parent=self)
   self.estado.set('JORNADA CERRADA · No se admiten nuevas ventas')
   return False
  self._aviso_cierre_fecha=None
  return True

 def verificar_condiciones_emision(self):
  """Condiciones compartidas antes de registrar cualquier venta que vaya a emitir DTE.

  Usado por `registrar()` (venta presencial) y por el canje de entradas online
  (`CanjeOnlineController`, vía `panel_qr_online`). El bloqueo se comprueba
  ANTES de escribir en SQLite.
  """
  try:
   from validacion_produccion import CONFIG as CONFIG_PRODUCCION
   import json as _json
   _cfg=_json.loads(CONFIG_PRODUCCION.read_text(encoding='utf-8'))
   _habilitada=(_cfg.get('ambiente')=='produccion' and _cfg.get('emision_habilitada') is True)
  except (OSError,ValueError,TypeError):
   _habilitada=False
  if not _habilitada:
   messagebox.showwarning('Emisión electrónica deshabilitada',
    'No se registró ninguna venta. La emisión DTE 39 continúa bloqueada en la configuración de producción.\n\n'
    'No habilites producción hasta autorizar la primera emisión real.',parent=self)
   return False
  # No admitir nuevas ventas cuando exista un envío tributario sin resultado definitivo.
  # El cajero debe conciliarlo con Facturacion.com antes de continuar.
  try:
   _pendiente=conn.execute("SELECT venta_id,estado FROM intentos_soap_dte WHERE estado IN ('ENVIO_INICIADO','INCIERTO') ORDER BY id LIMIT 1").fetchone()
  except sqlite3.OperationalError:
   _pendiente=None
  if _pendiente:
   messagebox.showerror('DTE pendiente de conciliación',
    f'La venta {_pendiente[0]} tiene un envío SOAP en estado {_pendiente[1]}.\n\n'
    'No se puede registrar otra venta hasta comprobar su estado en Facturacion.com.\n'
    'No repitas la emisión ni modifiques manualmente el folio.',parent=self)
   return False
  if not self.comprobar_jornada():return False
  return True

 def registrar(self):
  if not self.verificar_condiciones_emision():return
  if not self.medio.get():
   messagebox.showwarning('Medio de pago','Selecciona Efectivo, Webpay o Tarjeta antes de registrar la venta.',parent=self);return
  if self.emision_en_curso:
   messagebox.showwarning('Emisión en curso','Espera el resultado de la boleta anterior antes de registrar otra venta.',parent=self);return
  try:n=int(self.cantidad.get())
  except ValueError:n=0
  if not 1<=n<=99999:
   messagebox.showwarning('Cantidad inválida','Ingresa una cantidad de personas mayor que cero.');return
  tipo=self.tipo.get()
  if tipo in MANUALES:
   try:precio_venta=int(self.monto_alojamiento.get())
   except ValueError:precio_venta=0
   if not 1<=precio_venta<=100000000:
    messagebox.showwarning('Valor inválido',f'Ingresa el valor por persona de {tipo} en pesos, mayor que cero.');return
   total=n*precio_venta
   if total>100000000:
    messagebox.showwarning('Total inválido','El total supera el límite permitido de $100.000.000.');return
  else:
   precio_venta=self.precio_temperada if tipo=='Piscina Temperada' else self.precio
   total=n*precio_venta
  try:
   with conn:
    cursor=conn.execute('INSERT INTO ventas(fecha,cantidad,precio,total,medio,tipo,estado_boleta,referencia_venta,tipo_dte) VALUES (?,?,?,?,?,?,?,?,?)',
     (datetime.now().isoformat(timespec='seconds'),n,precio_venta,total,self.medio.get(),tipo,'PENDIENTE_INTEGRACION',str(uuid.uuid4()),39))
    referencia=conn.execute('SELECT referencia_venta FROM ventas WHERE id=?',(cursor.lastrowid,)).fetchone()[0]
    registrar_control_emision(conn,cursor.lastrowid,referencia)
    conn.execute('INSERT INTO eventos_dte(venta_id,fecha,evento,detalle) VALUES (?,?,?,?)',
     (cursor.lastrowid,datetime.now().isoformat(timespec='seconds'),'VENTA_REGISTRADA','Pendiente de emisión electrónica controlada'))
  except sqlite3.Error as e:messagebox.showerror('Error al guardar',str(e));return
  nueva_id=cursor.lastrowid
  self.limpiar();self.monto_alojamiento.set('0');self.monto_visible.set('$0');self.reiniciar_pago();self.campo_cantidad.focus_set();self.actualizar_resumen();self.estado.set(f'Venta {nueva_id}: {pesos(total)} · BOLETA PENDIENTE')
  self.emitir_automaticamente(nueva_id,total)

 def registrar_venta_online(self, total, cantidad):
  """Inserta la venta de un canje de entrada online ya confirmado por el backend.

  Medio siempre Webpay (regla del negocio: toda entrada online se pagó por
  Webpay en la web) y origen 'ONLINE' para que el cierre de caja (Task 20)
  la muestre en su propia línea sin sumarla al efectivo esperado. El resto
  del flujo (control de emisión, evento de auditoría) replica `registrar()`.

  tipo siempre 'Entrada General': es el único producto que entra al sistema
  (docs/PROYECTO.md 4.1); la columna `origen` ya distingue online de
  presencial para todo lo demás. `VentaBoleta.validar()` en
  integracion_facturacion.py solo acepta un conjunto fijo de modalidades y
  rechazaría cualquier otro valor, lo que haría fallar la emisión de la
  boleta en cada canje online (ver tests/test_registrar_venta_online.py).
  """
  with conn:
   cursor=conn.execute(
    "INSERT INTO ventas(fecha,cantidad,precio,total,medio,tipo,estado_boleta,referencia_venta,tipo_dte,origen) VALUES (?,?,?,?,?,?,?,?,?,?)",
    (datetime.now().isoformat(timespec='seconds'),cantidad,total//max(cantidad,1),total,'Webpay','Entrada General','PENDIENTE_INTEGRACION',str(uuid.uuid4()),39,'ONLINE'))
   referencia=conn.execute('SELECT referencia_venta FROM ventas WHERE id=?',(cursor.lastrowid,)).fetchone()[0]
   registrar_control_emision(conn,cursor.lastrowid,referencia)
   conn.execute('INSERT INTO eventos_dte(venta_id,fecha,evento,detalle) VALUES (?,?,?,?)',
    (cursor.lastrowid,datetime.now().isoformat(timespec='seconds'),'VENTA_REGISTRADA','Canje de entrada online; pendiente de emisión electrónica controlada'))
  return cursor.lastrowid

 def consultar_resultado_emision(self, venta_id):
  """Lee el folio y estado de boleta actuales de una venta, sin bloquear.

  Usado para sondear el resultado de `emitir_automaticamente()` (asíncrono,
  resuelto en un hilo propio) una vez que `emision_en_curso` vuelve a False.
  """
  fila=conn.execute('SELECT folio_dte,estado_boleta FROM ventas WHERE id=?',(venta_id,)).fetchone()
  if not fila:
   return None,None
  return fila[0],fila[1]

 def emitir_automaticamente(self, venta_id, total):
  """Un solo intento SOAP por venta, sin confirmaciones adicionales ni reenvíos."""
  if self.emision_en_curso:return
  self.emision_en_curso=True
  inicio_flujo=time.monotonic()
  registrar_tiempo(venta_id,'INICIO_EMISION')
  self.estado.set(f'Venta {venta_id} guardada · emitiendo DTE 39; espera el resultado')
  def trabajo():
   inicio_soap=time.monotonic()
   try:
    proceso=subprocess.run([sys.executable,str(Path(__file__).with_name('EMISION_REAL_CONTROLADA.py')),
      '--venta',str(venta_id),f'EMITIR {venta_id} {total}'],capture_output=True,text=True,
      timeout=100,cwd=str(Path(__file__).parent))
    mensaje=(proceso.stdout if proceso.returncode==0 else proceso.stderr).strip()
    if not mensaje:mensaje='Resultado no confirmado. NO REINTENTAR; verificar en Facturacion.com.'
   except Exception as exc:
    mensaje=f'RESULTADO INCIERTO ({type(exc).__name__}). NO REINTENTAR. Revisar Facturacion.com.'
   registrar_tiempo(venta_id,'FIN_PROCESO_EMISION',segundos=round(time.monotonic()-inicio_soap,3),resultado='CONFIRMADO' if 'RESPUESTA SOAP CONFIRMADA' in mensaje else 'REVISAR')
   def terminar():
    # Conservar el bloqueo mientras se recupera e imprime el PDF.
    # En caso de respuesta incierta, el bloqueo se libera solo para permitir
    # revisar el historial; la siguiente venta se detiene por la bitácora SOAP.
    if 'RESPUESTA SOAP CONFIRMADA' not in mensaje:
     self.emision_en_curso=False
    self.estado.set(f'Venta {venta_id} · '+mensaje[:170])
    self.actualizar_resumen()
    if 'RESPUESTA SOAP CONFIRMADA' in mensaje:
     self.estado.set(f'Venta {venta_id} · DTE confirmado · recuperando PDF e imprimiendo')
     impresora_destino=config('impresora_80mm') or None
     def imprimir_en_segundo_plano():
      try:
       # SOLO recuperación del PDF: jamás repetir la emisión SOAP.
       def informar_espera(intento, maximo, segundos):
        self.after(0,lambda i=intento,m=maximo,s=segundos:
         self.estado.set(f'Venta {venta_id} · DTE emitido · PDF aún no disponible; espera {s}s (intento {i}/{m})'))
       inicio_pdf=time.monotonic()
       ruta=recuperar_con_espera(venta_id,notificar=informar_espera)
       registrar_tiempo(venta_id,'PDF_RECUPERADO',segundos=round(time.monotonic()-inicio_pdf,3))
       inicio_impresion=time.monotonic()
       resultado=imprimir_pdf_oficial(ruta,impresora_destino,venta_id=venta_id)
       registrar_tiempo(venta_id,'IMPRESION_ENVIADA_COLA',segundos=round(time.monotonic()-inicio_impresion,3),total_desde_inicio=round(time.monotonic()-inicio_flujo,3))
       with sqlite3.connect(DB,timeout=15) as db_auditoria:
        db_auditoria.execute("""INSERT INTO eventos_dte(venta_id,fecha,evento,detalle)
         VALUES (?,?,?,?)""",(venta_id,datetime.now().isoformat(timespec='seconds'),
         'IMPRESION_AUTOMATICA_ENVIADA','PDF oficial recuperado y trabajo enviado a cola de impresión'))
       # Confirmación no modal: el cajero no necesita presionar OK.
       # La cola confirma recepción del trabajo, NO la salida física del papel.
       with sqlite3.connect(DB,timeout=15) as db_folio:
        fila=db_folio.execute('SELECT folio_dte FROM ventas WHERE id=?',(venta_id,)).fetchone()
       folio=str(fila[0]).strip() if fila and fila[0] else 'pendiente de consulta'
       estado_exito=f'Venta {venta_id} · Boleta folio {folio} enviada a impresión · Caja lista'
       self.after(0,lambda texto=estado_exito: (self.estado.set(texto),setattr(self,'emision_en_curso',False)))
      except Exception as exc:
       registrar_tiempo(venta_id,'ERROR_POST_EMISION',total_desde_inicio=round(time.monotonic()-inicio_flujo,3),error=type(exc).__name__)
       aviso=f'DTE EMITIDO; IMPRESIÓN PENDIENTE: {exc}\n\nNO repetir la venta. El folio permanece registrado.'
       self.after(0,lambda texto=aviso: (setattr(self,'emision_en_curso',False),messagebox.showwarning('ROMERAL · Impresión pendiente',texto,parent=self)))
     threading.Thread(target=imprimir_en_segundo_plano,daemon=True).start()
    else:
     # Solo reconocer agotamiento cuando la respuesta oficial contiene una señal explícita.
     # Nunca equiparar errores de red, timeouts o respuestas inciertas con falta de folios.
     alerta=registrar_alerta(APP_DIR,venta_id,mensaje)
     if alerta:
      self.estado.set('ALERTA · POSIBLE AGOTAMIENTO DE FOLIOS DTE 39 · AVISAR AL SUPERVISOR')
      messagebox.showerror('ROMERAL · FOLIOS DTE 39',
       'Facturacion.com informó una posible falta de folios para DTE 39.\n\n'
       'Solicita al supervisor revisar y gestionar nuevos folios con el proveedor.\n'
       'No repitas esta venta: verifica su estado en el portal antes de continuar.\n\n'
       'Detalle: '+mensaje[:700],parent=self)
     else:
      messagebox.showwarning('DTE 39 · requiere revisión',mensaje+'\n\nNO registrar otra boleta para reemplazarla ni repetir esta emisión.',parent=self)
   self.after(0,terminar)
  threading.Thread(target=trabajo,daemon=True).start()

 def reimprimir_dte(self):
  """Reimprime un DTE 39 emitido buscando su folio tributario, nunca su ID interno."""
  folio=simpledialog.askstring('Reimprimir boleta electrónica',
   'Ingresa el FOLIO OFICIAL de la boleta (ejemplo: 26185):',parent=self)
  if folio is None:return
  folio=folio.strip()
  if not folio.isascii() or not folio.isdecimal() or int(folio)<=0:
   messagebox.showerror('Folio inválido','Ingresa únicamente el número del folio oficial de la boleta.',parent=self)
   return
  # El folio es único dentro del tipo DTE 39; nunca se interpreta como ID de venta.
  # Se consulta en el hilo de Tkinter; la descarga usa sus propias conexiones SQLite.
  filas=conn.execute("""SELECT id,fecha,tipo,cantidad,total,medio
     FROM ventas WHERE folio_dte=? AND tipo_dte=39 AND estado_boleta='EMITIDA'
     ORDER BY id DESC LIMIT 2""",(str(int(folio)),)).fetchall()
  if not filas:
   messagebox.showwarning('Boleta no encontrada',
    'No existe una boleta DTE 39 EMITIDA con ese folio en el historial local.\n'
    'No se imprimió ni se emitió otra boleta.',parent=self)
   return
  if len(filas)!=1:
   messagebox.showerror('Folio duplicado',
    'Se detectaron registros ambiguos para este folio. Revisa el historial antes de imprimir.',parent=self)
   return
  vid,fecha,tipo,cantidad,total,medio=filas[0]
  if not messagebox.askyesno('Confirmar reimpresión',
    f'Folio DTE 39: {folio}\nVenta ROMERAL: {vid}\nFecha: {fecha}\n'
    f'Concepto: {nombre_visible(tipo)}\nPersonas: {cantidad}\n'
    f'Total: {pesos(total)}\nMedio: {medio}\n\n'
    '¿Reimprimir esta boleta existente?\nNo se generará otro DTE.',parent=self):return
  impresora_destino=config('impresora_80mm') or None
  def tarea():
   try:
    ruta=recuperar(vid)
    resultado=imprimir_pdf_oficial(ruta,impresora_destino,venta_id=vid)
    # Registro de auditoría con conexión propia para evitar errores de hilos SQLite.
    with sqlite3.connect(DB,timeout=15) as db_auditoria:
     db_auditoria.execute("""INSERT INTO eventos_dte(venta_id,fecha,evento,detalle)
       VALUES (?,?,?,?)""",(vid,datetime.now().isoformat(timespec='seconds'),
       'REIMPRESION_SOLICITADA',f'DTE 39 folio {folio}; trabajo enviado a cola de impresión'))
    mensaje=f'Folio {folio} enviado a impresión.\n'+resultado+\
      '\n\nComprueba la impresión física y el timbre. No se emitió otra boleta.'
   except Exception as exc:
    mensaje='No se imprimió: '+str(exc)+'\nNo se emitió otra boleta.'
   self.after(0,lambda:messagebox.showinfo('Reimpresión DTE',mensaje,parent=self))
  threading.Thread(target=tarea,daemon=True).start()

 def abrir_pdf_oficial(self):
  """Selecciona y envía el PDF tributario ORIGINAL a la impresora configurada."""
  ruta=filedialog.askopenfilename(parent=self,title='Seleccionar PDF oficial de Facturacion.com',filetypes=[('PDF oficial','*.pdf')])
  if not ruta:return
  if not messagebox.askyesno('Impresión de boleta oficial','Confirma que este PDF fue descargado de Facturacion.com y corresponde a la venta correcta.\n\nEl PDF oficial se conservará intacto. Se imprimirá una copia adaptada a 80 mm en la POS-80.',parent=self):return
  try:
   impresora=config('impresora_80mm') or None
   resultado=imprimir_pdf_oficial(ruta, impresora)
   messagebox.showinfo('Impresión solicitada',resultado+'\n\nVerifica la salida física de la boleta.',parent=self)
  except Exception as exc:
   messagebox.showerror('No se pudo imprimir',str(exc),parent=self)

 def panel_emitir_dte(self, venta_preferida=None):
  """Emisión opt-in, una venta a la vez, proceso aislado; nunca reintenta."""
  try:
   from validacion_produccion import CONFIG as CONFIG_PRODUCCION
   import json as _json
   _cfg=_json.loads(CONFIG_PRODUCCION.read_text(encoding='utf-8'))
   _habilitada=(_cfg.get('ambiente')=='produccion' and _cfg.get('emision_habilitada') is True)
  except (OSError,ValueError,TypeError):
   _habilitada=False
  if not _habilitada:
   messagebox.showwarning('Emisión bloqueada','No se envió ningún DTE. La producción sigue deshabilitada.',parent=self)
   return
  if self.emision_en_curso:
   messagebox.showwarning('Emisión en curso','Espera el resultado de la emisión anterior.',parent=self);return
  from registro_intentos_soap import crear_tabla as crear_intentos
  crear_intentos(conn);conn.commit()
  filas=conn.execute("""SELECT v.id,v.fecha,v.tipo,v.cantidad,v.total,v.medio
     FROM ventas v JOIN control_emision c ON c.venta_id=v.id
     WHERE v.estado_boleta='PENDIENTE_INTEGRACION' AND c.estado='PENDIENTE_INTEGRACION'
       AND v.folio_dte IS NULL AND substr(v.fecha,1,10)=?
       AND NOT EXISTS (SELECT 1 FROM intentos_soap_dte i WHERE i.venta_id=v.id)
     ORDER BY v.id DESC LIMIT 50""",(datetime.now().strftime('%Y-%m-%d'),)).fetchall()
  if not filas:
   messagebox.showinfo('Sin ventas elegibles','No hay ventas de hoy pendientes sin intentos previos.\nUna boleta emitida o incierta NO se puede reenviar.',parent=self);return
  win=tk.Toplevel(self);win.title('ROMERAL | Emisión electrónica real DTE 39');win.geometry('690x410');win.configure(bg='#f1f6fc')
  tk.Label(win,text='EMISIÓN ELECTRÓNICA DTE 39',font=('Arial',19,'bold'),bg='#f1f6fc',fg='#082e56').pack(pady=(20,6))
  tk.Label(win,text='Producción · un envío por venta · sin reintentos',bg='#f1f6fc',fg='#8a4b00').pack(pady=4)
  opciones={f'{r[0]} · {r[2]} · {r[3]} pers. · {pesos(r[4])} · {r[5]}':r for r in filas}
  seleccionado=tk.StringVar()
  for etiqueta,r in opciones.items():
   if r[0]==venta_preferida:seleccionado.set(etiqueta)
  if not seleccionado.get():seleccionado.set(next(iter(opciones)))
  ttk.Combobox(win,textvariable=seleccionado,values=list(opciones),state='readonly',width=70).pack(pady=14)
  tk.Label(win,text='La operación puede generar una boleta tributaria real.',bg='#f1f6fc').pack(pady=4)
  estado=tk.StringVar(value='Selecciona una venta y confirma para emitir.')
  tk.Label(win,textvariable=estado,wraplength=630,bg='#f1f6fc',fg='#082e56',justify='center').pack(pady=12)
  def emitir():
   if self.emision_en_curso:return
   fila=opciones.get(seleccionado.get())
   if not fila:return
   vid,fecha,tipo,cantidad,total,medio=fila
   if not messagebox.askyesno('CONFIRMACIÓN TRIBUTARIA',f'¿EMITIR BOLETA REAL DTE 39?\n\nVenta: {vid}\nServicio: {tipo}\nPersonas: {cantidad}\nMonto IVA incluido: {pesos(total)}\nPago: {medio}\n\nPuede consumir un folio. NO se reintentará automáticamente.',parent=win):return
   self.emision_en_curso=True;boton.config(state='disabled');estado.set('Enviando una sola vez. No cierres ROMERAL ni repitas la operación.');win.update_idletasks()
   def trabajo():
    try:
     proceso=subprocess.run([sys.executable,str(Path(__file__).with_name('EMISION_REAL_CONTROLADA.py')),'--venta',str(vid),f'EMITIR {vid} {total}'],capture_output=True,text=True,timeout=100,cwd=str(Path(__file__).parent))
     mensaje=(proceso.stdout if proceso.returncode==0 else proceso.stderr).strip()
     if not mensaje:mensaje='Sin respuesta interpretable. Revisar portal antes de cualquier acción.'
    except Exception as exc:
     mensaje=f'RESULTADO INCIERTO: {type(exc).__name__}. NO REINTENTAR. Revisar Facturacion.com.'
    def terminar():
     self.emision_en_curso=False
     estado.set(mensaje)
     messagebox.showinfo('Resultado de emisión · revisar portal',mensaje,parent=win)
     self.actualizar_resumen()
     win.destroy()
    self.after(0,terminar)
   threading.Thread(target=trabajo,daemon=True).start()
  boton=self.boton(win,'EMITIR BOLETA REAL · UNA VEZ',emitir,bg='#16734B',fg='white',size=13)
  boton.pack(pady=15)
  tk.Label(win,text='Después de emitir, verifica el folio y descarga el PDF oficial en Facturacion.com.\nLa impresión tributaria usa ese PDF, no un comprobante interno.',bg='#f1f6fc',justify='center').pack(pady=6)

 def datos_hoy(self):
  return conn.execute('SELECT medio,COALESCE(SUM(cantidad),0),COALESCE(SUM(total),0),COUNT(*) FROM ventas WHERE fecha>=? AND fecha<? AND estado_boleta <> \'ANULADA_PRUEBA\' GROUP BY medio',
   (datetime.now().strftime('%Y-%m-%d'),(datetime.now().date()).isoformat()+'T99')).fetchall()
 def actualizar_resumen(self):
  rows=self.datos_hoy();persons=sum(r[1] for r in rows);amount=sum(r[2] for r in rows);ops=sum(r[3] for r in rows)
  by={r[0]:r[2] for r in rows}
  desglose=conn.execute("SELECT CASE WHEN tipo='Alojamiento' THEN 'Cabañas' ELSE tipo END,COALESCE(SUM(cantidad),0),COALESCE(SUM(total),0) FROM ventas WHERE substr(fecha,1,10)=? AND estado_boleta <> 'ANULADA_PRUEBA' GROUP BY CASE WHEN tipo='Alojamiento' THEN 'Cabañas' ELSE tipo END",(datetime.now().strftime('%Y-%m-%d'),)).fetchall()
  detalle='\n'.join(f'{t}: {p} pers. · {pesos(m)}' for t,p,m in desglose)
  self.resumen.set(f'PERSONAS INGRESADAS\n{persons}\n\nRECAUDACIÓN\n{pesos(amount)}\n\nVENTAS REALIZADAS\n{ops}\n\nPOR MEDIO DE PAGO\n'+ '\n'.join(f'{m}: {pesos(by.get(m,0))}' for m in PAYMENTS) + '\n\nPOR TIPO DE ENTRADA\n' + detalle)
 def panel_facturacion(self):
   """Inspección local únicamente; nunca transmite credenciales ni invoca Procesar."""
   win=tk.Toplevel(self);win.title('ROMERAL | Estado de producción');win.geometry('740x490')
   win.configure(bg='#f1f6fc')
   tk.Label(win,text='FACTURACIÓN ELECTRÓNICA · PRODUCCIÓN',bg='#f1f6fc',fg='#082e56',font=('Arial',19,'bold')).pack(pady=(20,8))
   tk.Label(win,text='Diagnóstico de solo lectura · No emite boletas desde esta ventana',bg='#f1f6fc',fg='#744300',font=('Arial',12,'bold')).pack(pady=(0,16))
   info=tk.StringVar(value='Presiona comprobar para revisar la configuración local.')
   tk.Label(win,textvariable=info,bg='white',fg='#10294c',justify='left',anchor='nw',wraplength=670,font=('Arial',12),padx=18,pady=18).pack(fill='both',expand=True,padx=20,pady=8)
   def comprobar():
    ruta=APP_DIR/'facturacion_produccion.json'
    if not ruta.exists():
     info.set('No se encontró facturacion_produccion.json en ROMERAL_Datos.\nNo se modificó ninguna venta.\nEmisión bloqueada.');return
    try:
     data=json.loads(ruta.read_text(encoding='utf-8'))
     # No se muestran RUT, usuario, clave, ni respuestas privadas.
     ambiente=str(data.get('ambiente','')).lower()
     campos=bool(data.get('usuario') and data.get('rut'))
     if ambiente not in ('produccion','producción'):
      info.set('Configuración encontrada, pero el ambiente no está identificado como producción.\nEmisión bloqueada.');return
     try:
      import keyring
      # Las versiones del configurador pueden usar un identificador distinto.
      # No adivinarlo ni consultar credenciales de pruebas.
      llavero='Disponible (no se accedió a la contraseña)'
     except ImportError:
      llavero='Dependencia keyring no instalada'
     pendientes=conn.execute("SELECT COUNT(*) FROM ventas WHERE estado_boleta NOT IN ('EMITIDA','ANULADA_PRUEBA')").fetchone()[0]
     info.set('Configuración de PRODUCCIÓN localizada: SÍ\nCampos de identificación presentes: '+('SÍ' if campos else 'NO')+'\nLlavero del sistema: '+llavero+'\nVentas no confirmadas como emitidas: '+str(pendientes)+'\n\nAutenticación remota: NO VERIFICADA EN ESTE PANEL\nEmisión: BLOQUEADA\nFolios: NO SOLICITADOS\n\nEste panel no modifica las ventas ni transmite datos.')
    except (OSError,ValueError) as exc:
     info.set('No se pudo validar el archivo de configuración.\nEmisión bloqueada.\nDetalle: '+type(exc).__name__)
   def vista_previa():
    from integracion_facturacion import VentaBoleta, generar_txt
    try:
     texto=generar_txt(VentaBoleta(referencia='VISTA-PREVIA-NO-EMITIR',tipo='Entrada General',personas=1,total=10000,medio='Efectivo'))
     popup=tk.Toplevel(win);popup.title('VISTA PREVIA LOCAL · NO EMITIDA');popup.geometry('750x530')
     tk.Label(popup,text='EJEMPLO $10.000 IVA INCLUIDO · NO TRANSMITIDO',fg='#744300',font=('Arial',12,'bold')).pack(pady=10)
     area=tk.Text(popup,wrap='none');area.insert('1.0',texto);area.configure(state='disabled');area.pack(fill='both',expand=True,padx=10,pady=10)
    except Exception as exc:
     messagebox.showerror('Vista previa',f'No se pudo generar la vista previa: {type(exc).__name__}',parent=win)
   def consulta_produccion():
    if not messagebox.askyesno('Autorización de consulta',
       'Se enviarán las credenciales de PRODUCCIÓN guardadas en el llavero a Facturacion.com mediante HTTPS.\n\nSolo se ejecutará ConsultarCAF (DTE 39). NO se emitirá ninguna boleta.\n\n¿Autorizar esta consulta?',parent=win):
     return
    info.set('Consultando servicio de producción...\nNo se emitirá ninguna boleta.')
    import threading
    def trabajo():
     try:
      from validacion_produccion import consultar_caf_seguro
      resultado=consultar_caf_seguro()
     except Exception as exc:
      resultado='Consulta no completada ('+type(exc).__name__+').\nAutenticación NO confirmada. Emisión BLOQUEADA.'
     try: win.after(0,lambda:info.set(resultado))
     except RuntimeError: pass
    threading.Thread(target=trabajo,daemon=True).start()
   self.boton_color(win,'DIAGNOSTICAR CAF PRODUCCIÓN · SOLO LECTURA',consulta_produccion,'#176B87',size=12).pack(fill='x',padx=20,pady=4)
   self.boton_color(win,'COMPROBAR CONFIGURACIÓN LOCAL',comprobar,'#176B87',size=12).pack(fill='x',padx=20,pady=4)
   self.boton_color(win,'COMPROBANTES INTERNOS · 80 MM',self.panel_comprobantes,'#176B87',size=12).pack(fill='x',padx=20,pady=4)
   tk.Button(win,text='VER EJEMPLO LOCAL DE BOLETA $10.000',command=vista_previa,font=('Arial',12,'bold'),pady=9).pack(fill='x',padx=20,pady=(0,18))

 def panel_qr_online(self):
  """Canje de una entrada online comprada en la web (QR o ingreso manual).

  Dos pasos, igual que mock/frames/canje_online.html: BUSCAR ENTRADA
  (ventas_online.lookup_ticket, solo lectura) muestra el estado y los
  datos de la entrada; CANJEAR Y EMITIR BOLETA (CanjeOnlineController,
  mismo módulo que respalda sus tests) hace el canje real en el backend
  y dispara la emisión de la boleta por la ruta ya existente de
  emitir_automaticamente().
  """
  controller=CanjeOnlineController(self)
  # Holds the last lookup so the redeem button acts on exactly what is on
  # screen, not on whatever is currently typed in the entry field.
  estado={'ticket':None,'code':None,'habilitado':False}
  win=tk.Toplevel(self)
  win.title('ROMERAL | Canje de entrada online')
  win.geometry('820x700');win.minsize(700,600);win.configure(bg='#EDF3F8')
  tk.Label(win,text='CANJE DE ENTRADA ONLINE · QR',bg='#102F52',fg='white',
           font=('Arial',21,'bold'),pady=20).pack(fill='x')
  zona=tk.Frame(win,bg='#EDF3F8',padx=18,pady=16);zona.pack(fill='both',expand=True)

  panel_entrada=tk.Frame(zona,bg='white',padx=24,pady=20);panel_entrada.pack(fill='x',pady=(0,16))
  tk.Label(panel_entrada,text='Escanea el código QR o ingrésalo manualmente:',bg='white',fg='#102F52',
           font=('Arial',12,'bold')).pack(anchor='w')
  codigo=tk.StringVar()
  fila_entrada=tk.Frame(panel_entrada,bg='white');fila_entrada.pack(fill='x',pady=(10,0))
  entrada=tk.Entry(fila_entrada,textvariable=codigo,font=('Arial',17),width=36)
  entrada.pack(side='left',fill='x',expand=True);entrada.focus_set()
  self.boton_color(fila_entrada,'BUSCAR ENTRADA',lambda:buscar(),'#06499A',size=12,alto=50).pack(side='left',padx=(14,0))

  banner_var=tk.StringVar(value='')
  banner_label=tk.Label(zona,textvariable=banner_var,justify='left',anchor='w',
                         font=('Arial',15,'bold'),padx=22,pady=16,wraplength=740)

  tarjeta=tk.Frame(zona,bg='white',padx=24,pady=20)
  tarjeta_var=tk.StringVar(value='')
  tk.Label(tarjeta,textvariable=tarjeta_var,bg='white',fg='#17385C',justify='left',anchor='nw',
           font=('Arial',13)).pack(anchor='w')

  def canjear_click():
   if not estado['habilitado'] or not estado['code']:
    return
   mensaje=controller.canjear(estado['code'])
   messagebox.showinfo('Canje de entrada',mensaje,parent=win)
   # Re-read the ticket so the screen reflects the real post-redeem state
   # (REDEEMED, folio pending/confirmed) instead of guessing it locally.
   mostrar_ticket(estado['code'],_lookup_seguro(estado['code']))

  boton_canjear=self.boton_color(zona,'CANJEAR Y EMITIR BOLETA',canjear_click,'#AAB3BE',size=14,alto=66,fg='#E7EAEE')
  boton_canjear.pack(fill='x')

  def habilitar_boton(habilitado):
   estado['habilitado']=habilitado
   boton_canjear._romeral_color='#19705B' if habilitado else '#AAB3BE'
   boton_canjear._romeral_fg='white' if habilitado else '#E7EAEE'
   boton_canjear.redibujar()

  def _lookup_seguro(code):
   try:
    return ventas_online.lookup_ticket(code)
   except Exception as exc:
    messagebox.showwarning('Ventas online',
     f'No se pudo consultar el backend: {type(exc).__name__}. Revisa la conexión e inténtalo de nuevo.',parent=win)
    return None

  def mostrar_ticket(code,ticket):
   estado['code']=code;estado['ticket']=ticket
   tarjeta.pack_forget()
   if ticket is None:
    banner_var.set('CÓDIGO NO ENCONTRADO\nNo existe ninguna entrada con ese código. Revisa el escaneo.')
    banner_label.configure(bg='#FBE0E0',fg='#B42332')
    habilitar_boton(False)
    banner_label.pack(fill='x',pady=(0,16),before=boton_canjear)
    return
   status=ticket.get('status')
   fuera_temporada=ticket.get('display_status')=='fuera de temporada'
   if fuera_temporada:
    banner_var.set(f'FUERA DE TEMPORADA\nVenció el {ticket.get("valid_until")}. No se puede canjear.')
    banner_label.configure(bg='#E8E8EC',fg='#41536B')
    puede=False
   elif status=='VALID':
    banner_var.set('ENTRADA VÁLIDA\nLista para canjear. Verifica los datos antes de confirmar.')
    banner_label.configure(bg='#DDF0E6',fg='#19705B')
    puede=True
   elif status=='REDEEMED':
    banner_var.set(f'YA CANJEADA\n{ticket.get("redeemed_at") or ""} · {ticket.get("redeemed_by") or ""}')
    banner_label.configure(bg='#FFF0CF',fg='#744300')
    puede=False
   elif status=='REFUNDED_AFTER_REDEMPTION':
    banner_var.set('REEMBOLSADA DESPUÉS DE CANJEADA\nEl pedido fue reembolsado después del canje. No se puede volver a canjear.')
    banner_label.configure(bg='#FBE0E0',fg='#B42332')
    puede=False
   else:
    banner_var.set('ENTRADA ANULADA\nEl pedido fue reembolsado o cancelado en WooCommerce.')
    banner_label.configure(bg='#FBE0E0',fg='#B42332')
    puede=False
   lineas='\n'.join(
    f"  · {l.get('product_name','')} x{l.get('quantity','?')} · {pesos(l.get('unit_price',0))} c/u · {pesos(l.get('line_total',0))}"
    for l in ticket.get('lines',[]))
   tarjeta_var.set(
    f"Comprador: {ticket.get('buyer_name','')}\n"
    f"Pedido: #{ticket.get('woo_order_number','')}\n"
    f"Personas: {ticket.get('people_count','')}\n\n"
    f"{lineas}\n\n"
    f"Total pagado · {ticket.get('payment_method','Webpay')}: {pesos(ticket.get('total_paid',0))}")
   banner_label.pack(fill='x',pady=(0,16),before=boton_canjear)
   tarjeta.pack(fill='both',expand=True,pady=(0,16),before=boton_canjear)
   habilitar_boton(puede)

  def buscar(event=None):
   code=codigo.get().strip()
   if not code:
    return
   mostrar_ticket(code,_lookup_seguro(code))
   entrada.select_range(0,'end');entrada.focus_set()

  entrada.bind('<Return>',buscar)

 def imprimir_cierre_termico(self, fecha, preliminar=False):
  from cierre_termico import crear_pdf_cierre, enviar_pdf_termico
  destino=crear_pdf_cierre(conn, fecha, APP_DIR/'cierres', preliminar=preliminar)
  try:
   mensaje=enviar_pdf_termico(destino, config('impresora_80mm') or None)
   messagebox.showinfo('Impresión de cierre',mensaje+'\n\nPDF guardado en: '+str(destino),parent=self)
  except Exception as exc:
   messagebox.showwarning('Cierre guardado · Impresión pendiente',
    'El PDF quedó guardado. No se perdió el cierre.\n\n'+str(exc)+'\n\nArchivo: '+str(destino),parent=self)

 def panel_cierre(self):
  pendiente=self.cierre_pendiente()
  fecha=pendiente[0] if pendiente else datetime.now().date().isoformat()
  win=tk.Toplevel(self);win.title('ROMERAL | Cierre diario obligatorio');win.geometry('810x730');win.configure(bg='#f1f6fc')
  tk.Label(win,text='CIERRE DIARIO DE CAJA',bg='#f1f6fc',fg='#082e56',font=('Arial',21,'bold')).pack(pady=(16,5))
  tk.Label(win,text=f'Jornada: {fecha} · Un cierre por fecha · Supervisor',bg='#f1f6fc',fg='#744300',font=('Arial',12,'bold')).pack(pady=(0,12))
  info=tk.StringVar()
  tk.Label(win,textvariable=info,bg='white',fg='#10294c',justify='left',anchor='nw',font=('Arial',12),padx=20,pady=14).pack(fill='both',expand=True,padx=18,pady=8)
  fila=tk.Frame(win,bg='#f1f6fc');fila.pack(fill='x',padx=18,pady=6)
  tk.Label(fila,text='EFECTIVO CONTADO (CLP):',bg='#f1f6fc',fg='#10294c',font=('Arial',12,'bold')).pack(side='left')
  contado=tk.StringVar()
  tk.Entry(fila,textvariable=contado,font=('Arial',16),justify='right',width=18).pack(side='right')
  def resumen():
   rows=conn.execute("SELECT id,fecha,tipo,medio,cantidad,total,estado_boleta,folio_dte FROM ventas WHERE substr(fecha,1,10)=? AND estado_boleta != 'ANULADA_PRUEBA' ORDER BY id",(fecha,)).fetchall()
   medios={m:sum(int(r[5]) for r in rows if r[3]==m) for m in PAYMENTS}
   tipos={}
   for _,_,tipo,medio,personas,total,_,_ in rows:
    tipo=nombre_visible(tipo)
    a=tipos.setdefault(tipo,{'personas':0,'total':0,'ventas':0})
    a['personas']+=int(personas);a['total']+=int(total);a['ventas']+=1
   return rows,medios,tipos,len(rows),sum(int(r[4]) for r in rows),sum(int(r[5]) for r in rows)
  def refrescar():
   rows,medios,tipos,ventas,personas,total=resumen()
   cierre=conn.execute('SELECT creado,efectivo_contado,diferencia FROM cierres_caja WHERE fecha=?',(fecha,)).fetchone()
   estado=(f'CERRADO el {cierre[0]} · Efectivo contado {pesos(cierre[1])} · Diferencia {pesos(cierre[2])}' if cierre else 'ABIERTO · Cierre obligatorio antes de la próxima jornada')
   detalle='\n'.join(f'  {k}: {v["personas"]} personas · {v["ventas"]} ventas · {pesos(v["total"])}' for k,v in sorted(tipos.items())) or '  Sin ventas'
   info.set(f'ESTADO: {estado}\n\nVENTAS: {ventas}     PERSONAS: {personas}\nRECAUDACIÓN TOTAL: {pesos(total)}\n\nEFECTIVO ESPERADO: {pesos(medios["Efectivo"])}\nWEBPAY: {pesos(medios["Webpay"])}\nTARJETA: {pesos(medios["Tarjeta"])}\n\nPOR SERVICIO:\n{detalle}\n\nSe guarda detalle inmutable de operaciones al cierre.')
  def cerrar():
   if conn.execute('SELECT 1 FROM cierres_caja WHERE fecha=?',(fecha,)).fetchone():
    messagebox.showwarning('Ya cerrado','Esta jornada ya tiene cierre. Puedes reimprimirlo.',parent=win);return
   entrada=contado.get().strip().replace('.','')
   if not entrada.isdigit():
    messagebox.showwarning('Efectivo contado','Ingresa efectivo contado en pesos (0 o mayor).',parent=win);return
   efectivo=int(entrada)
   if efectivo>1000000000:
    messagebox.showwarning('Monto','Revisa el efectivo contado.',parent=win);return
   rows,medios,tipos,ventas,personas,total=resumen()
   diferencia=efectivo-medios['Efectivo']
   if not self.autorizar_supervisor():return
   if not messagebox.askyesno('Confirmar cierre definitivo',f'Jornada: {fecha}\nVentas: {ventas}\nTotal: {pesos(total)}\nEfectivo esperado: {pesos(medios["Efectivo"])}\nContado: {pesos(efectivo)}\nDiferencia: {pesos(diferencia)}\n\nCierre único e irreversible. ¿Confirmas?',parent=win):return
   # Nunca cerrar mientras una emisión real está en curso: esperar su resultado.
   if self.emision_en_curso:
    messagebox.showwarning('Emisión en curso','Espera a que termine la emisión de la boleta antes de cerrar.',parent=win);return
   try:
    backup=APP_DIR/('romeral_ANTES_CIERRE_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.sqlite3')
    with sqlite3.connect(backup) as copia:conn.backup(copia)
    # Releer dentro de la transacción para evitar cierre con cifras obsoletas.
    with conn:
     nuevos=conn.execute("SELECT id,fecha,tipo,medio,cantidad,total,estado_boleta,folio_dte FROM ventas WHERE substr(fecha,1,10)=? AND estado_boleta != 'ANULADA_PRUEBA' ORDER BY id",(fecha,)).fetchall()
     if nuevos!=rows:raise ValueError('Las operaciones cambiaron. Actualiza el resumen y vuelve a intentar.')
     conn.execute('INSERT INTO cierres_caja(fecha,creado,efectivo_esperado,efectivo_contado,diferencia,webpay,tarjeta,total,personas,ventas,desglose_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
      (fecha,datetime.now().isoformat(timespec='seconds'),medios['Efectivo'],efectivo,diferencia,medios['Webpay'],medios['Tarjeta'],total,personas,ventas,json.dumps(tipos,ensure_ascii=False)))
     conn.executemany('INSERT INTO cierre_operaciones(fecha_cierre,venta_id,fecha_venta,tipo,medio,cantidad,total,estado_boleta,folio_dte) VALUES (?,?,?,?,?,?,?,?,?)',
      [(fecha,r[0],r[1],r[2],r[3],r[4],r[5],r[6],r[7]) for r in rows])
    refrescar()
    self._aviso_cierre_fecha=None
    if messagebox.askyesno('Cierre guardado',f'Cierre de {fecha} guardado con {len(rows)} operaciones.\nRespaldo: {backup.name}\n\n¿Imprimir ahora en la impresora térmica?',parent=win):
     self.imprimir_cierre_termico(fecha)
   except (sqlite3.Error,OSError,ValueError) as exc:
    messagebox.showerror('Error de cierre',str(exc),parent=win)
  def imprimir_resumen():
   self.imprimir_cierre_termico(fecha,preliminar=not bool(conn.execute('SELECT 1 FROM cierres_caja WHERE fecha=?',(fecha,)).fetchone()))
  refrescar()
  self.boton_color(win,'ACTUALIZAR RESUMEN',refrescar,'#176B87',size=11).pack(fill='x',padx=18,pady=4)
  self.boton_color(win,'IMPRIMIR RESUMEN · SIN CERRAR',imprimir_resumen,'#176B87',size=11).pack(fill='x',padx=18,pady=4)
  self.boton_color(win,'CERRAR CAJA · AUTORIZACIÓN SUPERVISOR',cerrar,'#8B4A25',size=11).pack(fill='x',padx=18,pady=(4,16))

 def historial_cierres(self):
  """Consulta inmutable de cierres anteriores, con autorización de supervisor."""
  if not self.autorizar_supervisor():return
  from reportes_cierre import generar_reporte_cierre
  import webbrowser
  win=tk.Toplevel(self);win.title('ROMERAL | Historial de cierres');win.geometry('1060x640')
  win.configure(bg='#f1f6fc')
  tk.Label(win,text='HISTORIAL DE CIERRES DE CAJA',bg='#f1f6fc',fg='#082e56',font=('Arial',20,'bold')).pack(pady=(18,6))
  tk.Label(win,text='Consulta de registros guardados · No permite modificar ni eliminar cierres',bg='#f1f6fc',fg='#744300',font=('Arial',11,'bold')).pack(pady=(0,10))
  columns=('fecha','registrado','ventas','personas','total','esperado','contado','diferencia')
  cont=tk.Frame(win,bg='#f1f6fc');cont.pack(fill='both',expand=True,padx=16,pady=6)
  style=ttk.Style(win)
  style.configure('Cierres.Treeview',background='#ffffff',foreground='#10294c',fieldbackground='#ffffff',rowheight=30,font=('Arial',11))
  style.map('Cierres.Treeview',foreground=[('selected','#ffffff')],background=[('selected','#176B87')])
  tabla=ttk.Treeview(cont,columns=columns,show='headings',selectmode='browse',style='Cierres.Treeview')
  for key,label,width in zip(columns,('Fecha','Registrado','Ventas','Personas','Total','Ef. esperado','Ef. contado','Diferencia'),(110,170,75,85,120,120,120,120)):
   tabla.heading(key,text=label);tabla.column(key,width=width,anchor='center',stretch=True)
  scroll=ttk.Scrollbar(cont,orient='vertical',command=tabla.yview)
  tabla.configure(yscrollcommand=scroll.set)
  tabla.pack(side='left',fill='both',expand=True)
  scroll.pack(side='right',fill='y')
  estado=tk.StringVar(value='')
  tk.Label(win,textvariable=estado,bg='#f1f6fc',fg='#10294c',font=('Arial',11)).pack(pady=5)
  def refrescar():
   for item in tabla.get_children():tabla.delete(item)
   filas=conn.execute('SELECT fecha,creado,ventas,personas,total,efectivo_esperado,efectivo_contado,diferencia FROM cierres_caja ORDER BY fecha DESC').fetchall()
   for r in filas:
    tabla.insert('','end',iid=r[0],values=(r[0],r[1],r[2],r[3],pesos(r[4]),pesos(r[5]),pesos(r[6]),pesos(r[7])),tags=('diferencia',) if r[7] else ())
   tabla.tag_configure('diferencia',background='#fff0d5',foreground='#633500')
   estado.set(f'Cierres guardados: {len(filas)} · Los datos son históricos y no se recalculan')
  def reporte():
   sel=tabla.selection()
   if not sel:
    messagebox.showwarning('Selecciona un cierre','Selecciona una fecha de la tabla.',parent=win);return
   fecha=sel[0]
   r=conn.execute('SELECT fecha,creado,efectivo_esperado,efectivo_contado,diferencia,webpay,tarjeta,total,personas,ventas,desglose_json FROM cierres_caja WHERE fecha=?',(fecha,)).fetchone()
   if not r:
    messagebox.showerror('No encontrado','El cierre seleccionado ya no está disponible.',parent=win);return
   try:
    destino=generar_reporte_cierre(r,APP_DIR/'cierres')
    webbrowser.open(destino.as_uri())
   except (OSError,ValueError,KeyError,TypeError) as exc:
    messagebox.showerror('Reporte',f'No se pudo generar el reporte: {type(exc).__name__}',parent=win)
  refrescar()
  fila=tk.Frame(win,bg='#f1f6fc');fila.pack(fill='x',padx=16,pady=(4,16))
  self.boton_color(fila,'ACTUALIZAR HISTORIAL',refrescar,'#176B87',size=11).pack(side='left',fill='x',expand=True,padx=4)
  self.boton_color(fila,'VER REPORTE HTML',reporte,'#285d78',size=11).pack(side='left',fill='x',expand=True,padx=4)
  self.boton_color(fila,'REIMPRIMIR 80 MM',lambda: self.imprimir_cierre_termico(tabla.selection()[0]) if tabla.selection() else messagebox.showwarning('Selecciona un cierre','Selecciona una fecha.',parent=win),'#176B87',size=11).pack(side='left',fill='x',expand=True,padx=4)

 def panel_control_dte(self):
  """Panel de conciliación local, estrictamente de lectura. Nunca transmite DTE."""
  win=tk.Toplevel(self);win.title('ROMERAL | Control de boletas DTE 39 · solo lectura')
  win.geometry('1120x680');win.minsize(950,530);win.configure(bg='#f1f6fc')
  tk.Label(win,text='CONTROL DE BOLETAS ELECTRÓNICAS · DTE 39',bg='#f1f6fc',fg='#082e56',font=('Arial',19,'bold')).pack(pady=(16,4))
  tk.Label(win,text='SOLO LECTURA · Emisión bloqueada · Sin envío a Facturacion.com',bg='#f1f6fc',fg='#854900',font=('Arial',12,'bold')).pack(pady=(0,10))
  estado=tk.StringVar();tk.Label(win,textvariable=estado,bg='white',fg='#10294c',font=('Arial',12,'bold'),justify='left',anchor='w',padx=14,pady=12).pack(fill='x',padx=18,pady=(0,8))
  cols=('id','fecha','tipo','personas','total','pago','estado','folio','alerta')
  style=ttk.Style(win)
  style.configure('ControlDTE.Treeview',background='#ffffff',foreground='#10294c',fieldbackground='#ffffff',rowheight=30,font=('Arial',11))
  style.configure('ControlDTE.Treeview.Heading',font=('Arial',11,'bold'))
  style.map('ControlDTE.Treeview',foreground=[('selected','#ffffff')],background=[('selected','#176B87')])
  tree=ttk.Treeview(win,columns=cols,show='headings',selectmode='browse',style='ControlDTE.Treeview')
  for c,t,w in zip(cols,('ID','Fecha','Servicio','Pers.','Total','Pago','Estado interno','Folio','Revisión'),(50,140,125,55,95,90,165,75,240)):
   tree.heading(c,text=t);tree.column(c,width=w,anchor='center')
  tree.pack(fill='both',expand=True,padx=18,pady=8)
  tree.tag_configure('alerta',background='#fff0d5',foreground='#633500')
  tree.tag_configure('anulada',background='#edf1f6',foreground='#526276')
  tk.Label(win,text='Una venta pendiente no está emitida. Una marca local EMITIDA no acredita por sí sola aceptación del SII.',bg='#f1f6fc',fg='#38485a',font=('Arial',10)).pack(pady=4)
  def actualizar():
   from registro_intentos_soap import crear_tabla as crear_intentos
   crear_intentos(conn)
   for item in tree.get_children():tree.delete(item)
   rows=conn.execute("""SELECT id,fecha,tipo,cantidad,total,medio,estado_boleta,folio_dte,fecha_emision,ultimo_error_emision
      FROM ventas ORDER BY id DESC LIMIT 2000""").fetchall()
   pendientes=anuladas=marcadas=revision=0
   for r in rows:
    vid,fecha,tipo,n,total,medio,est,folio,emision,error=r
    est=est or 'SIN_ESTADO'
    if est=='ANULADA_PRUEBA':
     anuladas+=1;alerta='Excluida de emisión';tag='anulada'
     if folio or emision:alerta='ALERTA: anulada con datos DTE';revision+=1;tag='alerta'
    elif est=='PENDIENTE_INTEGRACION':
     pendientes+=1
     if folio or emision:alerta='ALERTA: pendiente con datos DTE';revision+=1;tag='alerta'
     else:alerta='Pendiente, no transmitida';tag=''
    elif est=='EMITIDA':
     marcadas+=1
     # La confirmación SOAP local es distinta de la aceptación tributaria del SII.
     # Solo presentar evidencia confirmada si coinciden venta y folio en ambos registros.
     prueba=conn.execute('''SELECT c.estado,c.folio,i.estado,i.folio,i.sha256_respuesta
       FROM control_emision c LEFT JOIN intentos_soap_dte i ON i.venta_id=c.venta_id
       WHERE c.venta_id=?''',(vid,)).fetchone()
     coincide=(bool(folio) and prueba is not None and prueba[0]=='EMITIDA'
       and str(prueba[1])==str(folio) and prueba[2]=='CONFIRMADO'
       and str(prueba[3])==str(folio) and bool(prueba[4]))
     if coincide:
      alerta='SOAP confirmado · verificar SII';tag=''
     else:
      revision+=1;alerta='Revisar evidencia del proveedor';tag='alerta'
      if not folio:alerta='ALERTA: emitida sin folio'
    else:
     revision+=1;alerta='Revisión manual obligatoria';tag='alerta'
    if error and est!='ANULADA_PRUEBA':alerta='Revisar error / estado';tag='alerta'
    tree.insert('','end',values=(vid,str(fecha).replace('T',' '),nombre_visible(tipo),n,pesos(total),medio,est,folio or '—',alerta),tags=(tag,) if tag else ())
   estado.set(f'Pendientes sin confirmar: {pendientes}    |    Marcadas emitidas: {marcadas}    |    Anuladas de prueba: {anuladas}    |    Casos a revisar: {revision}\nNo se modifica ningún registro ni se asignan folios.')
  def previsualizar_dte():
   seleccion=tree.selection()
   if not seleccion:
    messagebox.showwarning('Selecciona una venta','Selecciona una venta pendiente de la tabla.',parent=win);return
   vid=int(tree.item(seleccion[0],'values')[0])
   r=conn.execute('SELECT id,fecha,tipo,cantidad,total,medio,estado_boleta,folio_dte,fecha_emision,referencia_venta,ultimo_error_emision FROM ventas WHERE id=?',(vid,)).fetchone()
   if not r or r[6]!='PENDIENTE_INTEGRACION' or r[7] or r[8] or r[10]:
    messagebox.showwarning('No elegible','Solo se puede preparar una vista previa de ventas pendientes sin indicios de emisión ni error.',parent=win);return
   if not r[9]:
    messagebox.showwarning('Referencia faltante','Esta venta histórica no tiene referencia única. No se modificó el registro.',parent=win);return
   try:
    from integracion_facturacion import VentaBoleta, generar_txt
    tipo=nombre_visible(r[2])
    texto=generar_txt(VentaBoleta(referencia=r[9],tipo=tipo,personas=int(r[3]),total=int(r[4]),medio=r[5],fecha=r[1][:10]))
   except Exception as exc:
    messagebox.showerror('No se pudo preparar',f'Datos no válidos para la vista previa: {type(exc).__name__}',parent=win);return
   popup=tk.Toplevel(win);popup.title(f'ROMERAL | DTE 39 preliminar · venta {vid}');popup.geometry('800x620')
   tk.Label(popup,text='BORRADOR LOCAL · NO EMITIDO · NO TRANSMITIR SIN VALIDACIÓN',fg='#854900',font=('Arial',12,'bold')).pack(pady=12)
   tk.Label(popup,text='La estructura TXT es preliminar y debe ser validada con Facturacion.com antes de su uso.',fg='#10294c',font=('Arial',11)).pack(pady=3)
   area=tk.Text(popup,wrap='none',font=('Courier',11));area.insert('1.0',texto);area.configure(state='disabled')
   area.pack(fill='both',expand=True,padx=12,pady=12)
  def exportar_control():
   ruta=filedialog.asksaveasfilename(parent=win,defaultextension='.csv',filetypes=[('CSV','*.csv')],initialfile='ROMERAL_control_DTE_'+datetime.now().strftime('%Y%m%d')+'.csv')
   if not ruta:return
   try:
    filas=conn.execute('SELECT id,fecha,tipo,cantidad,total,medio,estado_boleta,folio_dte,fecha_emision,referencia_venta FROM ventas ORDER BY id').fetchall()
    with open(ruta,'w',encoding='utf-8-sig',newline='') as archivo:
     writer=csv.writer(archivo,delimiter=';')
     writer.writerow(['ID','Fecha','Servicio','Personas','Total CLP','Medio','Estado interno','Folio local','Fecha emisión local','Referencia única'])
     writer.writerows(filas)
    messagebox.showinfo('Exportación','Informe local guardado. No se envió información al proveedor.',parent=win)
   except OSError as exc:
    messagebox.showerror('Exportación',str(exc),parent=win)
  acciones=tk.Frame(win,bg='#f1f6fc');acciones.pack(fill='x',padx=18,pady=(5,15))
  self.boton_color(acciones,'VISTA PREVIA TXT · NO EMITIR',previsualizar_dte,'#285d78',size=11).pack(side='left',fill='x',expand=True,padx=3)
  self.boton_color(acciones,'EXPORTAR CONTROL CSV',exportar_control,'#285d78',size=11).pack(side='left',fill='x',expand=True,padx=3)
  self.boton_color(win,'ACTUALIZAR CONTROL DTE · SOLO LECTURA',actualizar,'#176B87',size=12).pack(fill='x',padx=18,pady=(0,8))
  actualizar()

 def panel_comprobantes(self):
  import webbrowser
  win=tk.Toplevel(self);win.title('ROMERAL | Comprobantes internos 80 mm')
  win.geometry('980x650');win.configure(bg='#f1f6fc')
  tk.Label(win,text='COMPROBANTES INTERNOS · 80 MM',bg='#f1f6fc',fg='#082e56',font=('Arial',19,'bold')).pack(pady=(18,5))
  tk.Label(win,text='NO SON BOLETAS ELECTRÓNICAS NI DOCUMENTOS TRIBUTARIOS',bg='#f1f6fc',fg='#8b4513',font=('Arial',11,'bold')).pack(pady=(0,10))
  rut_estado=tk.StringVar(value='RUT configurado: '+(config('rut_empresa') or 'PENDIENTE'))
  tk.Label(win,textvariable=rut_estado,bg='#f1f6fc',fg='#10294c',font=('Arial',12,'bold')).pack(pady=3)
  def configurar_rut():
   if not self.autorizar_supervisor():return
   entrada=simpledialog.askstring('RUT de VALLE DE ROMERAL SPA','Ingresa el RUT real de la empresa (con dígito verificador):',parent=win,initialvalue=config('rut_empresa') or '')
   if entrada is None:return
   rut=validar_rut(entrada)
   if not rut:
    messagebox.showerror('RUT inválido','El RUT no tiene formato o dígito verificador válido. No se guardó.',parent=win);return
   with conn:conn.execute('INSERT OR REPLACE INTO config(key,value) VALUES (?,?)',('rut_empresa',rut))
   rut_estado.set('RUT configurado: '+rut)
   messagebox.showinfo('RUT guardado','RUT de empresa configurado para comprobantes internos.',parent=win)
  self.boton_color(win,'CONFIGURAR RUT EMPRESA · SUPERVISOR',configurar_rut,'#285d78',size=11).pack(fill='x',padx=18,pady=3)
  cols=('id','fecha','tipo','personas','total','medio','estado')
  tabla=ttk.Treeview(win,columns=cols,show='headings',selectmode='browse')
  for c,t,w in zip(cols,('N°','Fecha','Modalidad','Personas','Total','Pago','Estado DTE'),(55,145,150,80,100,100,180)):
   tabla.heading(c,text=t);tabla.column(c,width=w,anchor='center')
  for r in conn.execute("SELECT id,fecha,tipo,cantidad,total,medio,estado_boleta FROM ventas WHERE estado_boleta != 'ANULADA_PRUEBA' ORDER BY id DESC LIMIT 500"):
   tabla.insert('', 'end',iid=str(r[0]),values=(r[0],r[1].replace('T',' '),nombre_visible(r[2]),r[3],pesos(r[4]),r[5],r[6]))
  tabla.pack(fill='both',expand=True,padx=18,pady=10)
  def imprimir():
   sel=tabla.selection()
   if not sel:
    messagebox.showwarning('Selecciona una venta','Selecciona una venta de la tabla.',parent=win);return
   r=conn.execute("SELECT id,fecha,tipo,cantidad,total,medio,estado_boleta,folio_dte,fecha_emision FROM ventas WHERE id=?",(int(sel[0]),)).fetchone()
   if not r or r[6]=='ANULADA_PRUEBA':
    messagebox.showerror('No disponible','La venta no está disponible.',parent=win);return
   try:
    destino=crear_comprobante_html(r,APP_DIR/'comprobantes',config('rut_empresa'))
    webbrowser.open(destino.as_uri())
    messagebox.showinfo('Vista previa 80 mm','Se abrió el comprobante INTERNO en el navegador.\\nUsa Archivo > Imprimir y selecciona tu impresora de 80 mm.\\nDesactiva encabezados y pies de página.\\n\\nNO es una boleta electrónica.',parent=win)
   except (OSError,ValueError) as exc:
    messagebox.showerror('Error',str(exc),parent=win)
  def ejemplo():
   # No insertar en SQLite ni usar una venta real.
   try:
    from datetime import datetime
    import tempfile
    muestra=('EJEMPLO',datetime.now().isoformat(timespec='seconds'),'Entrada General',1,10000,'Efectivo','SIMULACIÓN',None,None)
    with tempfile.TemporaryDirectory(prefix='romeral_ejemplo_') as tmp:
     ruta=crear_comprobante_html(muestra,Path(tmp),config('rut_empresa'))
     # Abrir archivo persistente temporal, pues el navegador carga asincrónicamente.
     import shutil
     destino=Path(tempfile.gettempdir())/'ROMERAL_vista_previa_ejemplo_80mm.html'
     shutil.copyfile(ruta,destino)
    webbrowser.open(destino.as_uri())
   except (OSError,ValueError) as exc:
    messagebox.showerror('Vista previa',str(exc),parent=win)
  self.boton_color(win,'VER EJEMPLO FICTICIO $10.000 · SIN REGISTRAR VENTA',ejemplo,'#285d78',size=12).pack(fill='x',padx=18,pady=(4,4))
  self.boton_color(win,'PREVISUALIZAR / IMPRIMIR COMPROBANTE INTERNO',imprimir,'#176B87',size=12).pack(fill='x',padx=18,pady=(4,18))

 def anular_pruebas(self):
  """Anula solo las cuatro ventas pendientes seleccionadas; copia SQLite consistente."""
  rows=conn.execute("SELECT id,fecha,tipo,cantidad,total,medio,estado_boleta,folio_dte,fecha_emision FROM ventas WHERE estado_boleta <> 'ANULADA_PRUEBA' ORDER BY id").fetchall()
  if not rows:
   messagebox.showinfo('Sin ventas activas','No hay ventas activas para anular.',parent=self);return
  # Solo ofrecer ventas locales pendientes, sin evidencia de emisión.
  elegibles=[r for r in rows if r[6]=='PENDIENTE_INTEGRACION' and not r[7] and not r[8]]
  win=tk.Toplevel(self);win.title('ROMERAL | Anulación interna de pruebas');win.geometry('1060x650');win.minsize(900,560)
  win.configure(bg='#f0f5fb')
  tk.Label(win,text='ANULACIÓN DE VENTAS DE PRUEBA',font=('Arial',20,'bold'),bg='#f0f5fb',fg='#10294c').pack(pady=(18,4))
  tk.Label(win,text='Marca las casillas de EXACTAMENTE 4 ventas. Solo registros pendientes, sin folio ni emisión.',font=('Arial',12),bg='#f0f5fb',fg='#334155').pack(pady=(0,12))
  listado=tk.Frame(win,bg='white');listado.pack(fill='both',expand=True,padx=22,pady=5)
  cab=tk.Frame(listado,bg='#12395f');cab.pack(fill='x')
  for texto,ancho in [('Marcar',8),('ID',5),('Fecha',19),('Tipo',20),('Personas',9),('Total',13),('Pago',12)]:
   tk.Label(cab,text=texto,width=ancho,bg='#12395f',fg='white',font=('Arial',11,'bold'),anchor='w',padx=5,pady=12).pack(side='left')
  canvas=tk.Canvas(listado,bg='white',highlightthickness=0)
  scroll=tk.Scrollbar(listado,orient='vertical',command=canvas.yview)
  inner=tk.Frame(canvas,bg='white')
  inner.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
  canvas.create_window((0,0),window=inner,anchor='nw')
  canvas.configure(yscrollcommand=scroll.set)
  canvas.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y')
  checks={}
  contador=tk.StringVar(value='Seleccionadas: 0 de 4')
  def actualizar_contador(*_):
   contador.set(f'Seleccionadas: {sum(v.get() for v in checks.values())} de 4')
  for i,r in enumerate(elegibles):
   linea=tk.Frame(inner,bg='#ffffff' if i%2==0 else '#eaf1fa');linea.pack(fill='x')
   variable=tk.BooleanVar(value=False);checks[r[0]]=variable
   variable.trace_add('write',actualizar_contador)
   tk.Checkbutton(linea,variable=variable,bg=linea['bg'],activebackground=linea['bg'],width=8,anchor='w',font=('Arial',18),cursor='hand2').pack(side='left')
   for valor,ancho in [(r[0],5),(r[1].replace('T',' '),19),(nombre_visible(r[2]),20),(r[3],9),(pesos(r[4]),13),(r[5],12)]:
    tk.Label(linea,text=str(valor),width=ancho,bg=linea['bg'],fg='#10294c',anchor='w',font=('Arial',11),padx=5,pady=11).pack(side='left')
  tk.Label(win,textvariable=contador,font=('Arial',15,'bold'),bg='#f0f5fb',fg='#10294c').pack(pady=8)
  if not elegibles:
   tk.Label(win,text='No hay ventas pendientes elegibles para anulación.',bg='#f0f5fb',fg='#a33',font=('Arial',13)).pack()
  def ejecutar():
   ids=[int(vid) for vid,variable in checks.items() if variable.get()]
   if len(ids)!=4:
    messagebox.showwarning('Selección','Selecciona exactamente las cuatro ventas de prueba.',parent=win);return
   placeholders=','.join('?' for _ in ids)
   actual=conn.execute(f'SELECT id,estado_boleta,folio_dte,fecha_emision FROM ventas WHERE id IN ({placeholders})',ids).fetchall()
   if len(actual)!=4 or any(r[1]!='PENDIENTE_INTEGRACION' or r[2] or r[3] for r in actual):
    messagebox.showerror('Operación bloqueada','Alguna venta no está pendiente o tiene datos de emisión. No se modificó nada.',parent=win);return
   if not self.autorizar_supervisor():return
   if not messagebox.askyesno('Confirmar anulación interna','Se anularán únicamente estas cuatro ventas de prueba.\nSe conservarán en el historial.\nSe creará una copia de seguridad antes de guardar.\n\n¿Confirmas?',parent=win):return
   backup=APP_DIR / ('romeral_ANTES_ANULACION_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.sqlite3')
   try:
    # SQLite backup API incluye cambios aún alojados en el WAL.
    with sqlite3.connect(backup) as copia:conn.backup(copia)
    with conn:
     for vid in ids:
      result=conn.execute("UPDATE ventas SET estado_boleta='ANULADA_PRUEBA' WHERE id=? AND estado_boleta='PENDIENTE_INTEGRACION' AND (folio_dte IS NULL OR folio_dte='') AND fecha_emision IS NULL",(vid,))
      if result.rowcount!=1:raise RuntimeError('Cambio inesperado de estado. Operación revertida.')
      conn.execute('INSERT INTO eventos_dte(venta_id,fecha,evento,detalle) VALUES (?,?,?,?)',(vid,datetime.now().isoformat(timespec='seconds'),'ANULACION_PRUEBA','Anulación interna autorizada por supervisor; sin emisión tributaria'))
    self.actualizar_resumen();win.destroy()
    messagebox.showinfo('Anulación terminada',f'4 ventas marcadas ANULADA_PRUEBA.\nCopia de seguridad: {backup}\nNo se transmitió información al SII.',parent=self)
   except Exception as exc:
    messagebox.showerror('No se pudo anular',f'No se completó la anulación: {exc}',parent=win)
  boton=self.boton_color(win,'ANULAR LAS 4 MARCADAS (CON RESPALDO)',ejecutar,'#8B4A25',size=14)
  boton.pack(fill='x',padx=22,pady=(4,18))

 def historial(self):
  win=tk.Toplevel(self);win.title('ROMERAL - Historial de ventas e ingresos');win.geometry('1200x530')
  tk.Label(win,text='La hora de venta corresponde al ingreso inmediato del cliente. La hora de emisión DTE puede ser distinta.',font=('Arial',11),anchor='w').pack(fill='x',padx=12,pady=(10,0))
  cols=('id','fecha','hora','tipo','cantidad','precio','total','medio','boleta','folio','emision')
  tree=ttk.Treeview(win,columns=cols,show='headings')
  titulos=('N°','Fecha ingreso','Hora ingreso','Tipo','Personas','Precio','Total','Pago','Estado boleta','Folio','Fecha/hora DTE')
  anchos=(50,105,100,140,75,90,95,90,165,85,160)
  for c,titulo,ancho in zip(cols,titulos,anchos):
   tree.heading(c,text=titulo);tree.column(c,width=ancho,anchor='center')
  for r in conn.execute('SELECT id,fecha,tipo,cantidad,precio,total,medio,estado_boleta,folio_dte,fecha_emision FROM ventas ORDER BY id DESC LIMIT 2000'):
   fecha_ingreso=(r[1] or '').replace('T',' ')
   partes=fecha_ingreso.split(' ',1)
   dia=partes[0] if partes else '—'
   hora=partes[1] if len(partes)>1 else 'No registrada'
   tree.insert('', 'end',values=(r[0],dia,hora,nombre_visible(r[2]),r[3],pesos(r[4]) if r[4] else ('Manual (versión anterior)' if r[2] in ('Alojamiento','Cabañas','Camping') else pesos(r[4])),pesos(r[5]),r[6],r[7],r[8] or '—',(r[9] or '—').replace('T',' ')))
  tree.pack(fill='both',expand=True,padx=12,pady=12)
 def exportar(self):
  path=filedialog.asksaveasfilename(defaultextension='.csv',filetypes=[('CSV','*.csv')],initialfile=f'ROMERAL_ventas_{datetime.now():%Y%m%d}.csv')
  if not path:return
  try:
   with open(path,'w',newline='',encoding='utf-8-sig') as f:
    writer=csv.writer(f,delimiter=';');writer.writerow(['ID','Fecha','Tipo','Personas','Precio unitario CLP','Total CLP','Medio de pago','Estado boleta','Folio DTE','Referencia venta'])
    writer.writerows((r[0],r[1],nombre_visible(r[2]),*r[3:]) for r in conn.execute('SELECT id,fecha,tipo,cantidad,precio,total,medio,estado_boleta,folio_dte,referencia_venta FROM ventas ORDER BY id'))
   messagebox.showinfo('Exportación lista','Archivo CSV guardado correctamente.')
  except OSError as e:messagebox.showerror('Error',str(e))

if __name__=='__main__':
 try:Romeral().mainloop()
 finally:conn.close()
