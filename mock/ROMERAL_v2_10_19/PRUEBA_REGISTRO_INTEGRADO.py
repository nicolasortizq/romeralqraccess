"""Pruebas de integración con SQLite temporal: no toca ROMERAL_Datos."""
import sqlite3
import unittest
from registro_dte import crear_tabla, registrar_venta, resumen
class Pruebas(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:')
  self.db.execute('CREATE TABLE ventas (id INTEGER PRIMARY KEY, referencia_venta TEXT, estado_boleta TEXT)')
  crear_tabla(self.db)
 def tearDown(self): self.db.close()
 def agregar(self,ident=1,estado='PENDIENTE_INTEGRACION'):
  self.db.execute('INSERT INTO ventas VALUES (?,?,?)',(ident,'ref-'+str(ident),estado))
 def test_registro_unico(self):
  self.agregar();registrar_venta(self.db,1,'ref-1');self.assertEqual(resumen(self.db),[('PENDIENTE_INTEGRACION',1)])
  with self.assertRaises(sqlite3.IntegrityError): registrar_venta(self.db,1,'ref-1')
 def test_no_registra_anulada(self):
  self.agregar(1,'ANULADA_PRUEBA')
  with self.assertRaises(ValueError): registrar_venta(self.db,1,'ref-1')
 def test_no_registra_referencia_ajena(self):
  self.agregar()
  with self.assertRaises(ValueError): registrar_venta(self.db,1,'otra')
 def test_rollback_atomico(self):
  with self.assertRaises(RuntimeError):
   with self.db:
    self.agregar();registrar_venta(self.db,1,'ref-1');raise RuntimeError('simulación')
  self.assertEqual(self.db.execute('SELECT COUNT(*) FROM ventas').fetchone()[0],0)
  self.assertEqual(self.db.execute('SELECT COUNT(*) FROM control_emision').fetchone()[0],0)
 def test_no_envio(self):
  import inspect,registro_dte
  self.assertNotIn('Procesar(',inspect.getsource(registro_dte))
 def test_no_folios_inventados(self):
  self.agregar();registrar_venta(self.db,1,'ref-1')
  self.assertIsNone(self.db.execute('SELECT folio FROM control_emision').fetchone()[0])
if __name__=='__main__':
 print('Pruebas SQLite temporal; sin conexión de red ni boletas reales')
 unittest.main(verbosity=2)
