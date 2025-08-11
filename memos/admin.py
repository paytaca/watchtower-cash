from django.contrib import admin

# Register your models here.
from .models import (
    Memo
)


@admin.register(Memo)
class ShiftAdmin(admin.ModelAdmin):    
    list_display = [
        "wallet_hash",
        "created_at",
        "note",
        "txid"
    ]
