import itertools
import threading

import pytest
from django.db import connection
from django.utils import timezone

from tickets.models import OnlineTicket, Season, Terminal, TicketEvent
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


def run_concurrently(fn, times):
    """Runs fn() in `times` real OS threads, all released to start at the
    same time by a shared barrier, and returns their results in completion
    order. Each thread closes its own DB connection afterwards, since
    Django connections are not safe to share across threads."""
    barrier = threading.Barrier(times)
    results = [None] * times

    def target(i):
        barrier.wait()
        try:
            results[i] = fn()
        finally:
            connection.close()

    threads = [threading.Thread(target=target, args=(i,)) for i in range(times)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


@pytest.mark.django_db
def test_redeem_valid_ticket_succeeds(client, active_terminal_key):
    make_online_ticket(code_hash=hash_code("VR1ABC"), status="VALID")
    resp = client.post(
        "/api/v1/tickets/VR1ABC/redeem",
        data={"terminal": "Acceso 1", "redeemed_by": "cajero1"},
        content_type="application/json",
        headers={"X-Terminal-Key": active_terminal_key},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "REDEEMED"
    assert body["redeemed_by"] == "cajero1"
    assert body["redeemed_at"] is not None

    ticket = OnlineTicket.objects.get(code_hash=hash_code("VR1ABC"))
    assert ticket.status == "REDEEMED"
    assert ticket.redeemed_by == "cajero1"
    assert ticket.redeemed_at is not None
    event = TicketEvent.objects.get(ticket=ticket)
    assert event.event_type == "canjeada"
    assert event.terminal == "Acceso 1"


@pytest.mark.django_db
def test_redeem_unknown_code_returns_404(client, active_terminal_key):
    resp = client.post(
        "/api/v1/tickets/VR1DOESNOTEXIST/redeem",
        data={"terminal": "Acceso 1", "redeemed_by": "cajero1"},
        content_type="application/json",
        headers={"X-Terminal-Key": active_terminal_key},
    )
    assert resp.status_code == 404


@pytest.mark.django_db
def test_redeem_already_redeemed_ticket_returns_409(client, active_terminal_key):
    make_online_ticket(code_hash=hash_code("VR1ABC"), status="REDEEMED")
    resp = client.post(
        "/api/v1/tickets/VR1ABC/redeem",
        data={"terminal": "Acceso 1", "redeemed_by": "cajero1"},
        content_type="application/json",
        headers={"X-Terminal-Key": active_terminal_key},
    )
    assert resp.status_code == 409
    assert "ya fue" in resp.json()["detail"].lower() or "canje" in resp.json()["detail"].lower()


@pytest.mark.django_db
def test_redeem_cancelled_ticket_returns_409_with_reason(client, active_terminal_key):
    make_online_ticket(code_hash=hash_code("VR1ABC"), status="CANCELLED")
    resp = client.post(
        "/api/v1/tickets/VR1ABC/redeem",
        data={"terminal": "Acceso 1", "redeemed_by": "cajero1"},
        content_type="application/json",
        headers={"X-Terminal-Key": active_terminal_key},
    )
    assert resp.status_code == 409
    assert "anulada" in resp.json()["detail"].lower()


@pytest.mark.django_db
def test_redeem_refunded_after_redemption_ticket_returns_409_with_reason(
    client, active_terminal_key
):
    make_online_ticket(
        code_hash=hash_code("VR1ABC"), status="REFUNDED_AFTER_REDEMPTION"
    )
    resp = client.post(
        "/api/v1/tickets/VR1ABC/redeem",
        data={"terminal": "Acceso 1", "redeemed_by": "cajero1"},
        content_type="application/json",
        headers={"X-Terminal-Key": active_terminal_key},
    )
    assert resp.status_code == 409
    assert "reembols" in resp.json()["detail"].lower()


@pytest.mark.django_db
def test_redeem_ticket_past_valid_until_returns_409(client, active_terminal_key):
    season = make_season(ends_on="2020-01-31")
    make_online_ticket(
        code_hash=hash_code("VR1ABC"),
        status="VALID",
        season=season,
        valid_until=season.ends_on,
    )
    resp = client.post(
        "/api/v1/tickets/VR1ABC/redeem",
        data={"terminal": "Acceso 1", "redeemed_by": "cajero1"},
        content_type="application/json",
        headers={"X-Terminal-Key": active_terminal_key},
    )
    assert resp.status_code == 409
    assert "temporada" in resp.json()["detail"].lower()

    ticket = OnlineTicket.objects.get(code_hash=hash_code("VR1ABC"))
    assert ticket.status != "REDEEMED"


@pytest.mark.django_db(transaction=True)
def test_concurrent_redeem_requests_only_one_succeeds():
    # transaction=True disables the test's wrapping transaction, so the
    # rows below are actually committed and visible to the other real
    # threads/connections spawned by run_concurrently. Without it, every
    # thread would share the single outer test transaction (Django test
    # connections are not thread-local across a TestCase-style atomic
    # wrapper the way separate requests in production are), select_for_update
    # would never actually block a second transaction, and the test would
    # pass "by luck" rather than by exercising the lock.
    plaintext = "test-terminal-key-123"
    Terminal.objects.create(
        name="Acceso 1", api_key_hash=hash_code(plaintext), is_active=True
    )
    make_online_ticket(code_hash=hash_code("VR1ABC"), status="VALID")
    connection.close()  # force each thread below to open its own fresh connection

    def call():
        from django.test import Client

        return Client().post(
            "/api/v1/tickets/VR1ABC/redeem",
            data={"terminal": "Acceso 1", "redeemed_by": "cajero1"},
            content_type="application/json",
            headers={"X-Terminal-Key": plaintext},
        )

    results = [r.status_code for r in run_concurrently(call, times=10)]
    assert results.count(200) == 1
    assert results.count(409) == 9

    ticket = OnlineTicket.objects.get(code_hash=hash_code("VR1ABC"))
    assert ticket.status == "REDEEMED"
    assert TicketEvent.objects.filter(ticket=ticket, event_type="canjeada").count() == 1
