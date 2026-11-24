"""One-off operator command to backfill tickets for orders paid before
this backend existed.

This command is only for the currently active season (docs/PROYECTO.md
5.7), never a general "any past season" backfill tool: --season-id must
equal Season.objects.filter(is_active=True) or the command refuses to
run (see the active-season guard in handle() below). It exists to cover
the window before the API and webhook went live; any order paid in that
window has no OnlineTicket yet because no webhook was ever delivered for
it. Run once by hand, after WooCommerce API keys exist (external
blocker -- see docs/PROYECTO.md):

    python manage.py import_prior_orders --season-id=<id> [--send-email]

create_ticket_from_order (tickets/webhooks.py, Task 12) is called
directly rather than re-implemented here, for the same reason
reconcile_orders (Task 14) does: its get_or_create on woo_order_id is the
single source of idempotency across the webhook, the reconciliation cron
and this command, so running this command twice over an overlapping
range -- or over a range a webhook or reconcile_orders run already
covered -- never creates a duplicate ticket.

Season scoping: --season-id identifies the season being backfilled and is
used to build the WooCommerceClient query (its starts_on is the `since`
passed to list_paid_orders, matching how reconcile_orders calls the same
client method). It is not written onto the created tickets: like
reconcile_orders, this command leaves create_ticket_from_order's own
season lookup (the currently active Season) in control of the ticket's
`season` and `valid_until` fields, so all three ticket-creation paths
(webhook, reconciliation, import) agree on how a ticket's season is
decided. Because of that, --season-id is required to already be the
active season -- passing a season that used to be active (e.g. after a
rollover) would silently stamp new tickets with the now-active season's
dates instead of the one actually being backfilled, so handle() checks
this and raises CommandError rather than letting that happen quietly.
"""

from datetime import datetime, time

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from tickets.models import OnlineTicket, Season
from tickets.webhooks import create_ticket_from_order
from tickets.woocommerce_client import WooCommerceClient


class Command(BaseCommand):
    help = (
        "Imports paid WooCommerce orders from before the webhook existed, "
        "creating any ticket that is missing for them."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--season-id",
            type=int,
            required=True,
            help="Id of the Season being backfilled; its starts_on date "
            "scopes which WooCommerce orders are fetched.",
        )
        parser.add_argument(
            "--send-email",
            action="store_true",
            default=False,
            help="Also send the ticket email to each buyer. Omitted by "
            "default: a bulk historical import should not surprise "
            "buyers with an email long after their purchase.",
        )

    def handle(self, *args, **options):
        season_id = options["season_id"]
        send_email = options["send_email"]

        season = Season.objects.filter(id=season_id).first()
        if season is None:
            raise CommandError(f"No existe una temporada con id={season_id}.")

        active_season = Season.objects.filter(is_active=True).first()
        if active_season is None or active_season.id != season.id:
            raise CommandError(
                f"La temporada id={season_id} ({season.name}) no es la "
                "temporada activa. Este comando solo debe usarse para la "
                "temporada actual (ver docs/PROYECTO.md 5.7): "
                "create_ticket_from_order estampa la temporada activa en "
                "cada entrada creada sin importar --season-id, asi que "
                "correrlo con una temporada antigua despues de un cambio "
                "de temporada marcaria las entradas con la temporada y "
                "valid_until equivocados."
            )

        since = timezone.make_aware(datetime.combine(season.starts_on, time.min))
        client = WooCommerceClient()
        orders = client.list_paid_orders(since)

        created = 0
        skipped = 0
        for order in orders:
            order_id = order["id"]
            if OnlineTicket.objects.filter(woo_order_id=order_id).exists():
                skipped += 1
                continue

            ticket = create_ticket_from_order(order, send_email=send_email)
            # create_ticket_from_order always stamps source="WEBHOOK" (it
            # has no way to know who is calling it); overwrite it here so
            # an imported ticket is distinguishable in reporting, per
            # docs/PROYECTO.md's source field -- same pattern
            # reconcile_orders uses for source="RECONCILIATION". The
            # OnlineTicket.objects.filter(...).exists() check above means
            # this only runs when no ticket existed a moment ago, so the
            # only way this mislabels a webhook-created ticket is a
            # webhook delivery landing in the few milliseconds between
            # that check and this call -- accepted as a rare, low-stakes
            # race, same as in reconcile_orders.
            ticket.source = "IMPORT"
            ticket.save(update_fields=["source", "updated_at"])
            created += 1

        self.stdout.write(
            f"Importacion temporada {season.name}: {created} entrada(s) "
            f"creada(s), {skipped} ya existian (revisados {len(orders)} "
            f"pedido(s) desde {since.isoformat()})."
        )
