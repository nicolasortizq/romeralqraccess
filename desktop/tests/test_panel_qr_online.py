"""Tests for canje_online.CanjeOnlineController, the online-ticket redeem logic
behind romeral.py's panel_qr_online() screen.

`app` is never a real `Romeral` Tkinter instance here: it is a plain mock
duck-typed to the few attributes/methods the controller actually calls
(`verificar_condiciones_emision`, `emision_en_curso`, `terminal_nombre`,
`operador_actual`, `registrar_venta_online`, `emitir_automaticamente`,
`consultar_resultado_emision`, `after`). `app.after` runs its callback
immediately (synchronously) instead of scheduling it on a Tkinter event
loop, which is what lets the polling in `_esperar_resultado_y_reportar`
resolve within a single test call.
"""
from unittest.mock import MagicMock

import pytest

import canje_online
from canje_online import CanjeOnlineController
from ventas_online import TicketAlreadyRedeemedError


@pytest.fixture
def mock_app():
    app = MagicMock()
    app.verificar_condiciones_emision.return_value = True
    app.emision_en_curso = False
    app.terminal_nombre = 'acceso-1'
    app.operador_actual = 'jperez'
    app.registrar_venta_online.return_value = 501
    app.consultar_resultado_emision.return_value = (None, 'PENDIENTE_INTEGRACION')
    app.after = lambda ms, fn: fn()
    return app


@pytest.fixture
def mock_app_with_failed_precondition(mock_app):
    mock_app.verificar_condiciones_emision.return_value = False
    return mock_app


@pytest.fixture
def mock_ventas_online(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr(canje_online, 'ventas_online', mock)
    return mock


def test_canje_blocked_when_preconditions_fail(mock_app_with_failed_precondition):
    controller = CanjeOnlineController(mock_app_with_failed_precondition)
    assert controller.puede_canjear() is False


def test_canje_calls_emitir_automaticamente_on_successful_redeem(mock_app, mock_ventas_online):
    mock_ventas_online.redeem_ticket.return_value = {"status": "REDEEMED", "total_paid": 12000}
    controller = CanjeOnlineController(mock_app)
    controller.canjear("VR1ABC")
    mock_app.emitir_automaticamente.assert_called_once()


def test_canje_reports_invoice_result_back_to_backend(mock_app, mock_ventas_online):
    mock_ventas_online.redeem_ticket.return_value = {"status": "REDEEMED", "total_paid": 12000}
    controller = CanjeOnlineController(mock_app)
    controller.canjear("VR1ABC")
    mock_ventas_online.report_invoice.assert_called_once()


def test_canje_reports_pending_review_without_folio_when_emission_unresolved(mock_app, mock_ventas_online):
    mock_ventas_online.redeem_ticket.return_value = {"status": "REDEEMED", "total_paid": 12000}
    mock_app.consultar_resultado_emision.return_value = (None, 'PENDIENTE_INTEGRACION')
    controller = CanjeOnlineController(mock_app)
    controller.canjear("VR1ABC")
    mock_ventas_online.report_invoice.assert_called_once_with(
        "VR1ABC", status='PENDING_REVIEW', folio=None)


def test_canje_reports_issued_with_folio_on_confirmed_emission(mock_app, mock_ventas_online):
    mock_ventas_online.redeem_ticket.return_value = {"status": "REDEEMED", "total_paid": 12000}
    mock_app.consultar_resultado_emision.return_value = ('26193', 'EMITIDA')
    controller = CanjeOnlineController(mock_app)
    controller.canjear("VR1ABC")
    mock_ventas_online.report_invoice.assert_called_once_with(
        "VR1ABC", status='ISSUED', folio='26193')


def test_canje_shows_already_redeemed_message(mock_app, mock_ventas_online):
    mock_ventas_online.redeem_ticket.side_effect = TicketAlreadyRedeemedError("Entrada ya canjeada")
    controller = CanjeOnlineController(mock_app)
    assert "ya canjeada" in controller.canjear("VR1ABC").lower()


def test_canje_blocked_when_emission_already_in_progress(mock_app, mock_ventas_online):
    mock_app.emision_en_curso = True
    controller = CanjeOnlineController(mock_app)
    mensaje = controller.canjear("VR1ABC")
    mock_ventas_online.redeem_ticket.assert_not_called()
    assert 'emisión' in mensaje.lower() or 'boleta anterior' in mensaje.lower()
