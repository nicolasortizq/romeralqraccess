from datetime import date, datetime
from typing import Optional
from uuid import UUID

from django.db import transaction
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError

from tickets.auth import TerminalKeyAuth
from tickets.models import OnlineTicket, TicketEvent
from tickets.qr import hash_code

router = Router(auth=TerminalKeyAuth())

# Human-readable reasons for each non-redeemable status, used in the 409
# response so the cashier screen can show why a code was rejected.
_NOT_REDEEMABLE_REASONS = {
    "REDEEMED": "Esta entrada ya fue canjeada.",
    "CANCELLED": "Esta entrada esta anulada.",
    "REFUNDED_AFTER_REDEMPTION": "Esta entrada fue reembolsada tras el canje.",
}


class OnlineTicketLineOut(Schema):
    woo_product_id: int
    product_name: str
    quantity: int
    unit_price: int
    line_total: int


class OnlineTicketOut(Schema):
    """Mirrors the OnlineTicket schema in docs/api/openapi.yaml, plus the
    derived, read-only display_status field."""

    id: UUID
    woo_order_id: int
    woo_order_number: str
    buyer_name: str
    buyer_email: str
    people_count: int
    total_paid: int
    payment_method: str
    purchased_at: datetime
    season_id: int
    valid_until: date
    status: str
    redeemed_at: Optional[datetime] = None
    redeemed_by: Optional[str] = None
    invoice_status: str
    invoice_folio: Optional[str] = None
    source: str
    created_at: datetime
    updated_at: datetime
    lines: list[OnlineTicketLineOut]
    display_status: Optional[str] = None

    @staticmethod
    def resolve_display_status(obj) -> Optional[str]:
        # The stored status stays VALID until redemption or cancellation;
        # a ticket whose season has ended without being redeemed is still
        # VALID in the database but must no longer be presented as usable.
        if obj.status == "VALID" and timezone.localdate() > obj.valid_until:
            return "fuera de temporada"
        return None


@router.get("/{code}", response=OnlineTicketOut)
def get_ticket_by_code(request, code: str):
    ticket = OnlineTicket.objects.filter(code_hash=hash_code(code)).first()
    if ticket is None:
        raise HttpError(404, "No existe ninguna entrada con ese código.")
    return ticket


class RedeemIn(Schema):
    terminal: str
    redeemed_by: str


@router.post("/{code}/redeem", response=OnlineTicketOut)
def redeem_ticket(request, code: str, payload: RedeemIn):
    code_hash = hash_code(code)
    with transaction.atomic():
        # select_for_update() takes a row lock held for the rest of this
        # transaction: a second concurrent request for the same code blocks
        # here until the first commits, then re-reads the now-REDEEMED row
        # under its own lock and gets 409 instead of racing past this check.
        ticket = (
            OnlineTicket.objects.select_for_update()
            .filter(code_hash=code_hash)
            .first()
        )
        if ticket is None:
            raise HttpError(404, "No existe ninguna entrada con ese código.")

        if ticket.status != "VALID":
            reason = _NOT_REDEEMABLE_REASONS.get(
                ticket.status, "Esta entrada no se puede canjear."
            )
            raise HttpError(409, reason)

        now = timezone.now()
        ticket.status = "REDEEMED"
        ticket.redeemed_at = now
        ticket.redeemed_by = payload.redeemed_by
        ticket.save(update_fields=["status", "redeemed_at", "redeemed_by", "updated_at"])

        TicketEvent.objects.create(
            ticket=ticket,
            event_type="canjeada",
            occurred_at=now,
            terminal=payload.terminal,
            detail={"redeemed_by": payload.redeemed_by},
        )

    return ticket


@router.get("", response=list[OnlineTicketOut])
def search_tickets(
    request, order: Optional[str] = None, email: Optional[str] = None
):
    if not order and not email:
        raise HttpError(400, "Debe indicar order o email.")

    tickets = OnlineTicket.objects.all()
    if order:
        tickets = tickets.filter(woo_order_number=order)
    if email:
        tickets = tickets.filter(buyer_email=email)
    return tickets
