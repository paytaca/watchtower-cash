from django.contrib import admin

# Register your models here.
from .models import (
    Memo
)


@admin.register(Memo)
class MemoAdmin(admin.ModelAdmin):    
    list_display = [
        "txid",
        "created_at",
        "wallet_hash"
    ]
