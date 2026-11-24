from datetime import date

from tickets.emails import QR_CONTENT_ID, send_ticket_email
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

    assert len(message.attachments) == 1
    part = message.attachments[0]
    assert part.get_content_type() == "image/png"
    assert part["Content-ID"] == f"<{QR_CONTENT_ID}>"
    # A real PNG, not an empty placeholder.
    assert part.get_payload(decode=True).startswith(b"\x89PNG")

    # multipart/related is what ties the cid: reference to the image part;
    # a plain multipart/mixed attachment is not reliably resolved.
    built = message.message()
    related = next(
        p for p in built.walk() if p.get_content_type() == "multipart/related"
    )
    related_subtypes = [p.get_content_type() for p in related.iter_parts()]
    assert related_subtypes == ["text/html", "image/png"]


def test_email_shows_the_plaintext_code_in_both_bodies(db, mailoutbox):
    """If the image does not render, the code is the buyer's only way in:
    the gate screen accepts it typed by hand, and the database keeps only
    its hash."""
    ticket = make_online_ticket()
    send_ticket_email(ticket, "VR1PLAINTEXTCODE")

    message = mailoutbox[0]
    assert "VR1PLAINTEXTCODE" in message.body
    assert "VR1PLAINTEXTCODE" in message.alternatives[0][0]
