from django.contrib import admin

from .models import (
    Invoice,
    InvoiceOutput,
    InvoicePayment,
)

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
        "uuid",
        "time",
        "expires",
    ]

    inlines = [
        InvoiceOutputInline,
        InvoicePaymentInline,
    ]
