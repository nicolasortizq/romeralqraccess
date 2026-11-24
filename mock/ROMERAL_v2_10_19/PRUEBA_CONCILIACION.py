"""Pruebas sin red, sin datos reales, sin credenciales."""
import sqlite3,unittest
from registro_dte import crear_tabla,registrar_venta
from conciliacion_dte import preparar,reservar,marcar_incierta,enviar_revision,confirmar_respuesta_verificada,consultar
class Conciliacion(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:')
  self.db.execute('CREATE TABLE ventas (id INTEGER PRIMARY KEY,referencia_venta TEXT,estado_boleta TEXT,folio_dte TEXT,fecha_emision TEXT)')
  crear_tabla(self.db);preparar(self.db)
  for i in (1,2):
   self.db.execute('INSERT INTO ventas (id,referencia_venta,estado_boleta) VALUES (?,?,?)',(i,f'ref-{i}','PENDIENTE_INTEGRACION'))
   registrar_venta(self.db,i,f'ref-{i}')
 def tearDown(self):self.db.close()
 def test_estado_inicial(self):self.assertEqual(len(consultar(self.db)),2)
 def test_reserva(self):self.assertEqual(reservar(self.db,1,'test local'),'RESERVADA')
 def test_no_reserva_doble(self):
  reservar(self.db,1,'test')
  with self.assertRaises(ValueError):reservar(self.db,1,'test')
 def test_incierta(self):
  reservar(self.db,1,'test');marcar_incierta(self.db,1,'timeout')
  self.assertEqual(consultar(self.db)[1][2],'INCIERTA')
 def test_no_reenvio(self):
  reservar(self.db,1,'test');marcar_incierta(self.db,1,'timeout')
  with self.assertRaises(ValueError):reservar(self.db,1,'reintento')
 def test_revision(self):
  reservar(self.db,1,'test');marcar_incierta(self.db,1,'timeout');enviar_revision(self.db,1,'revisar proveedor')
 def test_no_emision_desde_pendiente(self):
  with self.assertRaises(ValueError):confirmar_respuesta_verificada(self.db,1,'100','evidencia')
 def test_no_folio_invalido(self):
  reservar(self.db,1,'test')
  with self.assertRaises(ValueError):confirmar_respuesta_verificada(self.db,1,'x','evidencia')
 def test_confirmacion_con_evidencia(self):
  reservar(self.db,1,'test');confirmar_respuesta_verificada(self.db,1,'100','respuesta externa validada')
  self.assertEqual(self.db.execute('SELECT estado_boleta,folio_dte FROM ventas WHERE id=1').fetchone(),('EMITIDA','100'))
 def test_confirmacion_inmutable(self):
  reservar(self.db,1,'test');confirmar_respuesta_verificada(self.db,1,'100','respuesta externa validada')
  with self.assertRaises(ValueError):confirmar_respuesta_verificada(self.db,1,'101','otra')
 def test_folio_no_repetido(self):
  reservar(self.db,1,'test');confirmar_respuesta_verificada(self.db,1,'100','respuesta externa validada')
  reservar(self.db,2,'test')
  with self.assertRaises(ValueError):confirmar_respuesta_verificada(self.db,2,'100','otra respuesta')
 def test_sin_evidencia(self):
  with self.assertRaises(ValueError):reservar(self.db,1,'')
 def test_sin_red_ni_procesar(self):
  import inspect,conciliacion_dte
  source=inspect.getsource(conciliacion_dte)
  self.assertNotIn('urllib',source);self.assertNotIn('requests.',source);self.assertNotIn('Procesar(',source)
if __name__=='__main__':
 print('ROMERAL conciliación local: base temporal, sin red, sin emisión real')
 unittest.main(verbosity=2)
