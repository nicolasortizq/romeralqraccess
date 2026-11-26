"""Sends the QR ticket email to a buyer.

This module is one of only two places in the codebase that ever see a
ticket's plaintext QR code (the other is the import command, Task 15); the
database only stores its SHA-256 hash (OnlineTicket.code_hash), so the code
has to be passed in by the caller rather than read back off the ticket.
"""

import io
from email.message import MIMEPart
from pathlib import Path

import qrcode
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.dateparse import parse_date

# Content-ID of the inline QR image part. The HTML template references it as
# `cid:` + this value; the two must stay in step.
QR_CONTENT_ID = "qr_code"

# Content-ID of the inline brand logo, same mechanism as the QR. The PNG
# itself is a static asset checked into the repo (not fetched from
# vallederomeral.cl on every send -- that would make every ticket email
# depend on the marketing site staying up).
LOGO_CONTENT_ID = "logo"
_LOGO_PATH = Path(__file__).with_name("assets") / "logo.png"

_MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def _format_long_date(d) -> str:
    """Formats a date as 'D de <mes> de AAAA', the copy approved in the
    mock. Built manually (not via Django's date filter) so the Spanish
    month name does not depend on LANGUAGE_CODE/locale activation."""
    if isinstance(d, str):
        d = parse_date(d)
    return f"{d.day} de {_MESES[d.month - 1]} de {d.year}"


def _format_valid_until(valid_until) -> str:
    return _format_long_date(valid_until)


def _blackout_note(season) -> str:
    """Builds the "(no valida el 1 de enero)"-style suffix for the
    validity line, from this season's SeasonBlackoutDate rows -- added
    because Rodrigo sells presencial at a higher price on Jan 1 due to
    demand, so a buyer must see upfront that their online ticket won't
    work that specific day. Empty string if the season has none."""
    dates = [bd.date for bd in season.blackout_dates.all()]
    if not dates:
        return ""
    formatted = " y ".join(_format_long_date(d) for d in dates)
    prefix = "el" if len(dates) == 1 else "los días"
    return f" (no válida {prefix} {formatted})"


def _people_label(people_count: int) -> str:
    noun = "persona" if people_count == 1 else "personas"
    return f"{people_count} {noun}"


def _pesos(amount: int) -> str:
    """Formats an integer CLP amount as '$12.345' -- the thousands
    separator the rest of the project (the desktop app's own `pesos()`)
    already uses, so a buyer sees the same convention everywhere."""
    return "$" + f"{int(amount):,}".replace(",", ".")


def _short_date(dt) -> str:
    """Formats a datetime as 'DD-MM-AAAA', the copy approved in the mock
    for "Fecha de compra" -- distinct from `_format_valid_until`'s longer
    Spanish form, which is for the season end date, not a purchase
    timestamp."""
    return dt.strftime("%d-%m-%Y")


def _qr_png(code: str) -> bytes:
    """Renders the QR code for `code` (the plaintext ticket code) as PNG
    bytes."""
    img = qrcode.make(code)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def _inline_image_part(png: bytes, content_id: str, filename: str) -> MIMEPart:
    """Builds an inline image MIME part the HTML body can reference as
    `cid:<content_id>`.

    A real MIME part with a Content-ID, not a data: URI: Gmail and several
    Outlook versions refuse to render `data:` image sources. For the QR
    specifically, the plaintext code also exists nowhere else (the database
    only keeps its hash), so a broken image would leave no way to recover
    the entry; the logo has no such stakes but uses the same mechanism for
    consistency and because `data:` URIs fail the same way regardless.
    """
    part = MIMEPart()
    part.set_content(
        png,
        maintype="image",
        subtype="png",
        # The angle brackets are what RFC 2392 expects in the header; the
        # `cid:` URL in the HTML refers to the id without them.
        cid=f"<{content_id}>",
        disposition="inline",
        filename=filename,
    )
    return part


def _logo_png() -> bytes:
    return _LOGO_PATH.read_bytes()


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
        "buyer_name": ticket.buyer_name,
        "buyer_email": ticket.buyer_email,
        "qr_content_id": QR_CONTENT_ID,
        "logo_content_id": LOGO_CONTENT_ID,
        "ticket_code": code,
        "order_number": ticket.woo_order_number,
        "purchased_at_label": _short_date(ticket.purchased_at),
        "people_label": _people_label(ticket.people_count),
        "valid_until_label": _format_valid_until(ticket.valid_until),
        "blackout_note": _blackout_note(ticket.season),
        "lines": [
            {
                "product_name": line.product_name,
                "quantity": line.quantity,
                "line_total_label": _pesos(line.line_total),
            }
            for line in ticket.lines.all()
        ],
        "total_paid_label": _pesos(ticket.total_paid),
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
        f"Valida hasta el {_format_valid_until(ticket.valid_until)}"
        f"{_blackout_note(ticket.season)}.\n"
    )

    message = _RelatedMultipartEmail(
        subject="Tu entrada - Valle del Romeral",
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[ticket.buyer_email],
    )
    message.attach_alternative(html_body, "text/html")
    message.attach(_inline_image_part(_qr_png(code), QR_CONTENT_ID, "entrada-qr.png"))
    message.attach(_inline_image_part(_logo_png(), LOGO_CONTENT_ID, "logo.png"))
    message.send()
