import itertools
from unittest.mock import Mock, patch

import pytest
from django.core.management import call_command
from django.utils import timezone

from tickets.models import OnlineTicket
from tickets.tests.conftest import make_online_ticket, make_season

_order_id_counter = itertools.count(9900)


def sample_order_dict(order_id, total="12000", **overrides):
    """Shape matching what create_ticket_from_order (tickets/webhooks.py)
    reads from its `order` parameter. This is deliberately identical to
    the webhook payload shape used in test_webhooks.py: WooCommerce's REST
    API GET /orders endpoint returns the same order resource representation
    that WooCommerce sends as a webhook body, so WooCommerceClient hands
    these dicts to create_ticket_from_order with no remapping needed.
    """
    payload = {
        "id": order_id,
        "number": str(order_id),
        "status": "processing",
        "total": total,
        "date_paid": "2026-11-20T10:00:00",
        "date_created": "2026-11-20T09:55:00",
        "billing": {
            "first_name": "Ana",
            "last_name": "Soto",
            "email": "ana@example.com",
        },
        "line_items": [
            {
                "product_id": 10,
                "name": "Entrada general",
                "quantity": 2,
                "price": "6000",
                "total": total,
            }
        ],
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def mock_woocommerce_client():
    """Replaces the WooCommerceClient the command instantiates with a
    Mock, so no test ever performs a real HTTP call to WooCommerce."""
    with patch(
        "tickets.management.commands.reconcile_orders.WooCommerceClient"
    ) as mock_cls:
        instance = Mock()
        mock_cls.return_value = instance
        yield instance


@pytest.mark.django_db
def test_reconcile_creates_tickets_for_paid_orders_without_one(mock_woocommerce_client):
    make_season()
    order_id = next(_order_id_counter)
    mock_woocommerce_client.list_paid_orders.return_value = [
        sample_order_dict(order_id=order_id)
    ]

    call_command("reconcile_orders")

    ticket = OnlineTicket.objects.get(woo_order_id=order_id)
    assert ticket.source == "RECONCILIATION"


@pytest.mark.django_db
def test_reconcile_skips_orders_that_already_have_a_ticket(mock_woocommerce_client):
    order_id = next(_order_id_counter)
    make_online_ticket(woo_order_id=order_id)
    mock_woocommerce_client.list_paid_orders.return_value = [
        sample_order_dict(order_id=order_id)
    ]

    call_command("reconcile_orders")

    assert OnlineTicket.objects.filter(woo_order_id=order_id).count() == 1


@pytest.mark.django_db
def test_reconcile_is_idempotent_across_two_runs(mock_woocommerce_client):
    """Running the command twice for the same unprocessed order must not
    create a second ticket -- this is what protects the real cron job
    (every 10 minutes, Task 17) from ever double-creating a ticket."""
    make_season()
    order_id = next(_order_id_counter)
    mock_woocommerce_client.list_paid_orders.return_value = [
        sample_order_dict(order_id=order_id)
    ]

    call_command("reconcile_orders")
    call_command("reconcile_orders")

    assert OnlineTicket.objects.filter(woo_order_id=order_id).count() == 1


@pytest.mark.django_db
def test_reconcile_queries_with_a_lookback_window_in_the_past(mock_woocommerce_client):
    mock_woocommerce_client.list_paid_orders.return_value = []

    call_command("reconcile_orders")

    mock_woocommerce_client.list_paid_orders.assert_called_once()
    (since,), _ = mock_woocommerce_client.list_paid_orders.call_args
    assert since < timezone.now()
