import base64
import hashlib
import hmac
import itertools
import json

import pytest
from django.core.serializers.json import DjangoJSONEncoder

from tickets.models import OnlineTicket, TicketEvent
from tickets.tests.conftest import make_online_ticket, make_season

_order_id_counter = itertools.count(9000)


def sample_order_payload(order_id, status, total="12000", **overrides):
    """Builds a minimal WooCommerce order webhook payload. Field names and
    nesting mirror the real WooCommerce REST order object (billing,
    line_items), trimmed to what create_ticket_from_order reads."""
    payload = {
        "id": order_id,
        "number": str(order_id),
        "status": status,
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


def compute_wc_signature(payload, secret):
    """Mirrors verify_wc_signature: HMAC-SHA256 of the exact bytes Django's
    test client sends as the request body, base64-encoded."""
    body = json.dumps(payload, cls=DjangoJSONEncoder).encode()
    digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def _post(client, payload, signature=None):
    headers = {}
    if signature is not None:
        headers["X-WC-Webhook-Signature"] = signature
    return client.post(
        "/api/v1/woocommerce/webhook",
        data=payload,
        content_type="application/json",
        headers=headers,
    )


@pytest.mark.django_db
def test_webhook_with_valid_signature_creates_ticket(client, settings):
    settings.WOOCOMMERCE_WEBHOOK_SECRET = "shhh"
    make_season()
    order_id = next(_order_id_counter)
    payload = sample_order_payload(order_id=order_id, status="processing", total="12000")
    signature = compute_wc_signature(payload, "shhh")

    resp = _post(client, payload, signature)

    assert resp.status_code == 200
    assert OnlineTicket.objects.filter(woo_order_id=order_id).exists()
    ticket = OnlineTicket.objects.get(woo_order_id=order_id)
    assert ticket.source == "WEBHOOK"
    assert ticket.status == "VALID"
    assert ticket.lines.count() == 1


@pytest.mark.django_db
def test_webhook_with_missing_signature_is_rejected(client, settings):
    settings.WOOCOMMERCE_WEBHOOK_SECRET = "shhh"
    order_id = next(_order_id_counter)
    payload = sample_order_payload(order_id=order_id, status="processing")

    resp = _post(client, payload, signature=None)

    assert resp.status_code == 401
    assert not OnlineTicket.objects.filter(woo_order_id=order_id).exists()


@pytest.mark.django_db
def test_webhook_with_wrong_signature_is_rejected(client, settings):
    settings.WOOCOMMERCE_WEBHOOK_SECRET = "shhh"
    order_id = next(_order_id_counter)
    payload = sample_order_payload(order_id=order_id, status="processing")

    resp = _post(client, payload, signature="wrong")

    assert resp.status_code == 401
    assert not OnlineTicket.objects.filter(woo_order_id=order_id).exists()


@pytest.mark.django_db
def test_webhook_is_idempotent_on_duplicate_order_id(client, settings):
    settings.WOOCOMMERCE_WEBHOOK_SECRET = "shhh"
    make_season()
    order_id = next(_order_id_counter)
    payload = sample_order_payload(order_id=order_id, status="processing")
    signature = compute_wc_signature(payload, "shhh")

    first = _post(client, payload, signature)
    second = _post(client, payload, signature)

    assert first.status_code == 200
    assert second.status_code == 200
    assert OnlineTicket.objects.filter(woo_order_id=order_id).count() == 1


@pytest.mark.django_db
def test_webhook_cancels_an_unredeemed_ticket(client, settings):
    settings.WOOCOMMERCE_WEBHOOK_SECRET = "shhh"
    order_id = next(_order_id_counter)
    make_online_ticket(woo_order_id=order_id, status="VALID")
    payload = sample_order_payload(order_id=order_id, status="cancelled")
    signature = compute_wc_signature(payload, "shhh")

    resp = _post(client, payload, signature)

    assert resp.status_code == 200
    ticket = OnlineTicket.objects.get(woo_order_id=order_id)
    assert ticket.status == "CANCELLED"
    assert TicketEvent.objects.filter(ticket=ticket, event_type="anulada").exists()


@pytest.mark.django_db
def test_webhook_refund_after_redemption_does_not_cancel(client, settings):
    settings.WOOCOMMERCE_WEBHOOK_SECRET = "shhh"
    order_id = next(_order_id_counter)
    make_online_ticket(woo_order_id=order_id, status="REDEEMED")
    payload = sample_order_payload(order_id=order_id, status="refunded")
    signature = compute_wc_signature(payload, "shhh")

    resp = _post(client, payload, signature)

    assert resp.status_code == 200
    ticket = OnlineTicket.objects.get(woo_order_id=order_id)
    assert ticket.status == "REFUNDED_AFTER_REDEMPTION"
    assert TicketEvent.objects.filter(
        ticket=ticket, event_type="reembolsada tras canje"
    ).exists()


@pytest.mark.django_db
def test_webhook_cancel_with_no_existing_ticket_is_a_noop(client, settings):
    settings.WOOCOMMERCE_WEBHOOK_SECRET = "shhh"
    order_id = next(_order_id_counter)
    payload = sample_order_payload(order_id=order_id, status="cancelled")
    signature = compute_wc_signature(payload, "shhh")

    resp = _post(client, payload, signature)

    assert resp.status_code == 200
    assert not OnlineTicket.objects.filter(woo_order_id=order_id).exists()


@pytest.mark.django_db
def test_webhook_already_cancelled_ticket_stays_cancelled(client, settings):
    settings.WOOCOMMERCE_WEBHOOK_SECRET = "shhh"
    order_id = next(_order_id_counter)
    make_online_ticket(woo_order_id=order_id, status="CANCELLED")
    payload = sample_order_payload(order_id=order_id, status="cancelled")
    signature = compute_wc_signature(payload, "shhh")

    resp = _post(client, payload, signature)

    assert resp.status_code == 200
    ticket = OnlineTicket.objects.get(woo_order_id=order_id)
    assert ticket.status == "CANCELLED"
