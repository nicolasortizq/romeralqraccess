"""Sends the QR ticket email to a buyer.

This module is one of only two places in the codebase that ever see a
ticket's plaintext QR code (the other is the import command, Task 15); the
database only stores its SHA-256 hash (OnlineTicket.code_hash), so the code
has to be passed in by the caller rather than read back off the ticket.
"""

import io
from email.message import MIMEPart

import qrcode
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.dateparse import parse_date

# Content-ID of the inline QR image part. The HTML template references it as
# `cid:` + this value; the two must stay in step.
QR_CONTENT_ID = "qr_code"

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


def _qr_png(code: str) -> bytes:
    """Renders the QR code for `code` (the plaintext ticket code) as PNG
    bytes."""
    img = qrcode.make(code)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def _qr_image_part(png: bytes) -> MIMEPart:
    """Builds the inline image part the HTML body references as
    `cid:QR_CONTENT_ID`.

    A real MIME part with a Content-ID, not a data: URI: Gmail and several
    Outlook versions refuse to render `data:` image sources, so a data URI
    would show a broken image to a large share of buyers -- and the
    plaintext code exists nowhere else (the database only keeps its hash),
    so there would be no way to recover the entry.
    """
    part = MIMEPart()
    part.set_content(
        png,
        maintype="image",
        subtype="png",
        # The angle brackets are what RFC 2392 expects in the header; the
        # `cid:` URL in the HTML refers to the id without them.
        cid=f"<{QR_CONTENT_ID}>",
        disposition="inline",
        filename="entrada-qr.png",
    )
    return part


class _RelatedMultipartEmail(EmailMultiAlternatives):
    """An EmailMultiAlternatives that nests its attachments in a
    multipart/related alongside the HTML body.

    Django 6.1 has no public API for inline (cid:) images: its default
    structure makes the QR a plain multipart/mixed attachment, which not
    every client resolves a `cid:` reference against. Overriding this one
    private hook produces the structure RFC 2387 describes and every mail
    client understands:

        multipart/alternative
          text/plain                 -> carries the code as text
          multipart/related
            text/html                -> <img src="cid:qr_code">
            image/png                -> Content-ID: <qr_code>
    """

    def _add_attachments(self, msg):
        if not self.attachments:
            return msg

        html_part = next(
            (p for p in msg.walk() if p.get_content_type() == "text/html"), None
        )
        if html_part is None:
            # No HTML body to relate the image to; fall back to Django's
            # ordinary multipart/mixed attachment handling.
            return super()._add_attachments(msg)

        html_part.make_related()
        for attachment in self.attachments:
            html_part.attach(attachment)
        return msg


def send_ticket_email(ticket, code: str) -> None:
    """Emails `ticket`'s buyer their QR code. `code` is the plaintext QR
    content (prefix VR1, uppercase letters and digits); the ticket itself
    only has `code_hash`.
    """
    context = {
        "buyer_first_name": ticket.buyer_name.split(" ")[0] if ticket.buyer_name else "",
        "qr_content_id": QR_CONTENT_ID,
        "ticket_code": code,
        "order_number": ticket.woo_order_number,
        "people_label": _people_label(ticket.people_count),
        "valid_until_label": _format_valid_until(ticket.valid_until),
    }
    html_body = render_to_string("emails/qr_ticket.html", context)

    # The plaintext body carries the code too. Both bodies must: if the
    # image does not render (blocked remote content, a text-only client),
    # the code is the buyer's only remaining way in, through the gate
    # screen's manual-entry field.
    text_body = (
        f"Tu entrada #{ticket.woo_order_number} esta lista.\n\n"
        f"Codigo de tu entrada: {code}\n\n"
        f"Muestra el codigo QR de este correo en el acceso. Si la imagen no "
        f"se ve, dicta o escribe el codigo de arriba.\n\n"
        f"Personas: {_people_label(ticket.people_count)}\n"
        f"Valida hasta el {_format_valid_until(ticket.valid_until)}.\n"
    )

    message = _RelatedMultipartEmail(
        subject="Tu entrada - Valle del Romeral",
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[ticket.buyer_email],
    )
    message.attach_alternative(html_body, "text/html")
    message.attach(_qr_image_part(_qr_png(code)))
    message.send()
