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
        "shift_id",
        "bch_address",
        "ramp_type",
        "date_shift_created",
        "shift_status"
    ]
