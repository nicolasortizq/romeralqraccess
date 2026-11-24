"""Safety net for lost WooCommerce webhook deliveries.

Polls the WooCommerce REST API for orders paid within a lookback window
and creates any ticket a webhook delivery never produced. Run every 10
minutes by cron (deploy/crontab.txt, Task 17):

    python manage.py reconcile_orders

create_ticket_from_order (tickets/webhooks.py, Task 12) is called
directly rather than re-implemented here: its get_or_create on
woo_order_id is the single source of idempotency for both the webhook and
this command, so running this command twice -- or running it over a
window that overlaps a webhook that already succeeded -- never creates a
duplicate ticket.

A single order that cannot be processed is logged, counted and skipped;
the batch continues and the command exits non-zero at the end, so cron and
monitoring see the failure without the rest of the window being dropped.
"""

import logging

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from tickets.models import OnlineTicket
from tickets.webhooks import create_ticket_from_order
from tickets.woocommerce_client import WooCommerceClient

# How far back to look on every run. The cron interval itself is 10
# minutes, but a wider window is used here so that one missed run, a slow
# deploy, or a stretch of WooCommerce/network downtime does not cause an
# order to be silently skipped forever -- create_ticket_from_order's own
# idempotency check is what makes a wider, overlapping window safe.
LOOKBACK_HOURS = 6

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Reconciles paid WooCommerce orders against OnlineTicket, "
        "creating any ticket a lost webhook delivery never produced."
    )

    def handle(self, *args, **options):
        since = timezone.now() - timezone.timedelta(hours=LOOKBACK_HOURS)
        client = WooCommerceClient()
        orders = client.list_paid_orders(since)

        created = 0
        skipped = 0
        failed = 0
        for order in orders:
            order_id = order.get("id")
            # One malformed or unprocessable order must not cost the batch
            # every order behind it: this runs unattended from cron, and
            # aborting on the first failure would leave the rest of the
            # window unreconciled until someone noticed.
            try:
                if OnlineTicket.objects.filter(woo_order_id=order_id).exists():
                    skipped += 1
                    continue

                ticket = create_ticket_from_order(order)
                # create_ticket_from_order always stamps source="WEBHOOK"
                # (it has no way to know who is calling it); overwrite it
                # here so a ticket this safety net created is
                # distinguishable in reporting, per docs/PROYECTO.md's
                # source field. The
                # OnlineTicket.objects.filter(...).exists() check above
                # means this only runs when no ticket existed a moment
                # ago, so the only way this mislabels a webhook-created
                # ticket is a webhook delivery landing in the few
                # milliseconds between that check and this call --
                # accepted as a rare, low-stakes race rather than
                # extending create_ticket_from_order's signature (Task 14
                # brief: do not modify webhooks.py).
                ticket.source = "RECONCILIATION"
                ticket.save(update_fields=["source", "updated_at"])
                created += 1
            except Exception:
                failed += 1
                logger.exception(
                    "Reconciliation failed for WooCommerce order %s", order_id
                )
                self.stderr.write(
                    f"Error al reconciliar el pedido {order_id}; se continua "
                    "con el resto."
                )

        self.stdout.write(
            f"Reconciliacion: {created} entrada(s) creada(s), {skipped} ya "
            f"existian, {failed} con error (revisados {len(orders)} "
            f"pedido(s) desde {since.isoformat()})."
        )

        if failed:
            # Non-zero exit so cron mail and any monitoring notice, instead
            # of a run that "succeeded" while silently dropping orders.
            raise CommandError(
                f"{failed} pedido(s) no se pudieron reconciliar; ver el log "
                "de tickets para el detalle."
            )
