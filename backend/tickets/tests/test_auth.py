import pytest
from django.test import RequestFactory

from tickets.auth import TerminalKeyAuth, hash_key
from tickets.models import Terminal


@pytest.fixture
def request_factory():
    return RequestFactory().get("/")


@pytest.mark.django_db
def test_valid_active_terminal_key_authenticates(request_factory):
    terminal = Terminal.objects.create(
        name="Acceso 1", api_key_hash=hash_key("secret123"), is_active=True
    )
    assert TerminalKeyAuth().authenticate(request_factory, "secret123") == terminal


@pytest.mark.django_db
def test_inactive_terminal_key_is_rejected(request_factory):
    Terminal.objects.create(
        name="Acceso 1", api_key_hash=hash_key("secret123"), is_active=False
    )
    assert TerminalKeyAuth().authenticate(request_factory, "secret123") is None


@pytest.mark.django_db
def test_unknown_key_is_rejected(request_factory):
    assert TerminalKeyAuth().authenticate(request_factory, "nope") is None


@pytest.mark.django_db
def test_empty_key_is_rejected(request_factory):
    assert TerminalKeyAuth().authenticate(request_factory, "") is None
    assert TerminalKeyAuth().authenticate(request_factory, None) is None
