import hashlib
from datetime import datetime

from django.core.paginator import EmptyPage, Paginator
from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status as http_status
from rest_framework.response import Response
from rest_framework.views import APIView

from main.models import WalletActivity


def _parse_date(date_str):
    if date_str:
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None
    return timezone.now().date()


def asset_for_history(history):
    """Return the asset identifier for a WalletHistory row.

    Returns ``'bch'`` for BCH records, ``'ct/{category}'`` for CashToken
    records, or None when the row has no recognizable asset.
    """
    if history is None:
        return None
    if history.token is not None and history.token.name == "bch":
        return "bch"
    if history.cashtoken_ft_id is not None:
        return f"ct/{history.cashtoken_ft.category}"
    if history.cashtoken_nft_id is not None:
        return f"ct/{history.cashtoken_nft.category}"
    return None


class WalletActivityReportView(APIView):
    """Return per-event WalletActivity rows for a specific UTC day.

    Each event carries the WalletActivity record id as ``event_id``,
    together with a wallet digest (sha256 of the wallet hash), the
    activity date, kind, asset (``'bch'`` or ``'ct/{category}'``), and
    (for transaction events) the on-chain txid and amount in satoshis.
    """

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter(
                name="date",
                type=openapi.TYPE_STRING,
                in_=openapi.IN_QUERY,
                description="UTC day in YYYY-MM-DD format. Defaults to today (UTC).",
            ),
            openapi.Parameter(
                name="page",
                type=openapi.TYPE_NUMBER,
                in_=openapi.IN_QUERY,
                default=1,
            ),
            openapi.Parameter(
                name="page_size",
                type=openapi.TYPE_NUMBER,
                in_=openapi.IN_QUERY,
                default=100,
            ),
        ],
    )
    def get(self, request, *args, **kwargs):
        date_str = request.query_params.get("date")
        page = request.query_params.get("page", 1)
        page_size = request.query_params.get("page_size", 100)

        try:
            page = int(page)
            page_size = int(page_size)
        except (ValueError, TypeError):
            return Response(
                {"error": "page and page_size must be integers."},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        if page < 1 or page_size < 1:
            return Response(
                {"error": "page and page_size must be positive integers."},
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        page_size = min(page_size, 1000)

        report_date = _parse_date(date_str)
        if report_date is None:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD."},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        activities = WalletActivity.objects.filter(
            activity_date=report_date,
        ).select_related(
            "wallet",
            "history",
            "history__cashtoken_ft",
            "history__cashtoken_nft",
        ).order_by("-date_created", "-id")

        pages = Paginator(activities, page_size)
        try:
            page_obj = pages.page(page)
        except EmptyPage:
            return Response(
                {"error": "Page out of range."},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        events = []
        for activity in page_obj.object_list:
            history = activity.history
            amount = None
            txid = None
            asset = None
            if history is not None:
                if history.amount is not None:
                    amount = int(round(history.amount * 100_000_000))
                txid = history.txid
                asset = asset_for_history(history)
            events.append({
                "event_id": str(activity.id),
                "wallet_digest": hashlib.sha256(
                    activity.wallet.wallet_hash.encode()
                ).hexdigest(),
                "activity_date": activity.activity_date.isoformat(),
                "kind": activity.kind,
                "asset": asset,
                "txid": txid,
                "amount": amount,
            })

        return Response({
            "results": events,
            "count": pages.count,
            "page": page,
            "page_size": page_size,
            "num_pages": pages.num_pages,
            "has_next": page_obj.has_next(),
        })
