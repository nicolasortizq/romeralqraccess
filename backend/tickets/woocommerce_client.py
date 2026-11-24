"""Read-only WooCommerce REST API client.

Used by the `reconcile_orders` management command (Task 14) to catch any
paid order a lost or failed webhook delivery never turned into a ticket.
This client must only ever read from WooCommerce -- it must never create,
update or delete anything there. See docs/PROYECTO.md 5.1/5.4 for why the
webhook is the primary path and this is only a safety net.
"""

from datetime import datetime

import requests
from django.conf import settings

# Orders in either of these statuses are the ones create_ticket_from_order
# (tickets/webhooks.py) is willing to turn into a ticket -- mirrors
# PAID_STATUSES in webhooks.py.
PAID_STATUSES = "processing,completed"

PER_PAGE = 100


class WooCommerceClient:
    """Thin wrapper around GET /wp-json/wc/v3/orders.

    WooCommerce's REST API order resource and the order payload WooCommerce
    posts to the webhook URL are the same representation (id, number,
    status, total, date_paid, date_created, billing, line_items, ...), so
    list_paid_orders can hand each order straight to
    tickets.webhooks.create_ticket_from_order with no field remapping.
    """

    def __init__(self, base_url=None, api_key=None, api_secret=None, timeout=15):
        self.base_url = (base_url or settings.WOOCOMMERCE_API_URL).rstrip("/")
        self.api_key = api_key or settings.WOOCOMMERCE_API_KEY
        self.api_secret = api_secret or settings.WOOCOMMERCE_API_SECRET
        self.timeout = timeout

    def list_paid_orders(self, since: datetime) -> list[dict]:
        """Returns every order WooCommerce currently reports as paid
        (status processing or completed) and modified at or after `since`,
        paging through the REST API until it runs out of results."""
        orders = []
        page = 1
        while True:
            response = requests.get(
                f"{self.base_url}/orders",
                params={
                    "status": PAID_STATUSES,
                    "modified_after": since.isoformat(),
                    "per_page": PER_PAGE,
                    "page": page,
                },
                auth=(self.api_key, self.api_secret),
                timeout=self.timeout,
            )
            response.raise_for_status()
            page_orders = response.json()
            if not page_orders:
                break
            orders.extend(page_orders)
            if len(page_orders) < PER_PAGE:
                break
            page += 1
        return orders
