import itertools
from unittest.mock import Mock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from tickets.models import OnlineTicket
from tickets.tests.conftest import make_season
from tickets.tests.test_reconcile_orders import sample_order_dict

_order_id_counter = itertools.count(9800)


@pytest.fixture
def season(db):
    return make_season()


@pytest.fixture
def mock_woocommerce_client():
    """Replaces the WooCommerceClient the command instantiates with a
    Mock, so no test ever performs a real HTTP call to WooCommerce."""
    with patch(
        "tickets.management.commands.import_prior_orders.WooCommerceClient"
    ) as mock_cls:
        instance = Mock()
        mock_cls.return_value = instance
        yield instance


@pytest.mark.django_db
def test_import_creates_tickets_for_unused_paid_orders(mock_woocommerce_client, season):
    order_id = next(_order_id_counter)
    mock_woocommerce_client.list_paid_orders.return_value = [
        sample_order_dict(order_id=order_id)
    ]

    call_command("import_prior_orders", season_id=season.id)

    ticket = OnlineTicket.objects.get(woo_order_id=order_id)
    assert ticket.source == "IMPORT"


@pytest.mark.django_db
def test_import_does_not_email_by_default(mock_woocommerce_client, season, mailoutbox):
    order_id = next(_order_id_counter)
    mock_woocommerce_client.list_paid_orders.return_value = [
        sample_order_dict(order_id=order_id)
    ]

    call_command("import_prior_orders", season_id=season.id)

    assert len(mailoutbox) == 0


@pytest.mark.django_db
def test_import_emails_when_flag_passed(
    mock_woocommerce_client, season, mailoutbox, django_capture_on_commit_callbacks
):
    """create_ticket_from_order defers the email to transaction.on_commit
    (Task 12); django_capture_on_commit_callbacks(execute=True) is what
    makes that callback actually run inside a test's wrapping
    transaction, same as test_webhooks.py does for the webhook path."""
    order_id = next(_order_id_counter)
    mock_woocommerce_client.list_paid_orders.return_value = [
        sample_order_dict(order_id=order_id)
    ]

    with django_capture_on_commit_callbacks(execute=True):
        call_command("import_prior_orders", season_id=season.id, send_email=True)

    assert len(mailoutbox) == 1


@pytest.mark.django_db
def test_import_skips_orders_that_already_have_a_ticket(mock_woocommerce_client, season):
    from tickets.tests.conftest import make_online_ticket

    order_id = next(_order_id_counter)
    make_online_ticket(woo_order_id=order_id, season=season)
    mock_woocommerce_client.list_paid_orders.return_value = [
        sample_order_dict(order_id=order_id)
    ]

    call_command("import_prior_orders", season_id=season.id)

    assert OnlineTicket.objects.filter(woo_order_id=order_id).count() == 1


@pytest.mark.django_db
def test_import_is_idempotent_across_two_runs(mock_woocommerce_client, season):
    order_id = next(_order_id_counter)
    mock_woocommerce_client.list_paid_orders.return_value = [
        sample_order_dict(order_id=order_id)
    ]

    call_command("import_prior_orders", season_id=season.id)
    call_command("import_prior_orders", season_id=season.id)

    assert OnlineTicket.objects.filter(woo_order_id=order_id).count() == 1


@pytest.mark.django_db
def test_import_rejects_unknown_season_id(mock_woocommerce_client):
    with pytest.raises(CommandError):
        call_command("import_prior_orders", season_id=999999)

    mock_woocommerce_client.list_paid_orders.assert_not_called()


@pytest.mark.django_db
def test_import_passes_send_email_false_by_default(mock_woocommerce_client, season):
    """Proves the command actually calls create_ticket_from_order with
    send_email=False when --send-email is absent -- not merely that no
    email happens to be observed, which could pass for unrelated reasons
    (e.g. tickets.emails being unavailable)."""
    order_id = next(_order_id_counter)
    mock_woocommerce_client.list_paid_orders.return_value = [
        sample_order_dict(order_id=order_id)
    ]

    with patch(
        "tickets.management.commands.import_prior_orders.create_ticket_from_order"
    ) as mock_create:
        mock_create.return_value = Mock(source="WEBHOOK")
        call_command("import_prior_orders", season_id=season.id)

    mock_create.assert_called_once()
    _, kwargs = mock_create.call_args
    assert kwargs["send_email"] is False


@pytest.mark.django_db
def test_import_rejects_season_id_that_is_not_the_active_season(mock_woocommerce_client, season):
    """--season-id must match the currently active Season. This command
    is only meant for backfilling the active season (docs/PROYECTO.md
    5.7); create_ticket_from_order always stamps the active season onto
    new tickets regardless of --season-id, so a stale --season-id after
    a season rollover would silently mislabel tickets with the wrong
    season/valid_until unless this is rejected up front."""
    season.is_active = False
    season.save(update_fields=["is_active"])
    make_season(name="2027-2028", starts_on="2027-11-20", ends_on="2028-02-28", is_active=True)

    with pytest.raises(CommandError):
        call_command("import_prior_orders", season_id=season.id)

    mock_woocommerce_client.list_paid_orders.assert_not_called()
    assert OnlineTicket.objects.filter(season=season).count() == 0


@pytest.mark.django_db
def test_import_passes_send_email_true_when_flag_passed(mock_woocommerce_client, season):
    order_id = next(_order_id_counter)
    mock_woocommerce_client.list_paid_orders.return_value = [
        sample_order_dict(order_id=order_id)
    ]

    with patch(
        "tickets.management.commands.import_prior_orders.create_ticket_from_order"
    ) as mock_create:
        mock_create.return_value = Mock(source="WEBHOOK")
        call_command("import_prior_orders", season_id=season.id, send_email=True)

    mock_create.assert_called_once()
    _, kwargs = mock_create.call_args
    assert kwargs["send_email"] is True
