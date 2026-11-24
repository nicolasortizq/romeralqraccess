"""WooCommerce order webhook: signature verification and the order-to-
ticket creation/cancellation logic behind it.

WooCommerce sends every order create/update to this one URL; there is no
separate event type for cancellation, so we branch on the order's current
`status` field. See docs/PROYECTO.md 5.1 for the flow this implements.
"""

import base64
import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from tickets.models import OnlineTicket, OnlineTicketLine, Season, TicketEvent
from tickets.qr import generate_code, hash_code

logger = logging.getLogger(__name__)

# tickets.emails (Task 13) is implemented after this task in the plan's
# dependency order. create_ticket_from_order calls it only when sending an
# email was requested, so a missing module never blocks ticket creation --
# we just log and skip the email, once, here, rather than at every call site.
try:
    from tickets import emails
except ImportError:
    emails = None

PAID_STATUSES = {"processing", "completed"}
CANCEL_STATUSES = {"cancelled", "refunded"}


def verify_wc_signature(raw_body: bytes, header_value: str) -> bool:
    """Checks X-WC-Webhook-Signature: base64(HMAC-SHA256(raw body, secret)).

    Compares with hmac.compare_digest so a timing attack can't be used to
    recover the secret byte by byte. An empty secret or empty header is
    always rejected rather than compared (an unconfigured secret must not
    make every request "valid").
    """
    secret = settings.WOOCOMMERCE_WEBHOOK_SECRET
    if not secret or not header_value:
        return False
    digest = hmac.new(secret.encode(), raw_body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected, header_value)


def _parse_purchased_at(order: dict):
    raw = order.get("date_paid") or order.get("date_created")
    dt = parse_datetime(raw) if raw else None
    if dt is None:
        return timezone.now()
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt


def create_ticket_from_order(order: dict, send_email: bool = True) -> OnlineTicket:
    """Creates one OnlineTicket (plus one OnlineTicketLine per line item)
    from a WooCommerce order payload. Idempotent on woo_order_id: calling
    it twice for the same order returns the existing ticket both times and
    creates nothing extra.

    Tasks 14 (reconciliation) and 15 (resend) import this directly instead
    of re-implementing order-to-ticket mapping.
    """
    order_id = order["id"]

    existing = OnlineTicket.objects.filter(woo_order_id=order_id).first()
    if existing is not None:
        return existing

    season = Season.objects.filter(is_active=True).first()
    if season is None:
        # Not expected in production -- there should always be exactly one
        # active season -- but fail loudly rather than guess a season.
        raise ValueError(
            f"No hay temporada activa; no se puede crear la entrada del "
            f"pedido {order_id}."
        )

    billing = order.get("billing") or {}
    buyer_name = f"{billing.get('first_name', '')} {billing.get('last_name', '')}".strip()
    line_items = order.get("line_items") or []
    people_count = sum(int(item.get("quantity", 0)) for item in line_items) or 1

    code = generate_code()

    # get_or_create's create() runs inside its own atomic block and relies
    # on the unique constraint on woo_order_id: if two webhook deliveries
    # for the same order race past the `existing` check above, only one
    # INSERT succeeds and the other call gets IntegrityError -> re-fetches
    # and returns that row instead of raising. So at most one ticket is
    # ever created per order even under a true race.
    ticket, created = OnlineTicket.objects.get_or_create(
        woo_order_id=order_id,
        defaults=dict(
            code_hash=hash_code(code),
            woo_order_number=str(order.get("number", order_id)),
            buyer_name=buyer_name,
            buyer_email=billing.get("email", ""),
            people_count=people_count,
            total_paid=round(float(order.get("total", 0) or 0)),
            payment_method="Webpay",
            purchased_at=_parse_purchased_at(order),
            season=season,
            valid_until=season.ends_on,
            status="VALID",
            source="WEBHOOK",
        ),
    )

    if not created:
        return ticket

    OnlineTicketLine.objects.bulk_create(
        OnlineTicketLine(
            ticket=ticket,
            woo_product_id=item.get("product_id", 0),
            product_name=item.get("name", ""),
            quantity=int(item.get("quantity", 0)),
            unit_price=round(float(item.get("price", 0) or 0)),
            line_total=round(float(item.get("total", 0) or 0)),
        )
        for item in line_items
    )

    TicketEvent.objects.create(
        ticket=ticket,
        event_type="creada",
        occurred_at=timezone.now(),
        detail={"woo_order_id": order_id},
    )

    if send_email:
        if emails is not None:
            try:
                emails.send_ticket_email(ticket, code)
            except Exception:
                # A failed email must not undo an already-paid ticket; the
                # buyer can still be found by order number or email.
                logger.exception(
                    "Failed to send ticket email for order %s", order_id
                )
        else:
            logger.info(
                "tickets.emails not available yet; skipped email for order %s",
                order_id,
            )

    return ticket


def _cancel_or_refund_ticket(order_id) -> None:
    """Handles a cancelled/refunded order for an order that already has a
    ticket. Locks the row with select_for_update() because this can race
    with a gate redeeming the same ticket (Task 10's redeem endpoint uses
    the same lock)."""
    with transaction.atomic():
        ticket = (
            OnlineTicket.objects.select_for_update()
            .filter(woo_order_id=order_id)
            .first()
        )
        if ticket is None:
            return

        now = timezone.now()
        if ticket.status == "VALID":
            ticket.status = "CANCELLED"
            ticket.save(update_fields=["status", "updated_at"])
            TicketEvent.objects.create(
                ticket=ticket,
                event_type="anulada",
                occurred_at=now,
                detail={"woo_order_id": order_id},
            )
        elif ticket.status == "REDEEMED":
            # Boleta already issued for this ticket; Fase 3 settles the
            # accounting side. Fase 1 only needs the state visible and
            # distinct from a plain cancellation.
            ticket.status = "REFUNDED_AFTER_REDEMPTION"
            ticket.save(update_fields=["status", "updated_at"])
            TicketEvent.objects.create(
                ticket=ticket,
                event_type="reembolsada tras canje",
                occurred_at=now,
                detail={"woo_order_id": order_id},
            )
        # CANCELLED or REFUNDED_AFTER_REDEMPTION already -- no-op, this
        # delivery is a duplicate or a second cancel/refund event.


@csrf_exempt
@require_POST
def woocommerce_webhook(request) -> HttpResponse:
    """POST /api/v1/woocommerce/webhook -- the single URL WooCommerce calls
    for every order create/update. There is no separate "cancelled" event;
    we branch on the order's current status field instead."""
    raw_body = request.body
    signature = request.headers.get("X-WC-Webhook-Signature", "")
    if not verify_wc_signature(raw_body, signature):
        return JsonResponse({"detail": "Firma inválida."}, status=401)

    try:
        order = json.loads(raw_body)
    except ValueError:
        return JsonResponse({"detail": "JSON inválido."}, status=400)

    status = order.get("status")
    order_id = order.get("id")

    if status in PAID_STATUSES:
        create_ticket_from_order(order)
    elif status in CANCEL_STATUSES:
        _cancel_or_refund_ticket(order_id)
    # Any other status (pending, on-hold, failed, draft, ...) is not yet
    # a paid order and not a cancellation either -- nothing to do.

    return JsonResponse({"ok": True})
