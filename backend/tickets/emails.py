"""Sends the QR ticket email to a buyer.

This module is one of only two places in the codebase that ever see a
ticket's plaintext QR code (the other is the import command, Task 15); the
database only stores its SHA-256 hash (OnlineTicket.code_hash), so the code
has to be passed in by the caller rather than read back off the ticket.
"""

import base64
import io

import qrcode
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.dateparse import parse_date

_MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def _format_valid_until(valid_until) -> str:
    """Formats a date as 'D de <mes> de AAAA', the copy approved in the
    mock. Built manually (not via Django's date filter) so the Spanish
    month name does not depend on LANGUAGE_CODE/locale activation."""
    if isinstance(valid_until, str):
        valid_until = parse_date(valid_until)
    return f"{valid_until.day} de {_MESES[valid_until.month - 1]} de {valid_until.year}"


def _people_label(people_count: int) -> str:
    noun = "persona" if people_count == 1 else "personas"
    return f"{people_count} {noun}"


def _qr_data_uri(code: str) -> str:
    """Renders the QR code for `code` (the plaintext ticket code) as a PNG
    and returns it as a data: URI.

    A data URI (rather than a MIME attachment with a Content-ID) keeps the
    image inline in a single HTML part, which is simpler and more reliable
    to assert against in tests: it is just a substring of
    mailoutbox[0].alternatives[0][0], with no need to inspect a separate
    multipart/related attachment to verify the email carries the right
    image.
    """
    img = qrcode.make(code)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def send_ticket_email(ticket, code: str) -> None:
    """Emails `ticket`'s buyer their QR code. `code` is the plaintext QR
    content (prefix VR1, uppercase letters and digits); the ticket itself
    only has `code_hash`.
    """
    context = {
        "buyer_first_name": ticket.buyer_name.split(" ")[0] if ticket.buyer_name else "",
        "qr_data_uri": _qr_data_uri(code),
        "order_number": ticket.woo_order_number,
        "people_label": _people_label(ticket.people_count),
        "valid_until_label": _format_valid_until(ticket.valid_until),
    }
    html_body = render_to_string("emails/qr_ticket.html", context)

    message = EmailMultiAlternatives(
        subject="Tu entrada - Valle del Romeral",
        body=f"Tu entrada #{ticket.woo_order_number} esta lista. Abre este correo en un cliente que muestre HTML para ver tu código QR.",
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[ticket.buyer_email],
    )
    message.attach_alternative(html_body, "text/html")
    message.send()
