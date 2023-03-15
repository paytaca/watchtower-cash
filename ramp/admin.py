from django.contrib import admin

# Register your models here.
from .models import (
    Shift
)

@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    search_fields = [
        "wallet_hash",
        "bch_address",
        "shift_status"
    ]

    list_display = [
        "wallet_hash",
        "bch_address",
        "ramp_type",
        "shift_status"
    ]