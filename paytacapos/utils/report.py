from django.contrib.postgres.fields.jsonb import KeyTransform
from django.db.models import (
    Q,
    F,
    Sum,
    Count,
    CharField,
    FloatField,
    Value,
    Func,
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
            Q(token__name="bch") | Q(cashtoken_ft__isnull=False),
            record_type=WalletHistory.INCOMING,
            wallet__wallet_hash=wallet_hash,
        )

        if isinstance(posid, int):
            queryset = queryset.filter(pos_wallet_history__posid=posid)
            response.posid = posid
        else:
            queryset = queryset.filter(pos_wallet_history__isnull=False)

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
                decimals_mult = Cast(
                    Func(
                        Value(10),
                        Coalesce(F("cashtoken_ft__info__decimals"), Value(0)),
                        function="POWER",
                    ),
                    FloatField(),
                )
            )
            queryset = queryset.annotate(
                value=F("amount") * Cast(KeyTransform(currency, "market_prices"), FloatField()) / F("decimals_mult"),
            )
            fields["total_market_value"] = Sum(F("value"))
            fields["currency"] = Value(currency, output_field=CharField())

        annotate = { "year": Extract("timestamp", "YEAR"), "month": Extract("timestamp", "MONTH") }
        if summary_range == cls.RANGE_DAY:
            annotate["day"] = Extract("timestamp", "DAY")
            response.range_type = cls.RANGE_DAY
        else:
            response.range_type = cls.RANGE_MONTH

        annotate["asset_id"] = Coalesce(F("cashtoken_ft_id"), F("token__name"))
        fields["ft_category"] = F("cashtoken_ft_id")
        queryset = queryset.annotate(**annotate)
        queryset = queryset.values(*annotate.keys())
        queryset = queryset.order_by(*["-" + key for key in annotate.keys()])
        queryset = queryset.annotate(**fields)

        response.data = queryset.all()
        return response
