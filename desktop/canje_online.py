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
import ventas_online
from ventas_online import TicketAlreadyRedeemedError

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
        """
        if not self.puede_canjear():
            return 'No se puede canjear: revisa las condiciones de emisión antes de continuar.'
        if self.app.emision_en_curso:
            return 'Espera el resultado de la boleta anterior antes de canjear otra entrada.'
        try:
            resultado = ventas_online.redeem_ticket(code, self.app.terminal_nombre, self.app.operador_actual)
        except TicketAlreadyRedeemedError as exc:
            return str(exc)
        total = resultado.get('total_paid', 0)
        cantidad = resultado.get('people_count', 1)
        venta_id = self.app.registrar_venta_online(total, cantidad)
        self.app.emitir_automaticamente(venta_id, total)
        self._esperar_resultado_y_reportar(code, venta_id)
        return f'Entrada canjeada · venta {venta_id} · emitiendo boleta DTE 39.'

    def _esperar_resultado_y_reportar(self, code, venta_id):
        """Polls until emitir_automaticamente() releases its lock, then reports.

        Scheduled through `app.after`, the same Tkinter-safe mechanism
        `emitir_automaticamente()` itself uses to get back onto the UI thread.
        """
        def revisar():
            if self.app.emision_en_curso:
                self.app.after(POLL_INTERVAL_MS, revisar)
                return
            folio, estado = self.app.consultar_resultado_emision(venta_id)
            if estado == ESTADO_BOLETA_EMITIDA and folio:
                ventas_online.report_invoice(code, status=INVOICE_STATUS_ISSUED, folio=folio)
            else:
                ventas_online.report_invoice(code, status=INVOICE_STATUS_PENDING_REVIEW, folio=None)
        self.app.after(0, revisar)
