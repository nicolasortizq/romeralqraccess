"""Decision logic for the online (QR) ticket redeem screen.

This module is deliberately separate from `romeral.py`: `desktop/tests/conftest.py`
registers a lightweight stand-in for the `romeral` module in `sys.modules` before
any test imports anything, precisely so importing test subjects never triggers
the real `romeral.py` module-level side effects (tkinter, opening the real
gate SQLite database). `ventas_online.py` already follows this convention
(it does `import romeral` at module level, but only calls `romeral.config()`
inside functions); `CanjeOnlineController` follows the same shape so it can
be unit-tested with a plain mock `app`, without ever constructing a real
`Romeral` Tkinter window.

`CanjeOnlineController` itself holds no state: it orchestrates calls between
the backend HTTP client (`ventas_online`) and the Tkinter app instance
(`app`, duck-typed as `Romeral` in production, a mock in tests), which owns
the local SQLite connection, the `emision_en_curso` lock and the actual DTE
emission (`emitir_automaticamente`, shared with in-person sales).
"""
import logging
import sqlite3

import ventas_online
from ventas_online import TicketAlreadyRedeemedError

logger = logging.getLogger(__name__)

# Must match docs/api/openapi.yaml's InvoiceReport.status enum.
INVOICE_STATUS_ISSUED = 'ISSUED'
INVOICE_STATUS_PENDING_REVIEW = 'PENDING_REVIEW'

# Must match the `ventas.estado_boleta` value set once EMISION_REAL_CONTROLADA.py
# confirms the SOAP response (see romeral.py's emitir_automaticamente/terminar()).
ESTADO_BOLETA_EMITIDA = 'EMITIDA'

# How often to poll for emitir_automaticamente()'s result once it has been
# started. It runs in its own background thread and offers no completion
# callback (by design: romeral.py's docstring on emitir_automaticamente()
# says callers should not change it), so this is the hook point available
# without touching that method.
POLL_INTERVAL_MS = 300

# Upper bound on how long to keep polling before giving up and reporting the
# invoice as pending review instead of waiting forever. emision_en_curso is
# only ever expected to clear within seconds (one SOAP attempt plus PDF
# retrieval), so ~2 minutes is generous; if it never clears this stops the
# poll loop instead of leaking it indefinitely.
MAX_POLL_ATTEMPTS = 400  # 400 * 300ms ~= 120s

# How many times to attempt reporting the invoice result to the backend
# before giving up and only logging the failure. The redemption and local
# sale have already succeeded by this point, so a report_invoice failure
# must never block or crash the cashier's screen.
REPORT_INVOICE_ATTEMPTS = 2


