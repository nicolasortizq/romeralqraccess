import pytest

from tickets.qr import hash_code
from tickets.tests.conftest import make_online_ticket


@pytest.mark.django_db
def test_invoice_issued_sets_folio(client, active_terminal_key):
    make_online_ticket(code_hash=hash_code("VR1ABC"), status="REDEEMED")
    resp = client.post(
        "/api/v1/tickets/VR1ABC/invoice",
        data={"status": "ISSUED", "folio": "26200"},
        content_type="application/json",
        headers={"X-Terminal-Key": active_terminal_key},
    )
    assert resp.status_code == 200
    assert resp.json()["invoice_status"] == "ISSUED"
    assert resp.json()["invoice_folio"] == "26200"


@pytest.mark.django_db
def test_invoice_pending_review_has_no_folio_and_is_visible(client, active_terminal_key):
    make_online_ticket(code_hash=hash_code("VR1ABC"), status="REDEEMED")
    resp = client.post(
        "/api/v1/tickets/VR1ABC/invoice",
        data={"status": "PENDING_REVIEW", "folio": None},
        content_type="application/json",
        headers={"X-Terminal-Key": active_terminal_key},
    )
    assert resp.json()["invoice_status"] == "PENDING_REVIEW"


@pytest.mark.django_db
def test_invoice_on_unredeemed_ticket_is_rejected(client, active_terminal_key):
    make_online_ticket(code_hash=hash_code("VR1ABC"), status="VALID")
    resp = client.post(
        "/api/v1/tickets/VR1ABC/invoice",
        data={"status": "ISSUED", "folio": "1"},
        content_type="application/json",
        headers={"X-Terminal-Key": active_terminal_key},
    )
    assert resp.status_code == 409


@pytest.mark.django_db
def test_invoice_with_invalid_status_is_rejected_with_422(client, active_terminal_key):
    ticket = make_online_ticket(code_hash=hash_code("VR1ABC"), status="REDEEMED")
    resp = client.post(
        "/api/v1/tickets/VR1ABC/invoice",
        data={"status": "BOGUS", "folio": "1"},
        content_type="application/json",
        headers={"X-Terminal-Key": active_terminal_key},
    )
    assert resp.status_code == 422
    ticket.refresh_from_db()
    assert ticket.invoice_status == "NOT_ISSUED"
