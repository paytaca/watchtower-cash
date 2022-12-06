from django.contrib.postgres.fields.jsonb import KeyTransform
from django.db.models import (
    F,
    Sum,
    Count,
    FloatField,
)
from django.db.models.functions import (
    Coalesce,
    Extract,
    Cast,
)
from django.apps import apps

class SalesSummaryException(Exception):
    pass

def get_sales_summary(
    wallet_hash="",
    posid=None,
    summary_range="month", # "month" | "day"
    timestamp_from=None,
    timestamp_to=None,
    currency=None,
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

    if timestamp_from:
        qs = qs.filter(ts__gte=timestamp_from)
    if timestamp_to:
        qs = qs.filter(ts__lte=timestamp_to)

    if currency:
        can_create = qs.filter(**{f"market_prices__{currency}__isnull": True }).exists()
        if can_create:
            raise SalesSummaryException(f"unable to create report for currency '{currency}'")
        qs = qs.annotate(
            value=F("amount") * Cast(KeyTransform(currency, "market_prices"), FloatField()),
        )
    else:
        qs = qs.annotate(value=F("amount"))

    annotate = { "year": Extract("ts", "YEAR"), "month": Extract("ts", "MONTH") }
    if summary_range == "day":
        annotate["day"] = Extract("ts", "DAY")

    qs = qs.annotate(**annotate)
    qs = qs.values(*annotate.keys())
    qs = qs.order_by(*annotate.keys())
    qs = qs.annotate(total=Sum(F("value")), count=Count(F("id")))

    return qs
