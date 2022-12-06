from django.db.models import (
    F,
    Sum,
    Count,
)
from django.db.models.functions import (
    Coalesce,
    Extract,
)
from django.apps import apps

def get_sales_summary(
    wallet_hash="",
    posid=None,
    summary_range="month", # "month" | "day"
):
    WalletHistory = apps.get_model("main", "WalletHistory")
    qs = WalletHistory.objects.filter(
        record_type=WalletHistory.INCOMING,
        token__name="bch",
        wallet__wallet_hash=wallet_hash,
    )

    if isinstance(posid, int):
        qs = qs.filter_pos(wallet_hash, posid=posid)
    else:
        qs = qs.filter_pos(wallet_hash)

    qs = qs.annotate(ts = Coalesce(F("tx_timestamp"), F("date_created")))

    annotate = { "year": Extract("ts", "YEAR"), "month": Extract("ts", "MONTH") }
    if summary_range == "day":
        annotate["day"] = Extract("ts", "DAY")

    qs = qs.annotate(**annotate)
    qs = qs.values(*annotate.keys())
    qs = qs.order_by(*annotate.keys())
    qs = qs.annotate(total=Sum(F("amount")), count=Count(F("id")))

    return qs
