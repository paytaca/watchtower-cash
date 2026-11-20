from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.decorators import action

from django.utils import timezone
from django.http import Http404
from django.core.exceptions import ValidationError
from django.db.models import (
    Q,
    Count,
    F,
    Value,
    ExpressionWrapper,
    DecimalField,
    Case,
    Func,
    When,
    OuterRef,
    Subquery,
    IntegerField,
    Avg,
)
from django.db.models.functions import Coalesce
from django.conf import settings
from django.views import View
from django.shortcuts import render

import math
from datetime import timedelta
from authentication.token import TokenAuthentication
from authentication.permissions import RampP2PIsAuthenticated
from rest_framework.exceptions import PermissionDenied
from rampp2p.order_access import order_participant_filter, require_order_participant
from decimal import Decimal

import rampp2p.serializers as serializers
import rampp2p.models as models
from rampp2p.feature_control import require_p2p_feature
import rampp2p.utils.websocket as websocket
from rampp2p.utils import bch_to_satoshi
from rampp2p.utils.notifications import clear_ad_unavailable_reminders

import logging

logger = logging.getLogger(__name__)


class Round(Func):
    function = "ROUND"
    template = "%(function)s(%(expressions)s, 8)"


class AdViewSet(viewsets.GenericViewSet):
    authentication_classes = [TokenAuthentication]
    permission_classes = [RampP2PIsAuthenticated]
    queryset = models.Ad.objects.filter(deleted_at__isnull=True)

    def get_object(self, pk):
        Ad = models.Ad
        try:
            ad = Ad.objects.get(pk=pk)
            if ad.deleted_at is not None:
                raise Ad.DoesNotExist
            return ad
        except Ad.DoesNotExist:
            raise Http404

    def fetch_queryset(self, request=None, pk=None):
        if request is None:
            return []

        response_data = None
        if pk:
            ad = self.get_object(pk)
            wallet_hash = request.user.wallet_hash
            context = {"wallet_hash": wallet_hash}
            serializer = serializers.AdSerializer(ad, context=context).data
            response_data = serializer
        else:
            queryset = models.Ad.objects.filter(
                Q(deleted_at__isnull=True)
                & Q(owner__is_disabled=False)
            )
            wallet_hash = request.headers.get("wallet_hash")
            owner_id = request.query_params.get("owner_id")
            currency = request.query_params.get("currency")
            trade_type = request.query_params.get("trade_type")
            price_types = request.query_params.getlist("price_types")
            payment_types = request.query_params.getlist("payment_types")
            time_limits = request.query_params.getlist("time_limits")
            price_order = request.query_params.get("price_order")
            order_by = request.query_params.get("order_by")
            query_name = request.query_params.get("query_name")
            order_amount = request.query_params.get("order_amount")
            order_amount_currency = request.query_params.get("order_amount_currency")
            owned = request.query_params.get("owned", False)
            owned = owned == "true"

            try:
                limit = int(request.query_params.get("limit", 0))
                page = int(request.query_params.get("page", 1))
            except ValueError as err:
                raise ValidationError(err.args[0])

            if limit < 0:
                raise ValidationError("limit must be a non-negative number")

            if page < 1:
                raise ValidationError("invalid page number")

            if not owned:
                # If not fetching owned ads: fetch only public ads and those with trade amount > 0
                queryset = queryset.filter(
                    Q(is_public=True)
                    & (
                        (Q(trade_limits_in_fiat=False) & Q(trade_amount_sats__gte=1000))
                        | (Q(trade_limits_in_fiat=True) & Q(trade_amount_fiat__gt=0))
                    )
                    & (Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
                )

            # filters
            if owner_id is not None:
                queryset = queryset.filter(owner_id=owner_id)

            if currency is not None:
                queryset = queryset.filter(Q(fiat_currency__symbol=currency))

            if trade_type is not None:
                queryset = queryset.filter(Q(trade_type=trade_type))

            if len(price_types) > 0:
                queryset = queryset.filter(Q(price_type__in=price_types))

            if len(payment_types) > 0:
                payment_types = list(map(int, payment_types))
                queryset = queryset.filter(
                    payment_methods__payment_type__id__in=payment_types
                ).distinct()

            if len(time_limits) > 0:
                time_limits = list(map(int, time_limits))
                queryset = queryset.filter(
                    appeal_cooldown_choice__in=time_limits
                ).distinct()

            market_rate_subq = models.MarketPrice.objects.filter(
                currency=OuterRef("fiat_currency__symbol")
            ).values("price")[:1]
            queryset = queryset.annotate(market_rate=Subquery(market_rate_subq))

            # Annotate to compute ad price based on price type (FIXED vs FLOATING)
            queryset = queryset.annotate(
                price=ExpressionWrapper(
                    Case(
                        When(
                            price_type=models.PriceType.FLOATING,
                            then=(F("floating_price") / 100 * F("market_rate")),
                        ),
                        default=F("fixed_price"),
                        output_field=DecimalField(),
                    ),
                    output_field=DecimalField(),
                )
            )

            if order_amount and order_amount_currency:
                if order_amount_currency == "BCH":
                    order_amount_sats = bch_to_satoshi(order_amount)
                    queryset = queryset.annotate(
                        order_amount_fiat=ExpressionWrapper(
                            order_amount * F("price"), output_field=DecimalField()
                        )
                    ).filter(
                        (
                            Q(trade_limits_in_fiat=False)
                            & Q(trade_floor_sats__lte=order_amount_sats)
                            & Q(trade_ceiling_sats__gte=order_amount_sats)
                        )
                        | (
                            Q(trade_limits_in_fiat=True)
                            & Q(trade_floor_fiat__lte=F("order_amount_fiat"))
                            & Q(trade_ceiling_fiat__gte=F("order_amount_fiat"))
                        )
                    )
                else:
                    queryset = queryset.annotate(
                        order_amount_sats=ExpressionWrapper(
                            (order_amount / F("price")) * settings.SATOSHI_PER_BCH,
                            output_field=IntegerField(),
                        )
                    ).filter(
                        (
                            Q(trade_limits_in_fiat=True)
                            & Q(trade_floor_fiat__lte=order_amount)
                            & Q(trade_ceiling_fiat__gte=order_amount)
                        )
                        | (
                            Q(trade_limits_in_fiat=False)
                            & Q(trade_floor_sats__lte=F("order_amount_sats"))
                            & Q(trade_ceiling_sats__gte=F("order_amount_sats"))
                        )
                    )

            # search for ads with specific owner name
            if query_name:
                queryset = queryset.filter(owner__name__icontains=query_name)

            """ Orders ads by price (if owned=True) or by created_at (if owned=False).
                Default order is ascending, descending if trade type is BUY. 
                price_order filter overrides this order.
                If order_by=priority, smart ordering is applied prioritizing rating and trade count. """
            if not owned:
                order_field = "price"
                if trade_type == models.TradeType.BUY:
                    order_field = "-price"
                if price_order is not None:
                    order_field = "price" if price_order == "ascending" else "-price"

                # Apply smart ordering if order_by=priority
                if order_by == "priority":
                    report_cutoff = timezone.now() - timedelta(hours=24)

                    # Annotate owner's average rating for sorting (NULL ratings treated as 0)
                    avg_rating_subq = (
                        models.OrderFeedback.objects.filter(to_peer=OuterRef("owner"))
                        .values("to_peer")
                        .annotate(avg=Avg("rating"))
                        .values("avg")[:1]
                    )
                    queryset = queryset.annotate(
                        owner_rating_raw=Subquery(avg_rating_subq),
                        owner_rating=Case(
                            When(
                                Q(owner__reported_at__gte=report_cutoff),
                                then=Value(0.0)
                            ),
                            default=Coalesce(Subquery(avg_rating_subq), 0.0),
                        ),
                    )

                    # Annotate owner's trade count for sorting (NULL counts treated as 0)
                    trade_count_subq = (
                        models.Order.objects.filter(
                            Q(ad_snapshot__ad__owner=OuterRef("owner"))
                            | Q(owner=OuterRef("owner"))
                        )
                        .annotate(cnt=Count("id"))
                        .values("cnt")[:1]
                    )
                    queryset = queryset.annotate(
                        owner_trade_count_raw=Subquery(trade_count_subq),
                        owner_trade_count=Case(
                            When(
                                Q(owner__reported_at__gte=report_cutoff),
                                then=Value(0)
                            ),
                            default=Coalesce(Subquery(trade_count_subq), 0),
                        ),
                    )

                    # Prioritize by rating and trade count first, then by price
                    queryset = queryset.order_by(
                        "-owner_rating", "-owner_trade_count", order_field, "created_at"
                    )
                else:
                    # Default ordering by price and creation date
                    queryset = queryset.order_by(order_field, "created_at")
            else:
                queryset = queryset.filter(Q(owner__wallet_hash=wallet_hash)).order_by(
                    "-created_at"
                )

            count = queryset.count()
            total_pages = page
            if limit > 0:
                total_pages = math.ceil(count / limit)

            offset = (page - 1) * limit
            paged_queryset = queryset[offset : offset + limit]

            context = {"wallet_hash": wallet_hash}
            AdSerializer = (
                serializers.ListAdSerializer if owned else serializers.StoreAdSerializer
            )
            serializer = AdSerializer(paged_queryset, many=True, context=context)
            data = {"ads": serializer.data, "count": count, "total_pages": total_pages}
            response_data = data
        return response_data

    def list(self, request):
        try:
            data = self.fetch_queryset(request=request)
            return Response(data, status=status.HTTP_200_OK)
        except ValidationError as err:
            return Response({"error": err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

    def retrieve(self, request, pk):
        try:
            data = self.fetch_queryset(request=request, pk=pk)
            return Response(data, status=status.HTTP_200_OK)
        except ValidationError as err:
            return Response({"error": err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

    @require_p2p_feature(models.FeatureControl.Type.AD_CREATE)
    def create(self, request):
        wallet_hash = request.headers.get("wallet_hash")
        payment_methods = request.data.get("payment_methods")

        if payment_methods and not self.has_payment_method_permissions(
            wallet_hash, payment_methods
        ):
            return Response(
                {"error": "No permission to use these payment methods"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            caller = models.Peer.objects.get(wallet_hash=wallet_hash)
        except models.Peer.DoesNotExist as err:
            return Response({"error": err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

        data = request.data.copy()
        data["owner"] = caller.id

        # make sure trade limits are correct
        trade_limits_in_fiat = data.get("trade_limits_in_fiat")
        if trade_limits_in_fiat == True:
            # fiat trade limits should not be empty
            if (
                data.get("trade_amount_fiat") == None
                or data.get("trade_floor_fiat") == None
                or data.get("trade_ceiling_fiat") == None
            ):
                return Response(
                    {
                        "error": "trade_amount_fiat, trade_floor_fiat, and trade_ceiling_fiat are required"
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if trade_limits_in_fiat == False:
            # sats trade limits should not be empty
            if (
                data.get("trade_amount_sats") == None
                or data.get("trade_floor_sats") == None
                or data.get("trade_ceiling_sats") == None
            ):
                return Response(
                    {
                        "error": "trade_amount_sats, trade_floor_sats, and trade_ceiling_sats are required"
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            crypto = data["crypto_currency"]
            data["crypto_currency"] = models.CryptoCurrency.objects.get(
                symbol=crypto
            ).id

            fiat = data["fiat_currency"]
            data["fiat_currency"] = models.FiatCurrency.objects.get(symbol=fiat).id
        except (
            models.CryptoCurrency.DoesNotExist,
            models.FiatCurrency.DoesNotExist,
        ) as err:
            return Response({"error": err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

        # limit to one ad per user per fiat currency
        if self.ad_count(wallet_hash, data["fiat_currency"], data["trade_type"]) >= 1:
            return Response(
                {"error": "Limited to 1 ad per fiat currency"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = serializers.WriteAdSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @require_p2p_feature(models.FeatureControl.Type.AD_UPDATE)
    def partial_update(self, request, pk):
        wallet_hash = request.user.wallet_hash
        payment_methods = request.data.get("payment_methods")

        has_write_permission = self.has_permissions(wallet_hash, pk)
        has_payment_permission = self.has_payment_method_permissions(
            wallet_hash, payment_methods
        )
        if not has_write_permission or (payment_methods and not has_payment_permission):
            return Response(
                {"error": "No permission to perform this action"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ad = self.get_object(pk)
        is_public = request.data.get("is_public")
        fiat_currency = request.data.get("fiat_currency")
        if fiat_currency and fiat_currency != ad.fiat_currency.id:
            return Response(
                {"error": "Not allowed to update ad fiat currency"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        exceeds_ad_limit = (
            self.ad_count(wallet_hash, ad.fiat_currency.id, ad.trade_type) > 1
        )
        currency_public_ad_count = self.public_ad_count(
            wallet_hash, ad.fiat_currency.id, ad.trade_type
        )
        private_to_public = not ad.is_public and is_public
        if private_to_public and exceeds_ad_limit and currency_public_ad_count >= 1:
            return Response(
                {"error": "Limited to 1 ad per fiat currency"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = request.data.copy()
        data.pop("crypto_currency", None)

        serializer = serializers.WriteAdSerializer(ad, data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        ad = serializer.save()

        # Renew expiry on any private-to-public transition
        if private_to_public:
            ad.expires_at = timezone.now() + timedelta(days=30)
            ad.save(update_fields=['expires_at', 'modified_at'])

        if (ad.unavailable_reminder_started_at is not None
                and (not ad.is_public or ad.get_unavailable_reason() is None)):
            clear_ad_unavailable_reminders(ad)

        context = {"wallet_hash": wallet_hash}
        serializer = serializers.AdSerializer(ad, context=context)

        # Notify ad subscribers
        websocket.send_ad_update("AD_UPDATED", pk)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def destroy(self, request, pk):
        wallet_hash = request.user.wallet_hash
        if not self.has_permissions(wallet_hash, pk):
            return Response(
                {"error": "No permission to perform this action"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ad = self.get_object(pk)
        ad.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(
        method="get",
        detail=False,
        operation_description="Checks if user has multiple ads that share the same currency",
    )
    def check_ad_limit(self, request):
        trade_type = request.query_params.get("trade_type")
        wallet_hash = request.user.wallet_hash

        currencies = models.FiatCurrency.objects.all()
        currency_ids = (
            currencies.annotate(paymenttype_count=Count("payment_types"))
            .values_list("id", flat=True)
            .filter(paymenttype_count__gt=0)
        )

        queryset = self.get_queryset().filter(owner__wallet_hash=wallet_hash)
        queryset = queryset.filter(fiat_currency__id__in=currency_ids)
        if trade_type:
            queryset = queryset.filter(trade_type=trade_type)
        queryset = (
            queryset.values("fiat_currency__name")
            .annotate(count=Count("id"))
            .filter(count__gt=1)
        )

        ads = []
        for entry in queryset:
            ads.append(
                {"currency": entry["fiat_currency__name"], "count": entry["count"]}
            )

        response = {"exceeds_limit": queryset.exists(), "ads": ads}
        return Response(response, status=status.HTTP_200_OK)

    @action(
        method="get",
        detail=False,
        operation_description="Retrieve fiat currencies not used in user's existing ads.",
    )
    def retrieve_currencies(self, request):
        wallet_hash = request.user.wallet_hash
        trade_type = request.query_params.get("trade_type")
        if not trade_type:
            return Response(
                {"error": "trade_type required"}, status=status.HTTP_400_BAD_REQUEST
            )

        used_currencies = (
            self.get_queryset()
            .filter(owner__wallet_hash=wallet_hash, trade_type=trade_type)
            .values_list("fiat_currency", flat=True)
            .distinct()
        )
        unused_currencies = models.FiatCurrency.objects.exclude(
            Q(id__in=used_currencies)
        )
        unused_currencies = unused_currencies.annotate(
            paymenttype_count=Count("payment_types")
        ).filter(paymenttype_count__gt=0)
        serializer = serializers.FiatCurrencySerializer(unused_currencies, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def has_permissions(self, wallet_hash, ad_id):
        """Returns true if user is ad owner, returns false otherwise."""
        return models.Ad.objects.filter(
            Q(pk=ad_id) & Q(owner__wallet_hash=wallet_hash)
        ).exists()

    def has_payment_method_permissions(self, wallet_hash, payment_method_ids):
        """Returns true if user owns the payment methods, returns false otherwise"""
        if payment_method_ids:
            return models.PaymentMethod.objects.filter(
                Q(owner__wallet_hash=wallet_hash) & Q(id__in=payment_method_ids)
            ).exists()
        return True

    def ad_count(self, user_wallet_hash, fiat_currency_id, trade_type):
        return models.Ad.objects.filter(
            owner__wallet_hash=user_wallet_hash,
            fiat_currency__id=fiat_currency_id,
            trade_type=trade_type,
            deleted_at__isnull=True,
        ).count()

    def public_ad_count(self, user_wallet_hash, fiat_currency_id, trade_type):
        now = timezone.now()
        return models.Ad.objects.filter(
            owner__wallet_hash=user_wallet_hash,
            fiat_currency__id=fiat_currency_id,
            trade_type=trade_type,
            is_public=True,
            deleted_at__isnull=True,
        ).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
        ).count()


class AdShareLinkView(View):
    @require_p2p_feature(models.FeatureControl.Type.AD_SHARE_LINKS)
    def get(self, request):
        ad_id = request.GET.get("id", "")
        ad = models.Ad.objects.filter(pk=ad_id)
        exists, trade_type, price, fiat_currency = False, "", None, None
        if ad.exists():
            exists = True
            ad = ad.first()
            trade_type = ad.trade_type.lower()
            price = f"{Decimal(ad.get_price()).quantize(Decimal('1.00')):,}"
            fiat_currency = ad.fiat_currency.symbol

        # Determine the appropriate action word based on trade type
        action_word = (
            "buy"
            if trade_type == "sell"
            else "sell"
            if trade_type == "buy"
            else "order"
        )

        context = {
            "ad_id": ad_id,
            "exists": exists,
            "trade_type": f"{trade_type}s",
            "price": price,
            "fiat_currency": fiat_currency,
            "title": f"This link opens a {trade_type} BCH ad!",
            "description": f"This link opens a {trade_type} Bitcoin Cash (BCH) ad for {price} {fiat_currency} per BCH. You can {action_word} using the Paytaca wallet app.",
        }
        return render(request, "ad.html", context=context)


class AdSnapshotViewSet(viewsets.GenericViewSet):
    authentication_classes = [TokenAuthentication]
    permission_classes = [RampP2PIsAuthenticated]

    def retrieve(self, request, pk):
        try:
            ad_snapshot = models.AdSnapshot.objects.get(pk=pk)
            if not models.Order.objects.filter(ad_snapshot_id=pk).filter(
                order_participant_filter(request.user)
            ).exists():
                raise PermissionDenied('Only order participants may access this snapshot.')
            serializer = serializers.AdSnapshotSerializer(ad_snapshot)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except models.AdSnapshot.DoesNotExist as err:
            return Response({"error": err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

    @action(method="get", detail=True)
    def retrieve_by_order(self, request, pk):
        try:
            order = models.Order.objects.get(pk=pk)
            require_order_participant(order, request.user)
            ad_snapshot = order.ad_snapshot
            serializer = serializers.AdSnapshotSerializer(ad_snapshot)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except models.Order.DoesNotExist as err:
            return Response({"error": err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
