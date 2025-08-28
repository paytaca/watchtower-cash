from django.contrib import admin
from django.contrib import messages

from .models import (
    Invoice,
    InvoiceOutput,
    InvoicePayment,
)
from .utils.notification import send_invoice_push_notification

# Register your models here.

class InvoicePaymentInline(admin.StackedInline):
    model = InvoicePayment
    extra = 0

class InvoiceOutputInline(admin.TabularInline):
    model = InvoiceOutput
    extra = 0

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = [
        "__str__",
        "uuid",
        "time",
        "expires",
        "get_payment_txid",
    ]

    inlines = [
        InvoiceOutputInline,
        InvoicePaymentInline,
    ]

    actions = [
        "send_push_notification",
    ]

    search_fields = [
        "merchant_data",
        "uuid",
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("payment")

    def get_payment_txid(self, obj):
        try:
            return obj.payment.txid
        except Invoice.payment.RelatedObjectDoesNotExist:
            pass
    get_payment_txid.short_description = 'Payment TXID'
    get_payment_txid.admin_order_field = 'payment__txid'

    def send_push_notification(self, request, queryset):
        for obj in queryset:
            try:
                if obj.payment.txid:
                    messages.info(request, f"{obj} -> Paid already: {obj.payment.txid}")
                    continue
            except Invoice.payment.RelatedObjectDoesNotExist:
                pass
            result = send_invoice_push_notification(obj, request)
            messages.info(request, f"{obj} -> {result}")

