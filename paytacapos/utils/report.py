from django.contrib.postgres.fields.jsonb import KeyTransform
from django.db.models import (
    F,
    Sum,
    Count,
    CharField,
    FloatField,
    Value,
)
from django.db.models.functions import (
    Coalesce,
    Extract,
    Cast,
)
from django.apps import apps

class SalesSummary(object):
    RANGE_MONTH = "month"
    RANGE_DAY = "day"

    def __init__(self, wallet_hash="", posid=None, data=[], range_type=None, timestamp_from=None, timestamp_to=None):
        self.wallet_hash = wallet_hash
        self.posid = posid
        self.data = []
        self.range_type = range_type
        self.timestamp_from = timestamp_from
        self.timestamp_to = timestamp_to

    @classmethod
    def get_summary(
        cls,
        wallet_hash="",
        posid=None,
        summary_range="month", # "month" | "day"
        timestamp_from=None,
        timestamp_to=None,
        currency=None,
    ):
        response = cls(wallet_hash=wallet_hash)
        WalletHistory = apps.get_model("main", "WalletHistory")
        queryset = WalletHistory.objects.filter(
            record_type=WalletHistory.INCOMING,
            token__name="bch",
            wallet__wallet_hash=wallet_hash,
        )

        if isinstance(posid, int):
            response.posid = posid
            queryset = queryset.filter_pos(wallet_hash, posid=posid)
        else:
            queryset = queryset.filter_pos(wallet_hash)

        queryset = queryset.annotate(timestamp = Coalesce(F("tx_timestamp"), F("date_created")))

        if timestamp_from:
            queryset = queryset.filter(timestamp__gte=timestamp_from)
            response.timestamp_from = timestamp_from
        if timestamp_to:
            queryset = queryset.filter(timestamp__lte=timestamp_to)
            response.timestamp_to = timestamp_to

        fields = dict(
            total=Sum(F("amount")),
            count=Count(F("id")),
        )

        if currency:
            queryset = queryset.annotate(
                value=F("amount") * Cast(KeyTransform(currency, "market_prices"), FloatField()),
            )
            fields["total_market_value"] = Sum(F("value"))
            fields["currency"] = Value(currency, output_field=CharField())

        annotate = { "year": Extract("timestamp", "YEAR"), "month": Extract("timestamp", "MONTH") }
        if summary_range == cls.RANGE_DAY:
            annotate["day"] = Extract("timestamp", "DAY")
            response.range_type = cls.RANGE_DAY
        else:
            response.range_type = cls.RANGE_MONTH

        queryset = queryset.annotate(**annotate)
        queryset = queryset.values(*annotate.keys())
        queryset = queryset.order_by(*["-" + key for key in annotate.keys()])
        queryset = queryset.annotate(**fields)

        response.data = queryset.all()
        return response
