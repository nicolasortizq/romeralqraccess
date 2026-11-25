from datetime import date

import pytest

from tickets.models import OnlineTicket
from tickets.qr import hash_code
from tickets.tests.conftest import make_online_ticket


@pytest.mark.django_db
def test_lookup_by_code_returns_ticket(client, active_terminal_key):
    ticket = make_online_ticket(code_hash=hash_code("VR1ABC"))
    resp = client.get(
        "/api/v1/tickets/VR1ABC", headers={"X-Terminal-Key": active_terminal_key}
    )
    assert resp.status_code == 200
    assert resp.json()["woo_order_number"] == ticket.woo_order_number


@pytest.mark.django_db
def test_lookup_unknown_code_returns_404(client, active_terminal_key):
    resp = client.get(
        "/api/v1/tickets/VR1DOESNOTEXIST",
        headers={"X-Terminal-Key": active_terminal_key},
    )
    assert resp.status_code == 404


@pytest.mark.django_db
def test_lookup_past_valid_until_reports_fuera_de_temporada(
    client, active_terminal_key
):
    make_online_ticket(
        code_hash=hash_code("VR1OLD"), valid_until=date(2025, 1, 1), status="VALID"
    )
    resp = client.get(
        "/api/v1/tickets/VR1OLD", headers={"X-Terminal-Key": active_terminal_key}
    )
    assert resp.status_code == 200
    assert resp.json()["display_status"] == "fuera de temporada"


@pytest.mark.django_db
def test_lookup_within_season_has_no_display_status(client, active_terminal_key):
    make_online_ticket(code_hash=hash_code("VR1CUR"), valid_until=date(2099, 1, 1))
    resp = client.get(
        "/api/v1/tickets/VR1CUR", headers={"X-Terminal-Key": active_terminal_key}
    )
    assert resp.status_code == 200
    assert resp.json()["display_status"] is None


@pytest.mark.django_db
def test_lookup_redeemed_past_valid_until_keeps_status(client, active_terminal_key):
    # display_status is only computed for VALID tickets that outlived their
    # season; a REDEEMED ticket's stored status already reflects reality.
    make_online_ticket(
        code_hash=hash_code("VR1RED"),
        valid_until=date(2025, 1, 1),
        status="REDEEMED",
    )
    resp = client.get(
        "/api/v1/tickets/VR1RED", headers={"X-Terminal-Key": active_terminal_key}
    )
    assert resp.json()["status"] == "REDEEMED"
    assert resp.json()["display_status"] is None


@pytest.mark.django_db
def test_search_by_order_number(client, active_terminal_key):
    make_online_ticket(woo_order_number="W-42")
    resp = client.get(
        "/api/v1/tickets?order=W-42", headers={"X-Terminal-Key": active_terminal_key}
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.django_db
def test_search_by_email(client, active_terminal_key):
    make_online_ticket(buyer_email="juan@example.com")
    resp = client.get(
        "/api/v1/tickets?email=juan@example.com",
        headers={"X-Terminal-Key": active_terminal_key},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.django_db
def test_search_without_order_or_email_is_rejected(client, active_terminal_key):
    resp = client.get(
        "/api/v1/tickets", headers={"X-Terminal-Key": active_terminal_key}
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_missing_terminal_key_is_rejected(client):
    resp = client.get("/api/v1/tickets/VR1ABC")
    assert resp.status_code == 401
