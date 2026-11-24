from datetime import date

from tickets.emails import send_ticket_email
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
