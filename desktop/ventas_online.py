"""HTTP client to the romeralQRAccess backend for online (QR) tickets.

The backend (built in `backend/`, contract in `docs/api/openapi.yaml`) is the
source of truth for online tickets: it receives paid WooCommerce orders,
creates the ticket and emails the QR, and exposes the API this module talks
to so the gate can look up, search, redeem and report the invoice of a
ticket. This module makes no local copy and keeps no SQLite state of its
own; the only thing it owns is turning this app's config into HTTP calls.

Configuration (`acceso_api_url`, `acceso_terminal_key`) comes from the same
mechanism the rest of the app already uses, `romeral.config()`, rather than
a second settings system. See `docs/api/README.md` for the full list of gate
configuration keys.

`romeral` is imported lazily inside the functions that need it, never at
module level: `romeral.py` runs as `__main__` and imports this module, so a
module-level `import romeral` re-executes `romeral.py` as a second module
and deadlocks the import cycle (romeral -> ventas_online -> romeral ->
canje_online -> ventas_online, which is still half-initialised).
"""
import requests

TIMEOUT_SECONDS = 10


class TicketAlreadyRedeemedError(Exception):
    """Raised when the backend refuses a redemption (HTTP 409).

    Covers every reason the API returns 409 for: already REDEEMED,
    CANCELLED, or REFUNDED_AFTER_REDEMPTION.
    """


def _config(key):
    # Deferred import: see the module docstring. romeral.py runs as __main__
    # and imports this module, so importing it at module level re-executes it.
    import romeral
    return romeral.config(key)


def _base_url():
    url = _config('acceso_api_url')
    if not url:
        raise RuntimeError('Falta configurar acceso_api_url.')
    return url.rstrip('/')


def _headers():
    terminal_key = _config('acceso_terminal_key')
    if not terminal_key:
        raise RuntimeError('Falta configurar acceso_terminal_key.')
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
