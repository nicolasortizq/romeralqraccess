import itertools
from datetime import date

import pytest
from django.utils import timezone

from tickets.models import OnlineTicket, Season, Terminal
from tickets.qr import hash_code

_counter = itertools.count(1)


def make_season(**overrides):
    defaults = dict(name="2026-2027", starts_on="2026-11-20", ends_on="2027-02-28")
    defaults.update(overrides)
    return Season.objects.create(**defaults)


def make_online_ticket(**overrides):
    season = overrides.pop("season", None) or make_season()
    n = next(_counter)
    defaults = dict(
        code_hash=hash_code(f"VR1TEST{n:016d}"),
        woo_order_id=n,
        woo_order_number=f"W-{n}",
        buyer_name="Ana",
        buyer_email="ana@example.com",
        people_count=2,
        total_paid=24000,
        payment_method="Webpay",
        purchased_at=timezone.now(),
        season=season,
        valid_until=season.ends_on,
        status="VALID",
        invoice_status="NOT_ISSUED",
        source="WEBHOOK",
    )
    defaults.update(overrides)
    return OnlineTicket.objects.create(**defaults)


@pytest.fixture
def active_terminal_key(db):
    plaintext = "test-terminal-key-123"
    Terminal.objects.create(
        name="Acceso 1", api_key_hash=hash_code(plaintext), is_active=True
    )
    return plaintext


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
