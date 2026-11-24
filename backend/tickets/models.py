import uuid

from django.db import models


class Season(models.Model):
    """A sales season (e.g. summer 2026-2027). Online tickets are valid
    through the season they were bought in; the end date is data, not a
    constant, per the Global Constraints."""

    name = models.CharField(max_length=100)
    starts_on = models.DateField()
    ends_on = models.DateField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Terminal(models.Model):
    """A gate terminal (cashier/access point) authorized to call the API
    via the X-Terminal-Key header. Only the hash of the key is stored."""

    name = models.CharField(max_length=100)
    api_key_hash = models.CharField(max_length=64)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class OnlineTicket(models.Model):
    """One online ticket per paid WooCommerce order. The backend is the
    source of truth; the QR code itself is never stored, only its
    SHA-256 hash (code_hash)."""

    STATUS_CHOICES = (
        ("VALID", "Valida"),
        ("REDEEMED", "Canjeada"),
        ("CANCELLED", "Anulada"),
        ("REFUNDED_AFTER_REDEMPTION", "Reembolsada tras canje"),
    )

    INVOICE_STATUS_CHOICES = (
        ("NOT_ISSUED", "No emitida"),
        ("ISSUED", "Emitida"),
        ("PENDING_REVIEW", "Pendiente de revision"),
    )

    SOURCE_CHOICES = (
        ("WEBHOOK", "Webhook"),
        ("RECONCILIATION", "Conciliacion"),
        ("IMPORT", "Importacion"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code_hash = models.CharField(max_length=64, unique=True)
    woo_order_id = models.IntegerField(unique=True)
    woo_order_number = models.CharField(max_length=50)
    buyer_name = models.CharField(max_length=200)
    buyer_email = models.EmailField()
    people_count = models.PositiveIntegerField()
    total_paid = models.PositiveIntegerField(help_text="CLP, integer, no cents.")
    payment_method = models.CharField(max_length=50)
    purchased_at = models.DateTimeField()
    season = models.ForeignKey(Season, on_delete=models.PROTECT, related_name="tickets")
    valid_until = models.DateField()
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="VALID")
    redeemed_at = models.DateTimeField(null=True, blank=True)
    redeemed_by = models.CharField(max_length=100, null=True, blank=True)
    invoice_status = models.CharField(
        max_length=20, choices=INVOICE_STATUS_CHOICES, default="NOT_ISSUED"
    )
    invoice_folio = models.CharField(max_length=50, null=True, blank=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.woo_order_number} ({self.status})"


class OnlineTicketLine(models.Model):
    """One line per WooCommerce order line item, kept so a ticket's
    total and composition can be reconstructed without calling back
    to WooCommerce."""

    ticket = models.ForeignKey(
        OnlineTicket, on_delete=models.CASCADE, related_name="lines"
    )
    woo_product_id = models.IntegerField()
    product_name = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField()
    unit_price = models.PositiveIntegerField(help_text="CLP, integer.")
    line_total = models.PositiveIntegerField(help_text="CLP, integer.")

    def __str__(self):
        return f"{self.product_name} x{self.quantity}"


class TicketEvent(models.Model):
    """Audit trail entry for an OnlineTicket: created, redeemed,
    cancelled, invoice reported, etc."""

    ticket = models.ForeignKey(
        OnlineTicket, on_delete=models.CASCADE, related_name="events"
    )
    event_type = models.CharField(max_length=50)
    occurred_at = models.DateTimeField()
    terminal = models.CharField(max_length=100, blank=True)
    detail = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.event_type} ({self.ticket_id})"
