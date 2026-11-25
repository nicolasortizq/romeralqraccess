"""Creates a gate Terminal and prints its API key once.

The gate app authenticates with X-Terminal-Key, and the backend only ever
stores the SHA-256 hash of that key (Terminal.api_key_hash), so there is no
way to read a key back afterwards. This command is therefore the only way an
operator can obtain a usable terminal key:

    python manage.py create_terminal "acceso-1"

The plaintext key is written to stdout exactly once and never logged or
stored. If it is lost, run the command again with --rotate to replace the
key of an existing terminal.
"""

import secrets

from django.core.management.base import BaseCommand, CommandError

from tickets.models import Terminal
from tickets.qr import hash_code

# 32 bytes of entropy, URL-safe, so the key can be pasted into the gate's
# config table and sent in an HTTP header without escaping.
KEY_BYTES = 32


class Command(BaseCommand):
    help = (
        "Creates a Terminal and prints its API key once to stdout. Only the "
        "key's SHA-256 hash is stored."
    )

    def add_arguments(self, parser):
        parser.add_argument("name", help="Terminal name, e.g. acceso-1.")
        parser.add_argument(
            "--rotate",
            action="store_true",
            default=False,
            help="Replace the key of an existing terminal with this name "
            "instead of refusing to run. The previous key stops working "
            "immediately.",
        )

    def handle(self, *args, **options):
        name = options["name"].strip()
        if not name:
            raise CommandError("El nombre del terminal no puede estar vacio.")

        terminal = Terminal.objects.filter(name=name).first()
        if terminal is not None and not options["rotate"]:
            raise CommandError(
                f"Ya existe un terminal llamado '{name}'. Use --rotate para "
                "reemplazar su clave (la anterior deja de funcionar)."
            )

        key = secrets.token_urlsafe(KEY_BYTES)
        if terminal is None:
            terminal = Terminal.objects.create(
                name=name, api_key_hash=hash_code(key), is_active=True
            )
            action = "creado"
        else:
            terminal.api_key_hash = hash_code(key)
            terminal.is_active = True
            terminal.save(update_fields=["api_key_hash", "is_active"])
            action = "actualizado"

        # Printed, never logged: this is the only moment the plaintext key
        # exists anywhere outside the gate PC's config table.
        self.stdout.write(f"Terminal '{terminal.name}' {action} (id={terminal.id}).")
        self.stdout.write("")
        self.stdout.write("Clave del terminal (se muestra una sola vez):")
        self.stdout.write(key)
        self.stdout.write("")
        self.stdout.write(
            "Guardela en la base del acceso con:\n"
            "  INSERT OR REPLACE INTO config VALUES ('acceso_terminal_key', "
            f"'{key}');"
        )
