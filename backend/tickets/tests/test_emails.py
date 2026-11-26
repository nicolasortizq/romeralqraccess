from datetime import date

from tickets.emails import LOGO_CONTENT_ID, QR_CONTENT_ID, send_ticket_email
from tickets.models import OnlineTicketLine
from tickets.tests.conftest import make_online_ticket


def test_send_ticket_email_delivers_one_message(db, mailoutbox):
    ticket = make_online_ticket(buyer_email="ana@example.com", people_count=2)
    send_ticket_email(ticket, "VR1ABC")
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["ana@example.com"]


def test_send_ticket_email_includes_order_number_and_validity(db, mailoutbox):
    ticket = make_online_ticket(woo_order_number="W-77", valid_until=date(2027, 2, 28))
    send_ticket_email(ticket, "VR1ABC")
    assert "W-77" in mailoutbox[0].alternatives[0][0]
    assert (
        "28 de febrero" in mailoutbox[0].alternatives[0][0]
        or "2027-02-28" in mailoutbox[0].alternatives[0][0]
    )


def test_qr_is_a_real_inline_attachment_not_a_data_uri(db, mailoutbox):
    """Gmail and several Outlook versions do not render `data:` image
    sources, so the QR has to travel as a multipart/related part the HTML
    references by Content-ID."""
    ticket = make_online_ticket()
    send_ticket_email(ticket, "VR1ABC")

    message = mailoutbox[0]
    html = message.alternatives[0][0]

    assert f"cid:{QR_CONTENT_ID}" in html
    assert "data:image/png;base64," not in html

    # Two inline images now: the QR and the brand logo (both cid:, neither
    # a data: URI -- see test_logo_is_a_real_inline_attachment_too below).
    assert len(message.attachments) == 2
    qr_part = next(p for p in message.attachments if p["Content-ID"] == f"<{QR_CONTENT_ID}>")
    assert qr_part.get_content_type() == "image/png"
    # A real PNG, not an empty placeholder.
    assert qr_part.get_payload(decode=True).startswith(b"\x89PNG")

    # multipart/related is what ties the cid: reference to the image parts;
    # a plain multipart/mixed attachment is not reliably resolved.
    built = message.message()
    related = next(
        p for p in built.walk() if p.get_content_type() == "multipart/related"
    )
    related_subtypes = [p.get_content_type() for p in related.iter_parts()]
    assert related_subtypes == ["text/html", "image/png", "image/png"]


def test_logo_is_a_real_inline_attachment_too(db, mailoutbox):
    """The brand logo travels the same way the QR does: a real cid: MIME
    part, not a data: URI (the mock used a data: URI only because it is a
    static preview file with no backend to attach anything to)."""
    ticket = make_online_ticket()
    send_ticket_email(ticket, "VR1ABC")

    message = mailoutbox[0]
    html = message.alternatives[0][0]

    assert f"cid:{LOGO_CONTENT_ID}" in html

    logo_part = next(
        p for p in message.attachments if p["Content-ID"] == f"<{LOGO_CONTENT_ID}>"
    )
    assert logo_part.get_content_type() == "image/png"
    assert logo_part.get_payload(decode=True).startswith(b"\x89PNG")


def test_email_shows_the_plaintext_code_in_both_bodies(db, mailoutbox):
    """If the image does not render, the code is the buyer's only way in:
    the gate screen accepts it typed by hand, and the database keeps only
    its hash."""
    ticket = make_online_ticket()
    send_ticket_email(ticket, "VR1PLAINTEXTCODE")

    message = mailoutbox[0]
    assert "VR1PLAINTEXTCODE" in message.body
    assert "VR1PLAINTEXTCODE" in message.alternatives[0][0]


def test_email_shows_buyer_purchase_date_and_item_lines(db, mailoutbox):
    """The redesigned template (approved mock v3, Puntoticket-style
    receipt layout) shows the buyer's name, purchase date, and the actual
    line items/total -- not just the order number and validity the
    original mock covered."""
    ticket = make_online_ticket(
        buyer_name="Ana Soto",
        total_paid=24000,
    )
    OnlineTicketLine.objects.create(
        ticket=ticket,
        woo_product_id=10,
        product_name="Entrada General",
        quantity=2,
        unit_price=12000,
        line_total=24000,
    )

    send_ticket_email(ticket, "VR1ABC")

    html = mailoutbox[0].alternatives[0][0]
    assert "Ana Soto" in html
    assert ticket.purchased_at.strftime("%d-%m-%Y") in html
    assert "Entrada General" in html
    assert "$24.000" in html


def test_email_mentions_blackout_dates_when_the_season_has_any(db, mailoutbox):
    from tickets.models import SeasonBlackoutDate

    ticket = make_online_ticket(valid_until=date(2027, 2, 28))
    SeasonBlackoutDate.objects.create(season=ticket.season, date=date(2027, 1, 1))

    send_ticket_email(ticket, "VR1ABC")

    html = mailoutbox[0].alternatives[0][0]
    assert "no válida el 1 de enero de 2027" in html
    assert "no válida el 1 de enero de 2027" in mailoutbox[0].body


def test_email_says_nothing_extra_when_the_season_has_no_blackout_dates(
    db, mailoutbox
):
    ticket = make_online_ticket(valid_until=date(2027, 2, 28))
    send_ticket_email(ticket, "VR1ABC")
    html = mailoutbox[0].alternatives[0][0]
    assert "no válida" not in html
