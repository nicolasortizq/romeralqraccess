"""Tests for ventas_online.py, the HTTP client to the romeralQRAccess backend.

No real network call happens here: every request goes through the
`requests_mock` fixture (a pytest plugin) against the base URL the fake
`romeral.config()` in desktop/conftest.py returns.
"""
import pytest

from ventas_online import (
    TicketAlreadyRedeemedError,
    lookup_ticket,
    redeem_ticket,
    report_invoice,
    search_tickets,
)

BASE_URL = 'https://acceso.vallederomeral.cl'


def sample_ticket_response():
    return {
        'id': '9f8f3b2a-0000-4000-8000-000000000001',
        'woo_order_id': 10452,
        'woo_order_number': '10452',
        'buyer_name': 'María Pérez',
        'buyer_email': 'maria.perez@example.com',
        'people_count': 3,
        'total_paid': 36000,
        'payment_method': 'Webpay',
        'purchased_at': '2026-11-20T15:00:00-03:00',
        'season_id': 1,
        'valid_until': '2027-03-31',
        'status': 'VALID',
        'redeemed_at': None,
        'redeemed_by': None,
        'invoice_status': 'NOT_ISSUED',
        'invoice_folio': None,
        'source': 'WEBHOOK',
        'created_at': '2026-11-20T15:00:01-03:00',
        'updated_at': '2026-11-20T15:00:01-03:00',
        'lines': [
            {
                'woo_product_id': 142,
                'product_name': 'Entrada General',
                'quantity': 3,
                'unit_price': 12000,
                'line_total': 36000,
            }
        ],
    }


def test_lookup_ticket_returns_parsed_json(requests_mock):
    requests_mock.get(f'{BASE_URL}/api/v1/tickets/VR1ABC', json=sample_ticket_response())
    result = lookup_ticket('VR1ABC')
    assert result['woo_order_number'] == sample_ticket_response()['woo_order_number']


def test_lookup_ticket_returns_none_on_404(requests_mock):
    requests_mock.get(f'{BASE_URL}/api/v1/tickets/VR1ZZZ', status_code=404)
    assert lookup_ticket('VR1ZZZ') is None


def test_lookup_ticket_sends_terminal_key_header(requests_mock):
    requests_mock.get(f'{BASE_URL}/api/v1/tickets/VR1ABC', json=sample_ticket_response())
    lookup_ticket('VR1ABC')
    assert requests_mock.last_request.headers['X-Terminal-Key'] == 'test-terminal-key'


def test_search_tickets_passes_order_and_email(requests_mock):
    m = requests_mock.get(f'{BASE_URL}/api/v1/tickets', json=[sample_ticket_response()])
    result = search_tickets(order='10452', email='maria.perez@example.com')
    assert result == [sample_ticket_response()]
    assert m.last_request.qs == {'order': ['10452'], 'email': ['maria.perez@example.com']}
    assert m.last_request.headers['X-Terminal-Key'] == 'test-terminal-key'


def test_redeem_ticket_raises_on_409(requests_mock):
    requests_mock.post(
        f'{BASE_URL}/api/v1/tickets/VR1ABC/redeem',
        status_code=409,
        json={'detail': 'Entrada ya canjeada'},
    )
    with pytest.raises(TicketAlreadyRedeemedError):
        redeem_ticket('VR1ABC', terminal='Acceso 1', redeemed_by='cajero1')


def test_redeem_ticket_sends_terminal_and_redeemed_by(requests_mock):
    m = requests_mock.post(f'{BASE_URL}/api/v1/tickets/VR1ABC/redeem', json=sample_ticket_response())
    redeem_ticket('VR1ABC', terminal='Acceso 1', redeemed_by='cajero1')
    assert m.last_request.json() == {'terminal': 'Acceso 1', 'redeemed_by': 'cajero1'}
    assert m.last_request.headers['X-Terminal-Key'] == 'test-terminal-key'


def test_report_invoice_sends_folio(requests_mock):
    m = requests_mock.post(
        f'{BASE_URL}/api/v1/tickets/VR1ABC/invoice',
        json={'invoice_status': 'ISSUED'},
    )
    report_invoice('VR1ABC', status='ISSUED', folio='26200')
    assert m.last_request.json() == {'status': 'ISSUED', 'folio': '26200'}
    assert m.last_request.headers['X-Terminal-Key'] == 'test-terminal-key'
