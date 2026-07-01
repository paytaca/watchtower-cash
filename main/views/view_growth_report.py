from datetime import datetime, time, timedelta

import pytz
from django.db.models import (
    ExpressionWrapper,
    F,
    FloatField,
    Q,
    Sum,
)
from django.db.models.functions import Coalesce
from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status as http_status
from rest_framework.response import Response
from rest_framework.views import APIView

from main.models import Address, Project, Wallet, WalletHistory


def _parse_date(date_str):
    if date_str:
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None
    return timezone.now().astimezone(pytz.utc).date()


def _day_bounds(report_date):
    utc = pytz.utc
    day_start = utc.localize(datetime.combine(report_date, time(0, 0, 0)))
    day_end = day_start + timedelta(days=1)
    return day_start, day_end


def _safe_div(numerator, denominator):
    if not denominator:
        return 0
    return round(numerator / denominator, 8)


class GrowthReportView(APIView):
    """Return growth-relevant aggregate metrics for a specific UTC day.

    Only BCH wallets (wallet_type='bch') and BCH transactions
    (token.name='bch') are considered; SLP and smartBCH are excluded.
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
                name="project",
                type=openapi.TYPE_STRING,
                in_=openapi.IN_QUERY,
                description="Project name to scope the report. Defaults to 'paytaca'.",
                default="paytaca",
            ),
        ],
    )
    def get(self, request, *args, **kwargs):
        date_str = request.query_params.get("date")
        project_name = request.query_params.get("project", "paytaca")

        report_date = _parse_date(date_str)
        if report_date is None:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD."},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        try:
            project = Project.objects.get(name__iexact=project_name)
        except Project.DoesNotExist:
            return Response(
                {"error": f"Project '{project_name}' not found."},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        day_start, day_end = _day_bounds(report_date)

        # ── Wallet metrics ──────────────────────────────────────────
        wallet_base = Wallet.objects.filter(
            wallet_type="bch",
            project=project,
        )
        new_wallets = wallet_base.filter(
            date_created__gte=day_start,
            date_created__lt=day_end,
        ).count()
        cumulative_wallets = wallet_base.filter(
            date_created__lt=day_end,
        ).count()
        daily_active_wallets = wallet_base.filter(
            last_balance_check__isnull=False,
            last_balance_check__gte=day_start,
            last_balance_check__lt=day_end,
        ).count()

        # ── Address metrics ─────────────────────────────────────────
        address_base = Address.objects.filter(
            wallet__wallet_type="bch",
            wallet__project=project,
        )
        new_addresses = address_base.filter(
            date_created__gte=day_start,
            date_created__lt=day_end,
        ).count()
        cumulative_addresses = address_base.filter(
            date_created__lt=day_end,
        ).count()

        # ── Transaction metrics (WalletHistory) ─────────────────────
        # Use tx_timestamp (on-chain time) with date_created fallback.
        wh_qs = (
            WalletHistory.objects
            .filter(
                wallet__wallet_type="bch",
                wallet__project=project,
                token__name__iexact="bch",
            )
            .annotate(
                effective_timestamp=Coalesce("tx_timestamp", "date_created"),
            )
            .filter(
                effective_timestamp__gte=day_start,
                effective_timestamp__lt=day_end,
            )
        )

        total_transactions = wh_qs.values("txid").distinct().count()
        incoming_transactions = wh_qs.filter(
            record_type=WalletHistory.INCOMING,
        ).count()
        outgoing_transactions = wh_qs.filter(
            record_type=WalletHistory.OUTGOING,
        ).count()
        total_records = incoming_transactions + outgoing_transactions

        # Volume aggregations
        volume_agg = wh_qs.aggregate(
            total_bch_volume=Sum("amount"),
            incoming_bch_volume=Sum(
                "amount",
                filter=Q(record_type=WalletHistory.INCOMING),
            ),
            outgoing_bch_volume=Sum(
                "amount",
                filter=Q(record_type=WalletHistory.OUTGOING),
            ),
            total_tx_fees=Sum("tx_fee"),
        )
        total_bch_volume = volume_agg["total_bch_volume"] or 0
        incoming_bch_volume = volume_agg["incoming_bch_volume"] or 0
        outgoing_bch_volume = volume_agg["outgoing_bch_volume"] or 0
        total_tx_fees = volume_agg["total_tx_fees"] or 0

        # USD volume: amount * usd_price per record
        usd_qs = wh_qs.annotate(
            usd_value=ExpressionWrapper(
                F("amount") * F("usd_price"),
                output_field=FloatField(),
            ),
        )
        usd_agg = usd_qs.aggregate(
            total_usd_volume=Sum("usd_value"),
            incoming_usd_volume=Sum(
                "usd_value",
                filter=Q(record_type=WalletHistory.INCOMING),
            ),
            outgoing_usd_volume=Sum(
                "usd_value",
                filter=Q(record_type=WalletHistory.OUTGOING),
            ),
        )
        total_usd_volume = float(usd_agg["total_usd_volume"] or 0)
        incoming_usd_volume = float(usd_agg["incoming_usd_volume"] or 0)
        outgoing_usd_volume = float(usd_agg["outgoing_usd_volume"] or 0)

        # Active wallets via transactions
        active_wallets_via_tx = (
            wh_qs.values("wallet_id").distinct().count()
        )
        active_sending_wallets = (
            wh_qs.filter(record_type=WalletHistory.OUTGOING)
            .values("wallet_id")
            .distinct()
            .count()
        )
        active_receiving_wallets = (
            wh_qs.filter(record_type=WalletHistory.INCOMING)
            .values("wallet_id")
            .distinct()
            .count()
        )

        # ── Derived / engagement metrics ────────────────────────────
        average_bch_tx_value = _safe_div(total_bch_volume, total_records)
        average_usd_tx_value = _safe_div(total_usd_volume, total_records)
        transactions_per_active_wallet = _safe_div(
            total_transactions, active_wallets_via_tx
        )
        net_bch_flow = round(incoming_bch_volume - outgoing_bch_volume, 8)

        return Response({
            "date": report_date.isoformat(),
            "project": project.name,
            "wallets": {
                "new_wallets": new_wallets,
                "cumulative_wallets": cumulative_wallets,
                "daily_active_wallets": daily_active_wallets,
                "active_wallets_via_transactions": active_wallets_via_tx,
            },
            "addresses": {
                "new_addresses": new_addresses,
                "cumulative_addresses": cumulative_addresses,
            },
            "transactions": {
                "total_transactions": total_transactions,
                "incoming_transactions": incoming_transactions,
                "outgoing_transactions": outgoing_transactions,
                "total_bch_volume": round(total_bch_volume, 8),
                "incoming_bch_volume": round(incoming_bch_volume, 8),
                "outgoing_bch_volume": round(outgoing_bch_volume, 8),
                "total_usd_volume": round(total_usd_volume, 2),
                "incoming_usd_volume": round(incoming_usd_volume, 2),
                "outgoing_usd_volume": round(outgoing_usd_volume, 2),
                "average_bch_tx_value": average_bch_tx_value,
                "average_usd_tx_value": round(average_usd_tx_value, 2),
                "total_tx_fees": round(total_tx_fees, 8),
                "active_sending_wallets": active_sending_wallets,
                "active_receiving_wallets": active_receiving_wallets,
            },
            "engagement": {
                "transactions_per_active_wallet": transactions_per_active_wallet,
                "net_bch_flow": net_bch_flow,
            },
        })
