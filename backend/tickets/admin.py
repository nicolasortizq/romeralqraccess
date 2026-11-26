"""Django admin for the Phase 1 models.

This is the only interface an operator has today for provisioning a Season
and for reviewing tickets whose boleta was left PENDING_REVIEW (a ticket
redeemed whose DTE 39 could not be confirmed). That list must not be
invisible to a supervisor, hence the invoice_status filter, which is the
whole point of registering OnlineTicket here. Terminal keys are not created
here: the plaintext key is only ever shown once, by the create_terminal
management command.
"""

from django.contrib import admin

from tickets.models import (
    OnlineTicket,
    OnlineTicketLine,
    Season,
    SeasonBlackoutDate,
    Terminal,
    TicketEvent,
)


class SeasonBlackoutDateInline(admin.TabularInline):
    """So Nico or Rodrigo can add/remove a blackout date (e.g. Jan 1,
    sold presencial at a higher price) from the Season's own admin page,
    without a code change or a deploy."""

    model = SeasonBlackoutDate
    extra = 0


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ("name", "starts_on", "ends_on", "is_active")
    list_filter = ("is_active",)
    inlines = (SeasonBlackoutDateInline,)


@admin.register(Terminal)
class TerminalAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    list_filter = ("is_active",)
    # api_key_hash is shown read-only rather than hidden: an operator may
    # need to confirm a terminal has a key at all, but the hash is never
    # editable by hand -- create_terminal is the only way to set one.
    readonly_fields = ("api_key_hash",)


class OnlineTicketLineInline(admin.TabularInline):
    model = OnlineTicketLine
    extra = 0
    can_delete = False


class TicketEventInline(admin.TabularInline):
    model = TicketEvent
    extra = 0
    can_delete = False
    ordering = ("occurred_at",)


@admin.register(OnlineTicket)
class OnlineTicketAdmin(admin.ModelAdmin):
    list_display = (
        "woo_order_number",
        "buyer_name",
        "buyer_email",
        "people_count",
        "total_paid",
        "status",
        "invoice_status",
        "invoice_folio",
        "purchased_at",
    )
    list_filter = ("status", "invoice_status", "source", "season")
    search_fields = ("woo_order_number", "buyer_email", "buyer_name")
    date_hierarchy = "purchased_at"
    inlines = (OnlineTicketLineInline, TicketEventInline)
    # code_hash is never editable: the plaintext code only ever exists in
    # the buyer's email, and a changed hash would make the ticket
    # unredeemable with no way to recover it.
    readonly_fields = ("id", "code_hash", "created_at", "updated_at")
