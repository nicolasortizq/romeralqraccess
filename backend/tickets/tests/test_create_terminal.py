"""The create_terminal command is the only way to obtain a usable terminal
key: the backend stores only the key's SHA-256 hash, so a key that is not
captured from this command's output is gone."""

import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from tickets.models import Terminal
from tickets.qr import hash_code


def _run(*args, **kwargs):
    out = io.StringIO()
    call_command("create_terminal", *args, stdout=out, **kwargs)
    return out.getvalue()


def _key_from_output(output, terminal):
    """Picks the plaintext key out of the command's output by hashing every
    printed token and matching it against what was stored. Deliberately not
    "the Nth line": the test must not depend on the output's layout."""
    tokens = [token for line in output.splitlines() for token in line.split()]
    for token in tokens:
        if hash_code(token) == terminal.api_key_hash:
            return token
    raise AssertionError(f"No printed token hashes to the stored key:\n{output}")


@pytest.mark.django_db
def test_it_creates_a_terminal_and_prints_a_key_that_matches_the_stored_hash():
    output = _run("acceso-1")

    terminal = Terminal.objects.get(name="acceso-1")
    assert terminal.is_active

    # The printed key is the only copy; it must be the one that
    # authenticates against the stored hash.
    key = _key_from_output(output, terminal)
    assert len(key) >= 32


@pytest.mark.django_db
def test_the_plaintext_key_is_never_stored():
    output = _run("acceso-1")
    terminal = Terminal.objects.get(name="acceso-1")
    key = _key_from_output(output, terminal)

    assert key != terminal.api_key_hash
    assert key not in terminal.api_key_hash


@pytest.mark.django_db
def test_it_refuses_to_silently_replace_an_existing_terminals_key():
    _run("acceso-1")
    original_hash = Terminal.objects.get(name="acceso-1").api_key_hash

    with pytest.raises(CommandError):
        _run("acceso-1")

    assert Terminal.objects.get(name="acceso-1").api_key_hash == original_hash


@pytest.mark.django_db
def test_rotate_replaces_the_key_of_an_existing_terminal():
    _run("acceso-1")
    original_hash = Terminal.objects.get(name="acceso-1").api_key_hash

    _run("acceso-1", rotate=True)

    assert Terminal.objects.count() == 1
    assert Terminal.objects.get(name="acceso-1").api_key_hash != original_hash


@pytest.mark.django_db
def test_the_created_key_authenticates_against_the_api(client):
    output = _run("acceso-1")
    terminal = Terminal.objects.get(name="acceso-1")
    key = _key_from_output(output, terminal)

    # 404 (not 401) proves the key was accepted and only the ticket is
    # missing.
    response = client.get(
        "/api/v1/tickets/VR1DOESNOTEXIST", headers={"X-Terminal-Key": key}
    )
    assert response.status_code == 404
