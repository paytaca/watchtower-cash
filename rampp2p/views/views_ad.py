from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response

from django.utils import timezone
from django.db.models import Q
from django.http import Http404
from django.core.exceptions import ValidationError
from django.db.models import (F, ExpressionWrapper, DecimalField, Case, When, OuterRef, Subquery)

import math
from datetime import timedelta
from authentication.token import TokenAuthentication

import rampp2p.serializers as rampp2p_serializers
import rampp2p.models as rampp2p_models

import logging
logger = logging.getLogger(__name__)

class ListCashInAdView(APIView):
    '''
        Filters the best Sell Ad for given payment type and amount.
        The best SELL ad is determined by:
            - Ad fiat currency
            - If SELL ad accepts the payment type selected by buyer
            - If buy amount is within range of the SELL ad
            - Sorted by last online
            - Sorted by price lowest first
        NB
            - Excludes ads where trade_limits_in_fiat=True
            - Excludes cash-in blacklisted peer ads if cash-in whitelist is empty
            - Only includes cash-in whitelisted peer ads if cash-in whitelist is not empty
    '''
    def get(self, request):
        wallet_hash = request.query_params.get('wallet_hash')
        currency = request.query_params.get('currency')
        payment_type = request.query_params.get('payment_type')
        amounts = request.query_params.getlist('amounts')
        trade_type = rampp2p_models.TradeType.SELL

        queryset = rampp2p_models.Ad.objects.filter(
            Q(deleted_at__isnull=True) & 
            Q(trade_type=trade_type) & 
            Q(is_public=True) & 
            Q(trade_amount__gt=0) &
            Q(trade_limits_in_fiat=False) &
            Q(fiat_currency__symbol=currency))
        
        queryset = queryset.exclude(owner__wallet_hash=wallet_hash)

        # Filter blacklisted/whitelisted
        currency_obj = rampp2p_models.FiatCurrency.objects.filter(symbol=currency)
        if currency_obj.exists():
            currency_obj = currency_obj.first()
            cashin_whitelisted_ids = currency_obj.cashin_whitelist.values_list('id', flat=True).all()
            
            # If whitelist is NOT empty, only whitelisted peer ads are allowed
            if len(cashin_whitelisted_ids) > 0:
                queryset = queryset.filter(owner__id__in=cashin_whitelisted_ids)
            else:
                # If whitelist is empty, blacklisted peer ads are not allowed
                cashin_blacklisted_ids = currency_obj.cashin_blacklist.values_list('id', flat=True).all()

                if len(cashin_blacklisted_ids) > 0:
                    queryset = queryset.exclude(owner__id__in=cashin_blacklisted_ids)

        queryset = queryset.annotate(last_online_at=F('owner__last_online_at'))
        count_online_queryset = queryset

        # Filters which ads accept the selected payment method
        if payment_type:
            queryset = queryset.filter(payment_methods__payment_type__id=payment_type).distinct()

        market_rate_subq = rampp2p_models.MarketRate.objects.filter(currency=OuterRef('fiat_currency__symbol')).values('price')[:1]
        queryset = queryset.annotate(market_rate=Subquery(market_rate_subq))

        # Annotate ad price for sorting
        queryset = queryset.annotate(
            price=ExpressionWrapper(
                Case(
                    When(price_type=rampp2p_models.PriceType.FLOATING, then=(F('floating_price')/100 * F('market_rate'))),
                    default=F('fixed_price'),
                    output_field=DecimalField()
                ),
                output_field=DecimalField()
            )
        )

        # prioritize online ads
        queryset = queryset.order_by('-last_online_at', 'price')
        
        # fetch related payment methods
        ads_with_payment_methods = queryset.prefetch_related('payment_methods')
        payment_types_set = set()
        for ad in ads_with_payment_methods:
            for payment_method in ad.payment_methods.all():
                payment_types_set.add(payment_method.payment_type)
        distinct_payment_types = list(payment_types_set)

        # count the number of available ads for given preset order amounts
        amount_ad_count = {}
        for amount in amounts:
            queryset_count = queryset.filter((Q(trade_floor__lte=amount) & Q(trade_ceiling__gte=amount))).count()
            amount_ad_count[amount] = queryset_count

        # fetch only ads with paymenttypes that have recently online owners
        paymenttypes, paymenttypes_ids = self.get_paymenttypes(count_online_queryset, distinct_payment_types)
        if payment_type is None:
            queryset = queryset.filter(payment_methods__payment_type__id__in=paymenttypes_ids)

        cashin_ads = queryset[:10]
        serialized_ads = rampp2p_serializers.CashinAdSerializer(cashin_ads, many=True, context = { 'wallet_hash': wallet_hash })

        responsedata = {
            'ads': serialized_ads.data,
            'payment_types': paymenttypes,
            'amount_ad_count': amount_ad_count
        }
        return Response(responsedata, status=status.HTTP_200_OK)
    
    def get_paymenttypes(self, queryset, payment_types):
        queryset = queryset.filter(last_online_at__gte=timezone.now() - timedelta(days=1))        

        paymenttypes = []
        ids = []
        for payment_type in payment_types:
            # Filters which ads accept the selected payment method
            pt_queryset = queryset.filter(payment_methods__payment_type__id=payment_type.id).values('owner').distinct()
            if pt_queryset.count() > 0:
                paymenttypes.append({
                    'id': payment_type.id,
                    'full_name': payment_type.full_name,
                    'short_name': payment_type.short_name,
                    'online_ads_count': pt_queryset.count()
                })
                ids.append(payment_type.id)

        return paymenttypes, ids

