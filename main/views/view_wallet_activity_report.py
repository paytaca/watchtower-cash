from datetime import datetime

from django.core.paginator import Paginator
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


class WalletActivityReportView(APIView):
    """Return per-event WalletActivity rows for a specific UTC day.

    Each event carries the WalletActivity record id as ``event_id``,
    together with the wallet hash, activity date, kind, and (for
    transaction events) the on-chain txid and amount in satoshis.
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

        report_date = _parse_date(date_str)
        if report_date is None:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD."},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        activities = WalletActivity.objects.filter(
            activity_date=report_date,
        ).select_related("wallet", "history").order_by("-date_created", "-id")

        pages = Paginator(activities, page_size)
        try:
            page_obj = pages.page(page)
        except Exception:
            return Response(
                {"error": "Page out of range."},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        events = []
        for activity in page_obj.object_list:
            history = activity.history
            amount = None
            txid = None
            if history is not None:
                if history.amount is not None:
                    amount = int(history.amount * 100_000_000)
                txid = history.txid
            events.append({
                "event_id": str(activity.id),
                "wallet_hash": activity.wallet.wallet_hash,
                "activity_date": activity.activity_date.isoformat(),
                "kind": activity.kind,
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
