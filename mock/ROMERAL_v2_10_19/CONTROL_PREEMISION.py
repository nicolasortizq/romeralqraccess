"""Control local de preemisión, sin red y sin acceso a la base de datos real."""
from dataclasses import dataclass
from enum import Enum
import sqlite3
import unittest
from integracion_facturacion import VentaBoleta, generar_txt, interpretar_resultado

class Estado(str, Enum):
    PENDIENTE = 'PENDIENTE'
    RESERVADA = 'RESERVADA'
    INCIERTA = 'INCIERTA'
    EMITIDA = 'EMITIDA'
    REVISAR = 'REVISAR'

class RegistroEmision:
    """Prototipo aislado de control transaccional; no está conectado a la caja."""
    def __init__(self, conexion):
        self.db = conexion
        self.db.execute('CREATE TABLE IF NOT EXISTS intentos (referencia TEXT PRIMARY KEY, estado TEXT NOT NULL, folio TEXT)')

    def reservar(self, referencia):
        if not referencia or not referencia.strip():
            raise ValueError('Referencia vacía')
        with self.db:
            cursor = self.db.execute('INSERT OR IGNORE INTO intentos(referencia, estado) VALUES (?, ?)', (referencia, Estado.RESERVADA.value))
        return cursor.rowcount == 1

    def marcar_incierta(self, referencia):
        with self.db:
            cur = self.db.execute('UPDATE intentos SET estado=? WHERE referencia=? AND estado=?', (Estado.INCIERTA.value, referencia, Estado.RESERVADA.value))
        return cur.rowcount == 1

    def confirmar(self, referencia, folio):
        if not str(folio).isdigit() or int(folio) < 1:
            raise ValueError('Folio inválido')
        with self.db:
            cur = self.db.execute('UPDATE intentos SET estado=?, folio=? WHERE referencia=? AND estado IN (?,?)', (Estado.EMITIDA.value, str(folio), referencia, Estado.RESERVADA.value, Estado.INCIERTA.value))
        return cur.rowcount == 1

class PruebasSeguridad(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.reg = RegistroEmision(self.db)
    def tearDown(self):
        self.db.close()
    def test_reserva_unica(self):
        self.assertTrue(self.reg.reservar('venta-1'))
        self.assertFalse(self.reg.reservar('venta-1'))
    def test_incierta_no_reenvio(self):
        self.reg.reservar('venta-2')
        self.assertTrue(self.reg.marcar_incierta('venta-2'))
        self.assertFalse(self.reg.reservar('venta-2'))
    def test_folio_valido(self):
        self.reg.reservar('venta-3')
        with self.assertRaises(ValueError): self.reg.confirmar('venta-3', '0')
        self.assertTrue(self.reg.confirmar('venta-3', '123'))
        self.assertFalse(self.reg.confirmar('venta-3', '124'))
    def test_referencia_vacia(self):
        with self.assertRaises(ValueError): self.reg.reservar('')
    def test_txt_sin_transmision(self):
        txt = generar_txt(VentaBoleta('local-1','Entrada General',2,20000,'Efectivo'))
        self.assertIn('->Boleta<-', txt)
        self.assertIn('20000', txt)
    def test_respuesta_no_confirmada(self):
        resultado = interpretar_resultado('<Respuesta><Resultado>false</Resultado></Respuesta>')
        self.assertFalse(resultado['confirmado'])
    def test_respuesta_ambigua(self):
        resultado = interpretar_resultado('<Respuesta><Resultado>true</Resultado></Respuesta>')
        self.assertFalse(resultado['confirmado'])
    def test_no_emision_en_codigo_control(self):
        import inspect
        fuente = inspect.getsource(RegistroEmision)
        self.assertNotIn('.Procesar(', fuente)

if __name__ == '__main__':
    print('ROMERAL - Control de preemisión aislado (sin red, sin ventas reales)')
    unittest.main(verbosity=2)
