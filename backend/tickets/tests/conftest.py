import itertools

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
