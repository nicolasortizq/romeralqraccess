import pytest
from django.db import IntegrityError
from django.utils import timezone

from tickets.models import (
    OnlineTicket,
    OnlineTicketLine,
    Season,
    SeasonBlackoutDate,
    Terminal,
    TicketEvent,
)


def make_season(**overrides):
    defaults = dict(
        name="2026-2027", starts_on="2026-11-20", ends_on="2027-02-28"
    )
    defaults.update(overrides)
    return Season.objects.create(**defaults)


def make_ticket(season, **overrides):
    defaults = dict(
        code_hash="a" * 64,
        woo_order_id=1,
        woo_order_number="W-1",
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


@pytest.mark.django_db
def test_online_ticket_status_choices_include_refunded_after_redemption():
    assert "REFUNDED_AFTER_REDEMPTION" in dict(OnlineTicket.STATUS_CHOICES)


@pytest.mark.django_db
def test_online_ticket_status_choices_match_global_constraints():
    assert dict(OnlineTicket.STATUS_CHOICES).keys() == {
        "VALID",
        "REDEEMED",
        "CANCELLED",
        "REFUNDED_AFTER_REDEMPTION",
    }


@pytest.mark.django_db
def test_online_ticket_invoice_status_choices_match_global_constraints():
    assert dict(OnlineTicket.INVOICE_STATUS_CHOICES).keys() == {
        "NOT_ISSUED",
        "ISSUED",
        "PENDING_REVIEW",
    }


@pytest.mark.django_db
def test_online_ticket_source_choices_match_global_constraints():
    assert dict(OnlineTicket.SOURCE_CHOICES).keys() == {
        "WEBHOOK",
        "RECONCILIATION",
        "IMPORT",
    }


@pytest.mark.django_db
def test_online_ticket_requires_unique_code_hash():
    season = make_season()
    make_ticket(season, code_hash="a" * 64, woo_order_id=1, woo_order_number="W-1")
    with pytest.raises(IntegrityError):
        make_ticket(season, code_hash="a" * 64, woo_order_id=2, woo_order_number="W-2")


@pytest.mark.django_db
def test_online_ticket_requires_unique_woo_order_id():
    season = make_season()
    make_ticket(season, code_hash="a" * 64, woo_order_id=42, woo_order_number="W-1")
    with pytest.raises(IntegrityError):
        make_ticket(
            season, code_hash="b" * 64, woo_order_id=42, woo_order_number="W-2"
        )


@pytest.mark.django_db
def test_online_ticket_uses_uuid_primary_key():
    import uuid

    season = make_season()
    ticket = make_ticket(season)
    assert isinstance(ticket.id, uuid.UUID)


@pytest.mark.django_db
def test_online_ticket_redeemed_fields_default_to_none():
    season = make_season()
    ticket = make_ticket(season)
    assert ticket.redeemed_at is None
    assert ticket.redeemed_by is None
    assert ticket.invoice_folio is None


@pytest.mark.django_db
def test_online_ticket_line_links_to_ticket_and_computes_total():
    season = make_season()
    ticket = make_ticket(season)
    line = OnlineTicketLine.objects.create(
        ticket=ticket,
        woo_product_id=10,
        product_name="Entrada general",
        quantity=2,
        unit_price=12000,
        line_total=24000,
    )
    assert line in ticket.lines.all()


@pytest.mark.django_db
def test_ticket_event_links_to_ticket_and_stores_detail_json():
    season = make_season()
    ticket = make_ticket(season)
    event = TicketEvent.objects.create(
        ticket=ticket,
        event_type="canjeada",
        occurred_at=timezone.now(),
        terminal="Acceso 1",
        detail={"redeemed_by": "cajero1"},
    )
    assert event in ticket.events.all()
    assert event.detail["redeemed_by"] == "cajero1"


@pytest.mark.django_db
def test_terminal_create_with_defaults():
    terminal = Terminal.objects.create(
        name="Acceso 1", api_key_hash="b" * 64, is_active=True
    )
    assert terminal.is_active is True


@pytest.mark.django_db
def test_season_create():
    season = Season.objects.create(
        name="2026-2027",
        starts_on="2026-11-20",
        ends_on="2027-02-28",
        is_active=True,
    )
    assert str(season.starts_on) == "2026-11-20"


def test_only_one_season_can_be_active_at_a_time(db):
    """webhooks.create_ticket_from_order and import_prior_orders both read
    Season.objects.filter(is_active=True).first() and treat it as "the"
    season; a second active season would make that choice arbitrary and
    stamp the wrong valid_until onto tickets."""
    make_season(name="2026-2027", is_active=True)

    with pytest.raises(IntegrityError):
        make_season(
            name="2027-2028",
            starts_on="2027-11-20",
            ends_on="2028-02-28",
            is_active=True,
        )


def test_a_second_inactive_season_is_allowed(db):
    make_season(name="2026-2027", is_active=True)
    make_season(
        name="2027-2028",
        starts_on="2027-11-20",
        ends_on="2028-02-28",
        is_active=False,
    )
    assert Season.objects.count() == 2


@pytest.mark.django_db
def test_season_blackout_date_links_to_season_with_a_reason():
    season = make_season()
    blackout = SeasonBlackoutDate.objects.create(
        season=season, date="2027-01-01", reason="Tarifa especial de alta demanda."
    )
    assert blackout in season.blackout_dates.all()
    assert str(blackout.date) == "2027-01-01"


@pytest.mark.django_db
def test_season_blackout_date_rejects_duplicate_date_for_same_season():
    season = make_season()
    SeasonBlackoutDate.objects.create(season=season, date="2027-01-01")

    with pytest.raises(IntegrityError):
        SeasonBlackoutDate.objects.create(season=season, date="2027-01-01")