class CanjeOnlineController:
    """Drives the redeem screen's single action: look up and canjear a code."""

    def __init__(self, app):
        self.app = app

    def puede_canjear(self):
        """True only when the shared pre-emission conditions currently hold.

        Does not check whether a ticket code has even been entered yet; that
        is the caller's (the Tkinter screen's) job, same as in-person sales.
        """
        return bool(self.app.verificar_condiciones_emision())

    def canjear(self, code):
        """Redeem one ticket code. Returns a user-facing status message.

        On success: redeems the ticket on the backend, inserts the local
        `ventas` row (origen='ONLINE'), starts `emitir_automaticamente()` and
        schedules reporting its outcome back to the backend. Never raises;
        every known failure mode returns a message instead.

        Once `ventas_online.redeem_ticket()` returns successfully, the
        backend has already committed the redemption: the ticket's one and
        only entry has been spent. Every failure path below this point
        (invalid total, local insert failure) must therefore still try to
        tell the backend via `report_invoice` and must say so clearly to the
        cashier, instead of silently losing the sale/boleta record.
        """
        if not self.puede_canjear():
            return 'No se puede canjear: revisa las condiciones de emisión antes de continuar.'
        if self.app.emision_en_curso:
            return 'Espera el resultado de la boleta anterior antes de canjear otra entrada.'
        try:
            resultado = ventas_online.redeem_ticket(code, self.app.terminal_nombre, self.app.operador_actual)
        except TicketAlreadyRedeemedError as exc:
            return str(exc)
        except Exception as exc:
            # Any other failure (timeout, connection error, 5xx via
            # raise_for_status) leaves the real redemption state unknown:
            # the request may have timed out AFTER the backend committed
            # it. Never guess here; tell the cashier to re-scan and read the
            # ticket's real current status instead of proceeding blind.
            logger.warning('redeem_ticket failed for %s with a non-409 error: %s', code, exc, exc_info=True)
            return (
                'No se pudo confirmar el canje con el backend '
                f'({type(exc).__name__}). La entrada puede o no haberse marcado como canjeada: '
                'vuelve a escanear el código para revisar su estado real antes de reintentar.'
            )

        total = resultado.get('total_paid', 0)
        cantidad = resultado.get('people_count', 1)
        if type(total) is not int or total <= 0:
            self._reportar_resultado(code, folio=None, estado=None)
            return (
                f'La entrada ya fue canjeada en el backend, pero el monto pagado informado ({total!r}) '
                'no es válido. No se registró ninguna venta local. Avisa al supervisor para revisar el pedido.'
            )

        try:
            venta_id = self.app.registrar_venta_online(total, cantidad)
        except sqlite3.Error as exc:
            # Worst reachable state: the backend redemption already
            # succeeded, so the ticket is spent, but the local sale/boleta
            # record never got written. Flag it for the supervisor via the
            # backend instead of leaving it untracked anywhere.
            logger.warning('registrar_venta_online failed for %s: %s', code, exc, exc_info=True)
            self._reportar_resultado(code, folio=None, estado=None)
            return (
                'La entrada ya fue canjeada (es válida), pero no se pudo guardar la venta local '
                f'({exc}). Avisa al supervisor: debe registrar la venta y la boleta manualmente.'
            )

        self.app.emitir_automaticamente(venta_id, total)
        self._esperar_resultado_y_reportar(code, venta_id)
        return f'Entrada canjeada · venta {venta_id} · emitiendo boleta DTE 39.'

    def _esperar_resultado_y_reportar(self, code, venta_id, intento=0):
        """Polls until emitir_automaticamente() releases its lock, then reports.

        Scheduled through `app.after`, the same Tkinter-safe mechanism
        `emitir_automaticamente()` itself uses to get back onto the UI thread.
        Bounded by MAX_POLL_ATTEMPTS: if emision_en_curso never clears, this
        stops polling and reports the invoice as pending review rather than
        polling forever.
        """
        def revisar():
            if self.app.emision_en_curso:
                if intento + 1 >= MAX_POLL_ATTEMPTS:
                    logger.warning(
                        'Polling the emission result for venta %s (code %s) timed out '
                        'after %d attempts; reporting as pending manual review.',
                        venta_id, code, intento + 1)
                    self._reportar_resultado(code, folio=None, estado=None)
                    return
                self._esperar_resultado_y_reportar(code, venta_id, intento + 1)
                return
            folio, estado = self.app.consultar_resultado_emision(venta_id)
            self._reportar_resultado(code, folio, estado)
        self.app.after(POLL_INTERVAL_MS if intento else 0, revisar)

    def _reportar_resultado(self, code, folio, estado):
        """Reports the invoice outcome to the backend, never raising.

        `report_invoice` runs on the UI thread and can block up to
        TIMEOUT_SECONDS; by the time this is called, the redemption and the
        local sale have already succeeded, so a reporting failure here must
        not crash or block the cashier's screen. Retries once, then only
        logs a warning so the gap is visible without losing the sale.
        """
        if estado == ESTADO_BOLETA_EMITIDA and folio:
            status, folio_a_reportar = INVOICE_STATUS_ISSUED, folio
        else:
            status, folio_a_reportar = INVOICE_STATUS_PENDING_REVIEW, None
        for intento in range(1, REPORT_INVOICE_ATTEMPTS + 1):
            try:
                ventas_online.report_invoice(code, status=status, folio=folio_a_reportar)
                return
            except Exception as exc:
                if intento == REPORT_INVOICE_ATTEMPTS:
                    logger.warning(
                        'report_invoice failed for %s (status=%s, folio=%s) after %d attempt(s): %s',
                        code, status, folio_a_reportar, intento, exc, exc_info=True)