class AdView(APIView):
    authentication_classes = [TokenAuthentication]

    def get_object(self, pk):
        Ad = rampp2p_models.Ad
        try:
            ad = Ad.objects.get(pk=pk)
            if ad.deleted_at is not None:
                raise Ad.DoesNotExist
            return ad
        except Ad.DoesNotExist:
            raise Http404

    def get_queryset (self, request, pk=None):
        response_data = None
        if pk:
            ad = self.get_object(pk)
            wallet_hash = request.user.wallet_hash
            context = { 'wallet_hash': wallet_hash }
            serializer = None
            if ad.owner.wallet_hash == wallet_hash:
                serializer = rampp2p_serializers.AdOwnerSerializer(ad, context=context).data
            else:
                serializer = rampp2p_serializers.AdDetailSerializer(ad, context=context).data
            response_data = serializer
        else:
            queryset = rampp2p_models.Ad.objects.filter(Q(deleted_at__isnull=True))
            wallet_hash = request.headers.get('wallet_hash')
            owner_id = request.query_params.get('owner_id')
            currency = request.query_params.get('currency')
            trade_type = request.query_params.get('trade_type')
            price_types = request.query_params.getlist('price_types')
            payment_types = request.query_params.getlist('payment_types')
            time_limits = request.query_params.getlist('time_limits')
            price_order = request.query_params.get('price_order')
            query_name = request.query_params.get('query_name')
            owned = request.query_params.get('owned', False)
            owned = owned == 'true'

            try:
                limit = int(request.query_params.get('limit', 0))
                page = int(request.query_params.get('page', 1))
            except ValueError as err:
                raise ValidationError(err.args[0])

            if limit < 0:
                raise ValidationError('limit must be a non-negative number')
            
            if page < 1:
                raise ValidationError('invalid page number')
            
            if not owned:
                # If not fetching owned ads: fetch only public ads and those with trade amount > 0
                queryset = queryset.filter(Q(is_public=True) & Q(trade_amount__gt=0))
            
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
                queryset = queryset.filter(payment_methods__payment_type__id__in=payment_types).distinct()

            if len(time_limits) > 0:
                time_limits = list(map(int, time_limits))
                queryset = queryset.filter(appeal_cooldown_choice__in=time_limits).distinct()

            market_rate_subq = rampp2p_models.MarketRate.objects.filter(currency=OuterRef('fiat_currency__symbol')).values('price')[:1]
            queryset = queryset.annotate(market_rate=Subquery(market_rate_subq))

            # Annotate to compute ad price based on price type (FIXED vs FLOATING)
            queryset = queryset.annotate(
                price=ExpressionWrapper(
                    Case(
                        When(price_type=rampp2p_models.PriceType.FLOATING, then=(F('floating_price')/100 * F('market_rate'))),
                        default=F('fixed_price'),
                        output_field=DecimalField()
                    ),
                    output_field=DecimalField()
                )
            )

            # search for ads with specific owner name
            if query_name:
                queryset = queryset.filter(owner__name__icontains=query_name)

            # Order ads by price (if store listings) or created_at (if owned ads)
            # Default order: ascending, descending if trade type is BUY, 
            # `price_order` filter overrides this order
            if not owned:            
                order_field = 'price'
                if trade_type == rampp2p_models.TradeType.BUY: 
                    order_field = '-price'
                if price_order is not None:
                    order_field = 'price' if price_order == 'ascending' else '-price'
                queryset = queryset.order_by(order_field, 'created_at')
            else:
                queryset = queryset.filter(Q(owner__wallet_hash=wallet_hash)).order_by('-created_at')

            count = queryset.count()
            total_pages = page
            if limit > 0:
                total_pages = math.ceil(count / limit)

            offset = (page - 1) * limit
            paged_queryset = queryset[offset:offset + limit]

            context = { 'wallet_hash': wallet_hash }
            serializer = rampp2p_serializers.AdListSerializer(paged_queryset, many=True, context=context)
            data = {
                'ads': serializer.data,
                'count': count,
                'total_pages': total_pages
            }
            response_data = data
        return response_data

    def get(self, request, pk=None):
        try:
            response_data = self.get_queryset(request, pk=pk)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        return Response(response_data, status=status.HTTP_200_OK)

    def post(self, request):
        wallet_hash = request.headers.get('wallet_hash')
        payment_methods = request.data.get('payment_methods')

        if payment_methods and not self.has_payment_method_permissions(wallet_hash, payment_methods):
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
    
        try:
            caller = rampp2p_models.Peer.objects.get(wallet_hash=wallet_hash)
        except rampp2p_models.Peer.DoesNotExist as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        
        data = request.data.copy()
        data['owner'] = caller.id

        try:
            crypto = data['crypto_currency']
            data['crypto_currency'] = rampp2p_models.CryptoCurrency.objects.get(symbol=crypto).id
            
            fiat = data['fiat_currency']
            data['fiat_currency'] = rampp2p_models.FiatCurrency.objects.get(symbol=fiat).id
        except (rampp2p_models.CryptoCurrency.DoesNotExist, rampp2p_models.FiatCurrency.DoesNotExist) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

        serializer = rampp2p_serializers.AdCreateSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def put(self, request, pk):
        wallet_hash = request.user.wallet_hash
        payment_methods = request.data.get('payment_methods')

        has_write_permission = self.has_permissions(wallet_hash, pk)
        has_payment_permission = self.has_payment_method_permissions(wallet_hash, payment_methods)
        if (not has_write_permission or (payment_methods and not has_payment_permission)):
            return Response({'error': 'No permission to perform this action'}, status=status.HTTP_400_BAD_REQUEST)
        
        ad = self.get_object(pk)
        serializer = rampp2p_serializers.AdSerializer(ad, data=request.data)
        if serializer.is_valid():
            ad = serializer.save()
            context = { 'wallet_hash': wallet_hash }
            serializer = rampp2p_serializers.AdListSerializer(ad, context=context)
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, pk):
        wallet_hash = request.user.wallet_hash
        if not self.has_permissions(wallet_hash, pk):
            return Response({'error': 'No permission to perform this action'}, status=status.HTTP_400_BAD_REQUEST)
        
        ad = self.get_object(pk)
        ad.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    def has_permissions(self, wallet_hash, ad_id):
        ''' Returns true if user is ad owner, returns false otherwise. '''
        return rampp2p_models.Ad.objects.filter(Q(pk=ad_id) & Q(owner__wallet_hash=wallet_hash)).exists()
    
    def has_payment_method_permissions(self, wallet_hash, payment_method_ids):
        ''' Returns true if user owns the payment methods, returns false otherwise'''
        if payment_method_ids:
            return rampp2p_models.PaymentMethod.objects.filter(Q(owner__wallet_hash=wallet_hash) & Q(id__in=payment_method_ids)).exists()
        return True
        
class AdSnapshotView(APIView):
    authentication_classes = [TokenAuthentication]
    def get(self, request):
        ad_snapshot_id = request.query_params.get('ad_snapshot_id')
        order_id = request.query_params.get('order_id')
        
        ad = None
        try:
            if ad_snapshot_id is not None:
                ad = rampp2p_models.AdSnapshot.objects.get(pk=ad_snapshot_id)
            elif order_id is not None:
                ad = rampp2p_models.Order.objects.get(pk=order_id).ad_snapshot
        except (rampp2p_models.AdSnapshot.DoesNotExist, rampp2p_models.Order.DoesNotExist):
            raise Http404

        serializer = rampp2p_serializers.AdSnapshotSerializer(ad)
        return Response(serializer.data, status=status.HTTP_200_OK)