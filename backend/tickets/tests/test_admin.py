"""The Django admin is the only interface an operator has in Fase 1 for
provisioning a Season and for noticing a ticket left in PENDING_REVIEW.
These tests pin that down: the registration itself is the feature."""

import pytest
from django.contrib import admin

from tickets.models import OnlineTicket, Season, Terminal


def test_the_models_an_operator_must_provision_are_registered():
    for model in (Season, Terminal, OnlineTicket):
        assert model in admin.site._registry


def test_online_tickets_can_be_filtered_by_invoice_status():
    """A redeemed ticket whose boleta could not be confirmed is left
    PENDING_REVIEW. Without this filter a supervisor has no way to find
    those, which the design document names as an anti-goal."""
    options = admin.site._registry[OnlineTicket]
    assert "invoice_status" in options.list_filter
    assert "status" in options.list_filter
    assert "invoice_status" in options.list_display
    assert "status" in options.list_display


def test_a_tickets_code_hash_is_not_editable():
    """Editing the hash by hand would make the ticket permanently
    unredeemable: the plaintext code only exists in the buyer's email."""
    options = admin.site._registry[OnlineTicket]
    assert "code_hash" in options.readonly_fields


@pytest.mark.django_db
def test_a_supervisor_can_reach_the_pending_review_list(client, django_user_model):
    django_user_model.objects.create_superuser(
        username="super", email="super@example.com", password="x" * 16
    )
    client.login(username="super", password="x" * 16)

    response = client.get(
        "/admin/tickets/onlineticket/?invoice_status=PENDING_REVIEW"
    )
    assert response.status_code == 200
