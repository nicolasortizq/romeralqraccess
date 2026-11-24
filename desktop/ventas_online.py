"""HTTP client to the romeralQRAccess backend for online (QR) tickets.

The backend (built in `backend/`, contract in `docs/api/openapi.yaml`) is the
source of truth for online tickets: it receives paid WooCommerce orders,
creates the ticket and emails the QR, and exposes the API this module talks
to so the gate can look up, search, redeem and report the invoice of a
ticket. This module makes no local copy and keeps no SQLite state of its
own; the only thing it owns is turning this app's config into HTTP calls.

Configuration (`ACCESO_API_URL`, `ACCESO_TERMINAL_KEY`) comes from the same
mechanism the rest of the app already uses, `romeral.config()`, rather than
a second settings system.
"""
import requests
import romeral

TIMEOUT_SECONDS = 10


class TicketAlreadyRedeemedError(Exception):
    """Raised when the backend refuses a redemption (HTTP 409).

    Covers every reason the API returns 409 for: already REDEEMED,
    CANCELLED, or REFUNDED_AFTER_REDEMPTION.
    """


def _base_url():
    url = romeral.config('ACCESO_API_URL')
    if not url:
        raise RuntimeError('Falta configurar ACCESO_API_URL.')
    return url.rstrip('/')


def _headers():
    terminal_key = romeral.config('ACCESO_TERMINAL_KEY')
    if not terminal_key:
        raise RuntimeError('Falta configurar ACCESO_TERMINAL_KEY.')
    return {'X-Terminal-Key': terminal_key}


def lookup_ticket(code):
    """Look up a ticket by its QR code. Returns None if it does not exist."""
    response = requests.get(
        f'{_base_url()}/api/v1/tickets/{code}',
        headers=_headers(),
        timeout=TIMEOUT_SECONDS,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def search_tickets(order=None, email=None):
    """Search tickets by WooCommerce order number and/or buyer email."""
    params = {}
    if order:
        params['order'] = order
    if email:
        params['email'] = email
    response = requests.get(
        f'{_base_url()}/api/v1/tickets',
        headers=_headers(),
        params=params,
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def redeem_ticket(code, terminal, redeemed_by):
    """Redeem a ticket. Raises TicketAlreadyRedeemedError if it cannot be redeemed."""
    response = requests.post(
        f'{_base_url()}/api/v1/tickets/{code}/redeem',
        headers=_headers(),
        json={'terminal': terminal, 'redeemed_by': redeemed_by},
        timeout=TIMEOUT_SECONDS,
    )
    if response.status_code == 409:
        detail = response.json().get('detail', 'Entrada ya canjeada')
        raise TicketAlreadyRedeemedError(detail)
    response.raise_for_status()
    return response.json()


def report_invoice(code, status, folio=None):
    """Report the result of issuing the boleta for a redeemed ticket."""
    response = requests.post(
        f'{_base_url()}/api/v1/tickets/{code}/invoice',
        headers=_headers(),
        json={'status': status, 'folio': folio},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()
