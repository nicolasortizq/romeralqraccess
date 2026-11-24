"""Registro local y validación preliminar de QR online.

No consulta pagos ni emite documentos tributarios. Para producción se requiere
API autenticada del comercio y conciliación con Facturacion.com.
"""
import hashlib
import sqlite3
from datetime import datetime

DDL = '''CREATE TABLE IF NOT EXISTS qr_online (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 qr_hash TEXT NOT NULL UNIQUE,
 qr_muestra TEXT NOT NULL,
 pedido TEXT,
 fecha_visita TEXT,
 cantidad INTEGER,
 monto INTEGER,
 estado TEXT NOT NULL DEFAULT 'PENDIENTE_VERIFICACION',
 pago_verificado INTEGER NOT NULL DEFAULT 0,
 documento_verificado INTEGER NOT NULL DEFAULT 0,
 folio_dte TEXT,
 venta_id INTEGER,
 fecha_registro TEXT NOT NULL,
 fecha_actualizacion TEXT NOT NULL,
 observaciones TEXT NOT NULL DEFAULT ''
)'''

def preparar(db):
 db.execute(DDL)
 db.execute('CREATE INDEX IF NOT EXISTS ix_qr_online_pedido ON qr_online(pedido)')
 db.commit()

def normalizar(valor):
 valor=(valor or '').strip()
 if not 4 <= len(valor) <= 1024 or any(ord(c)<32 for c in valor):
  raise ValueError('El código debe contener entre 4 y 1024 caracteres imprimibles.')
 return valor

def buscar(db, codigo):
 codigo=normalizar(codigo)
 huella=hashlib.sha256(codigo.encode('utf-8')).hexdigest()
 return db.execute('SELECT id,qr_muestra,pedido,fecha_visita,cantidad,monto,estado,pago_verificado,documento_verificado,folio_dte,fecha_registro FROM qr_online WHERE qr_hash=?',(huella,)).fetchone()

def registrar(db, codigo):
 codigo=normalizar(codigo)
 huella=hashlib.sha256(codigo.encode('utf-8')).hexdigest()
 ahora=datetime.now().isoformat(timespec='seconds')
 with db:
  db.execute('INSERT OR IGNORE INTO qr_online(qr_hash,qr_muestra,fecha_registro,fecha_actualizacion) VALUES (?,?,?,?)',
             (huella, codigo[:12]+'…' if len(codigo)>12 else codigo,ahora,ahora))
 return buscar(db,codigo)

def estadisticas(db):
 return db.execute('SELECT COUNT(*),SUM(CASE WHEN estado="PENDIENTE_VERIFICACION" THEN 1 ELSE 0 END) FROM qr_online').fetchone()
