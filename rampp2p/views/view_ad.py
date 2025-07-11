from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.decorators import action

from django.utils import timezone
from django.http import Http404
from django.core.exceptions import ValidationError
from django.db.models import (
    Q, Count, F, ExpressionWrapper, DecimalField, Case, Func, When, OuterRef, Subquery, IntegerField
)
from django.conf import settings
from django.views import View
from django.shortcuts import render

import math
from datetime import timedelta
from authentication.token import TokenAuthentication
from authentication.permissions import RampP2PIsAuthenticated
from decimal import Decimal

import rampp2p.serializers as serializers
import rampp2p.models as models
import rampp2p.utils.websocket as websocket
from rampp2p.utils import bch_to_satoshi, fiat_to_bch

import logging
logger = logging.getLogger(__name__)

class Round(Func):
    function = 'ROUND'
    template = '%(function)s(%(expressions)s, 8)'

class CashInAdViewSet(viewsets.GenericViewSet):

    def list(self, request):
        ''' [Deprecated] Retrieves a list of cash-in available ads, payment types, 
        and the ad count per given amounts '''
        wallet_hash = request.query_params.get('wallet_hash')
        currency = request.query_params.get('currency')
        payment_type = request.query_params.get('payment_type')
        amounts = request.query_params.getlist('amounts')
        trade_type = models.TradeType.SELL

        queryset = models.Ad.objects.filter(
            Q(deleted_at__isnull=True) & 
            Q(trade_type=trade_type) & 
            Q(is_public=True) & 
            Q(trade_amount__gt=0) &
            Q(trade_limits_in_fiat=False) &
            Q(fiat_currency__symbol=currency))
        
        queryset = queryset.exclude(owner__wallet_hash=wallet_hash)

        # Filter blacklisted/whitelisted
        currency_obj = models.FiatCurrency.objects.filter(symbol=currency)
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

        market_rate_subq = models.MarketPrice.objects.filter(currency=OuterRef('fiat_currency__symbol')).values('price')[:1]
        queryset = queryset.annotate(market_rate=Subquery(market_rate_subq))

        # Annotate ad price for sorting
        queryset = queryset.annotate(
            price=ExpressionWrapper(
                Case(
                    When(price_type=models.PriceType.FLOATING, then=(F('floating_price')/100 * F('market_rate'))),
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
        serialized_ads = serializers.CashinAdSerializer(cashin_ads, many=True, context = { 'wallet_hash': wallet_hash })

        responsedata = {
            'ads': serialized_ads.data,
            'payment_types': paymenttypes,
            'amount_ad_count': amount_ad_count
        }
        return Response(responsedata, status=status.HTTP_200_OK)

    @action(methods=['get'], detail=False)
    def list_presets(self, request):
        currency = request.query_params.get('currency')

        try: 
            currency = models.FiatCurrency.objects.get(symbol=currency)
            presets = currency.get_cashin_presets()
            return Response(presets, status=status.HTTP_200_OK)
        except models.FiatCurrency.DoesNotExist as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        
    @action(methods=['get'], detail=False)
    def retrieve_ad_count_by_payment_types(self, request):
        '''
        Retrieves a list by payment types where the number of recently online ads that are able to 
        accomodate at least 1 cash-in preset is greater than 0.
        '''
        wallet_hash = request.query_params.get('wallet_hash')
        currency = request.query_params.get('currency')

        try: 
            currency = models.FiatCurrency.objects.get(symbol=currency)
            queryset = self.get_queryset(currency, wallet_hash)
            queryset = self.filter_preset_available_ads(queryset, currency)

            # Count ads per payment_type
            payment_types = currency.payment_types.all()
            ad_count_by_payment = []
            for payment in payment_types:
                paymenttype_ads = queryset.filter(payment_methods__payment_type__id=payment.id)
                ad_count = paymenttype_ads.count()
                if ad_count > 0:
                    unique_sellers_count = paymenttype_ads.order_by('owner').distinct('owner').count()
                    ad_count_by_payment.append({
                        'payment_type': {
                            'id': payment.id,
                            'short_name': payment.short_name,
                            'full_name': payment.full_name
                        },
                        'ad_count': ad_count,
                        'online_sellers': unique_sellers_count
                    })
            return Response(ad_count_by_payment, status=status.HTTP_200_OK)
        except models.FiatCurrency.DoesNotExist as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(methods=['get'], detail=False)
    def retrieve_ads_by_presets(self, request):
        ''' Retrieves cash-in ads sorted by preset amounts of a given currency. '''

        wallet_hash = request.query_params.get('wallet_hash')
        payment_type_id = request.query_params.get('payment_type')
        currency = request.query_params.get('currency')
        by_fiat = request.query_params.get('by_fiat')
        by_fiat = by_fiat == 'true'

        try:
            fiat = models.FiatCurrency.objects.get(symbol=currency)
            bch = models.CryptoCurrency.objects.get(symbol="BCH")

            queryset = self.get_queryset(fiat, wallet_hash)
            queryset = queryset.filter(payment_methods__payment_type_id=payment_type_id)

            ads_by_amount = {}
            fiat_presets = fiat.get_cashin_presets()
            bch_presets = bch.get_cashin_presets()
            presets, amounts = fiat_presets, fiat_presets # use fiat presets by default

            if not by_fiat:
                # if filtering by bch, use bch presets but convert to satoshi
                satoshi_amounts = [bch_to_satoshi(preset) for preset in bch_presets]
                presets, amounts = bch_presets, satoshi_amounts

            # limit candidate ads to top 5
            queryset = queryset[0:5]
           
            for index, amount in enumerate(amounts):                
                amount_ads = []
                for ad in queryset:
                    trade_amount, trade_floor, trade_ceiling = 0, 0, 0

                    if by_fiat:
                        if ad.trade_limits_in_fiat:
                            trade_amount = ad.trade_amount_fiat
                            trade_floor = ad.trade_floor_fiat
                            trade_ceiling = ad.trade_ceiling_fiat
                        else:
                            # convert to fiat
                            trade_amount = Decimal(ad.trade_amount_sats / settings.SATOSHI_PER_BCH) * ad.price
                            trade_floor = Decimal(ad.trade_floor_sats / settings.SATOSHI_PER_BCH) * ad.price
                            trade_ceiling = Decimal(ad.trade_ceiling_sats / settings.SATOSHI_PER_BCH) * ad.price
                    else:
                        if not ad.trade_limits_in_fiat:
                            trade_amount = ad.trade_amount_sats
                            trade_floor = ad.trade_floor_sats
                            trade_ceiling = ad.trade_ceiling_sats
                        else:
                            # convert to sats
                            trade_amount = ad.trade_amount_fiat / ad.price * settings.SATOSHI_PER_BCH
                            trade_floor = ad.trade_floor_fiat / ad.price * settings.SATOSHI_PER_BCH
                            trade_ceiling = ad.trade_ceiling_fiat / ad.price * settings.SATOSHI_PER_BCH
                    
                    if trade_amount >= amount and trade_ceiling >= amount and trade_floor <= amount:
                        serialized_ad = serializers.CashinAdSerializer(ad)
                        amount_ads.append(serialized_ad.data)

                key = presets[index] or amounts[index]
                ads_by_amount[key] = amount_ads
            
            return Response(ads_by_amount, status=status.HTTP_200_OK)
        except (models.PaymentMethod.DoesNotExist, models.FiatCurrency.DoesNotExist) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)    

    def get_queryset(self, currency, wallet_hash):
        ''' Retrieves the viewset queryset. Filters public SELL ads of a given currency, excluding ads 
        created by caller (wallet_hash), and ads with owners offline for more than 24 hours. '''

        trade_type = models.TradeType.SELL
        queryset = models.Ad.objects.filter(
            Q(deleted_at__isnull=True) & 
            Q(trade_type=trade_type) & 
            Q(is_public=True) & 
            (Q(trade_amount_sats__gte=1000) |
            Q(trade_amount_fiat__gt=0)) &
            Q(fiat_currency__symbol=currency.symbol)) 
       
        # Exclude ads owned by caller
        queryset = queryset.exclude(owner__wallet_hash=wallet_hash)
        queryset = self.filter_by_access_control(currency, queryset)

        # Annotate price
        market_rate_subq = models.MarketPrice.objects.filter(currency=OuterRef('fiat_currency__symbol')).values('price')[:1]
        queryset = queryset.annotate(market_rate=Subquery(market_rate_subq)).annotate(
            price=ExpressionWrapper(
                Case(
                    When(price_type=models.PriceType.FLOATING, then=(F('floating_price')/100 * F('market_rate'))),
                    default=F('fixed_price'),
                    output_field=DecimalField()
                ),
                output_field=DecimalField()
            )
        )

        # Filter recently online ads
        queryset = queryset.annotate(last_online_at=F('owner__last_online_at'))
        queryset = queryset.filter(last_online_at__gte=timezone.now() - timedelta(days=1))
        queryset = queryset.order_by('price', '-last_online_at')

        return queryset
    
    def filter_by_access_control(self, currency, queryset):
        ''' Filters or excludes records by blacklisted or whitelisted list. '''
        whitelist = currency.cashin_whitelist.values_list('id', flat=True).all()
        
        if len(whitelist) > 0:
            queryset = queryset.filter(owner__id__in=whitelist)
        else:
            cashin_blacklisted_ids = currency.cashin_blacklist.values_list('id', flat=True).all()

            if len(cashin_blacklisted_ids) > 0:
                queryset = queryset.exclude(owner__id__in=cashin_blacklisted_ids)
        return queryset

    def filter_preset_available_ads(self, queryset, currency):
        ''' Filters only ads that can accomodate the currency's preset values. '''
        
        # annotate the trade limits
        annotated_limits_qs = queryset.annotate(
            ttrade_floor=Case(
                When(trade_limits_in_fiat=True, then=F('trade_floor_fiat')),
                When(trade_limits_in_fiat=False, then=F('trade_floor_sats')),
                output_field=DecimalField()
            ),
            ttrade_ceiling=Case(
                When(trade_limits_in_fiat=True, then=F('trade_ceiling_fiat')),
                When(trade_limits_in_fiat=False, then=F('trade_ceiling_sats')),
                output_field=DecimalField()
            ),
            ttrade_amount=Case(
                When(trade_limits_in_fiat=True, then=F('trade_amount_fiat')),
                When(trade_limits_in_fiat=False, then=F('trade_amount_sats')),
                output_field=DecimalField()
            )
        )

        bch_presets = self.get_bch_preset_amounts(currency)
        fiat_presets = currency.get_cashin_presets()

        q_objects = Q()
        for preset in fiat_presets:
            q_objects |= Q(
                trade_limits_in_fiat=True,
                ttrade_floor__lte=preset,
                ttrade_amount__gte=preset,
                ttrade_ceiling__gte=preset
            )

        for preset in bch_presets:
            q_objects |= Q(
                trade_limits_in_fiat=False,
                ttrade_floor__lte=preset,
                ttrade_amount__gte=preset,
                ttrade_ceiling__gte=preset
            )
        
        preset_filtered_qs = annotated_limits_qs.filter(q_objects)
        return preset_filtered_qs

    def get_bch_preset_amounts(self, currency):
        ''' Retrieves a currency's fiat preset amounts then converts it to BCH. 
        If preset is not set, returns the crypto currency's set preset amounts 
        or the hard coded preset amounts: ['0.02', '0.04', '0.1', '0.25', '0.5', '1'].'''

        # Use currency presets by default
        cashin_presets = currency.get_cashin_presets()

        # Use bch presets if currency's cash-in presets are not set
        if cashin_presets is None:
            bch_presets = models.CryptoCurrency.objects.get(symbol='BCH').get_cashin_presets()
            if bch_presets is None:
                # Use hard coded presets if cryptocurrency cash-in presets are not set
                bch_presets = ['0.02', '0.04', '0.1', '0.25', '0.5', '1']
            
            if bch_presets:
                # convert to satoshi
                satoshi_presets = []
                for preset in bch_presets:
                    satoshi_presets.append(bch_to_satoshi(preset))
                cashin_presets = satoshi_presets
        else:
            price_obj = models.MarketPrice.objects.filter(currency=currency.symbol)
            price = None
            if price_obj.exists():
                price = price_obj.first().price

            sat_amounts = []   
            for preset in cashin_presets:
                sat_amounts.append(bch_to_satoshi(fiat_to_bch(preset, price)))
            
            cashin_presets = sat_amounts
    
        return cashin_presets
    
    def get_paymenttypes(self, queryset, payment_types):
        ''' [Deprecated] Retrieves the list of unique payment types from cash-in available ads. '''
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

    def fetch_queryset (self, request=None, pk=None):
        if request is None:
            return []
        
        response_data = None
        if pk:
            ad = self.get_object(pk)
            wallet_hash = request.user.wallet_hash
            context = { 'wallet_hash': wallet_hash }
            serializer = serializers.AdSerializer(ad, context=context).data
            response_data = serializer
        else:
            queryset = models.Ad.objects.filter(Q(deleted_at__isnull=True))
            wallet_hash = request.headers.get('wallet_hash')
            owner_id = request.query_params.get('owner_id')
            currency = request.query_params.get('currency')
            trade_type = request.query_params.get('trade_type')
            price_types = request.query_params.getlist('price_types')
            payment_types = request.query_params.getlist('payment_types')
            time_limits = request.query_params.getlist('time_limits')
            price_order = request.query_params.get('price_order')
            query_name = request.query_params.get('query_name')
            order_amount = request.query_params.get('order_amount')
            order_amount_currency = request.query_params.get('order_amount_currency')
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
                queryset = queryset.filter(Q(is_public=True) & ((Q(trade_limits_in_fiat=False) & Q(trade_amount_sats__gte=1000)) | (Q(trade_limits_in_fiat=True) & Q(trade_amount_fiat__gt=0))))
            
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

            market_rate_subq = models.MarketPrice.objects.filter(currency=OuterRef('fiat_currency__symbol')).values('price')[:1]
            queryset = queryset.annotate(market_rate=Subquery(market_rate_subq))

            # Annotate to compute ad price based on price type (FIXED vs FLOATING)
            queryset = queryset.annotate(
                price=ExpressionWrapper(
                    Case(
                        When(price_type=models.PriceType.FLOATING, then=(F('floating_price')/100 * F('market_rate'))),
                        default=F('fixed_price'),
                        output_field=DecimalField()
                    ),
                    output_field=DecimalField()
                )
            )

            if order_amount and order_amount_currency:
                if order_amount_currency == 'BCH':
                    order_amount_sats = bch_to_satoshi(order_amount)
                    queryset = queryset.annotate(
                        order_amount_fiat=ExpressionWrapper(
                            order_amount * F('price'),
                            output_field=DecimalField()
                        )
                    ).filter(
                        (Q(trade_limits_in_fiat=False) & Q(trade_floor_sats__lte=order_amount_sats) & Q(trade_ceiling_sats__gte=order_amount_sats)) | 
                        (Q(trade_limits_in_fiat=True) & Q(trade_floor_fiat__lte=F('order_amount_fiat')) & Q(trade_ceiling_fiat__gte=F('order_amount_fiat')))
                    )
                else:
                    queryset = queryset.annotate(
                        order_amount_sats=ExpressionWrapper(
                            (order_amount / F('price')) *  settings.SATOSHI_PER_BCH,
                            output_field=IntegerField()
                        )
                    ).filter(
                        (Q(trade_limits_in_fiat=True) & Q(trade_floor_fiat__lte=order_amount) & Q(trade_ceiling_fiat__gte=order_amount)) | 
                        (Q(trade_limits_in_fiat=False) & Q(trade_floor_sats__lte=F('order_amount_sats')) & Q(trade_ceiling_sats__gte=F('order_amount_sats')))
                    )

            # search for ads with specific owner name
            if query_name:
                queryset = queryset.filter(owner__name__icontains=query_name)

            ''' Orders ads by price (if owned=True) or by created_at (if owned=False).
                Default order is ascending, descending if trade type is BUY. 
                price_order filter overrides this order '''
            if not owned:            
                order_field = 'price'
                if trade_type == models.TradeType.BUY: 
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
            AdSerializer = serializers.ListAdSerializer if owned else serializers.StoreAdSerializer
            serializer = AdSerializer(paged_queryset, many=True, context=context)
            data = {
                'ads': serializer.data,
                'count': count,
                'total_pages': total_pages
            }
            response_data = data
        return response_data

    def list(self, request):
        try:
            data = self.fetch_queryset(request=request)
            return Response(data, status=status.HTTP_200_OK)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

    def retrieve(self, request, pk):
        try:
            data = self.fetch_queryset(request=request, pk=pk)
            return Response(data, status=status.HTTP_200_OK)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

    def create(self, request):
        wallet_hash = request.headers.get('wallet_hash')
        payment_methods = request.data.get('payment_methods')

        if payment_methods and not self.has_payment_method_permissions(wallet_hash, payment_methods):
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
    
        try:
            caller = models.Peer.objects.get(wallet_hash=wallet_hash)
        except models.Peer.DoesNotExist as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        
        data = request.data.copy()
        data['owner'] = caller.id

        # make sure trade limits are correct
        trade_limits_in_fiat = data.get('trade_limits_in_fiat')
        if trade_limits_in_fiat == True:
            # fiat trade limits should not be empty
            if (data.get('trade_amount_fiat') == None or 
                data.get('trade_floor_fiat') == None or
                data.get('trade_ceiling_fiat') == None):
                return Response({'error': 'trade_amount_fiat, trade_floor_fiat, and trade_ceiling_fiat are required'}, status=status.HTTP_400_BAD_REQUEST)
        if trade_limits_in_fiat == False:
            # sats trade limits should not be empty
            if (data.get('trade_amount_sats') == None or
                data.get('trade_floor_sats') == None or
                data.get('trade_ceiling_sats') == None):
                return Response({'error': 'trade_amount_sats, trade_floor_sats, and trade_ceiling_sats are required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            crypto = data['crypto_currency']
            data['crypto_currency'] = models.CryptoCurrency.objects.get(symbol=crypto).id
            
            fiat = data['fiat_currency']
            data['fiat_currency'] = models.FiatCurrency.objects.get(symbol=fiat).id
        except (models.CryptoCurrency.DoesNotExist, models.FiatCurrency.DoesNotExist) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

        # limit to one ad per user per fiat currency
        if self.ad_count(wallet_hash, data['fiat_currency'], data['trade_type']) >= 1:
            return Response({ 'error': 'Limited to 1 ad per fiat currency' }, status=status.HTTP_400_BAD_REQUEST)

        serializer = serializers.WriteAdSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def partial_update(self, request, pk):
        wallet_hash = request.user.wallet_hash
        payment_methods = request.data.get('payment_methods')

        has_write_permission = self.has_permissions(wallet_hash, pk)
        has_payment_permission = self.has_payment_method_permissions(wallet_hash, payment_methods)
        if (not has_write_permission or (payment_methods and not has_payment_permission)):
            return Response({'error': 'No permission to perform this action'}, status=status.HTTP_400_BAD_REQUEST)
        
        ad = self.get_object(pk)
        is_public = request.data.get('is_public')
        fiat_currency = request.data.get('fiat_currency')
        if fiat_currency and fiat_currency != ad.fiat_currency.id:
            return Response({ 'error': 'Not allowed to update ad fiat currency' }, status=status.HTTP_400_BAD_REQUEST)

        exceeds_ad_limit = self.ad_count(wallet_hash, ad.fiat_currency.id, ad.trade_type) > 1
        currency_public_ad_count = self.public_ad_count(wallet_hash, ad.fiat_currency.id, ad.trade_type)
        private_to_public = not ad.is_public and is_public
        if private_to_public and exceeds_ad_limit and currency_public_ad_count >= 1:
            return Response({ 'error': 'Limited to 1 ad per fiat currency' }, status=status.HTTP_400_BAD_REQUEST)
        
        data = request.data.copy()
        data.pop('crypto_currency', None)

        serializer = serializers.WriteAdSerializer(ad, data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        ad = serializer.save()
        context = { 'wallet_hash': wallet_hash }
        serializer = serializers.AdSerializer(ad, context=context)

        # Notify ad subscribers
        websocket.send_ad_update('AD_UPDATED', pk)
        return Response(serializer.data, status=status.HTTP_200_OK)
        
    def destroy(self, request, pk):
        wallet_hash = request.user.wallet_hash
        if not self.has_permissions(wallet_hash, pk):
            return Response({'error': 'No permission to perform this action'}, status=status.HTTP_400_BAD_REQUEST)
        
        ad = self.get_object(pk)
        ad.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(method='get', detail=False, operation_description="Checks if user has multiple ads that share the same currency")
    def check_ad_limit(self, request):
        trade_type = request.query_params.get('trade_type')
        wallet_hash = request.user.wallet_hash

        currencies = models.FiatCurrency.objects.all()
        currency_ids = currencies.annotate(paymenttype_count=Count('payment_types')).values_list('id', flat=True).filter(paymenttype_count__gt=0)

        queryset = self.get_queryset().filter(owner__wallet_hash=wallet_hash)
        queryset = queryset.filter(fiat_currency__id__in=currency_ids)
        if trade_type:
            queryset = queryset.filter(trade_type=trade_type)
        queryset = queryset.values('fiat_currency__name').annotate(count=Count('id')).filter(count__gt=1)

        ads = []
        for entry in queryset:
            ads.append({'currency': entry['fiat_currency__name'], 'count': entry['count']})

        response = {
            'exceeds_limit': queryset.exists(),
            'ads': ads
        }
        return Response(response, status=status.HTTP_200_OK)

    @action(method='get', detail=False, operation_description="Retrieve fiat currencies not used in user's existing ads.")
    def retrieve_currencies(self, request):
        wallet_hash = request.user.wallet_hash
        trade_type = request.query_params.get('trade_type')
        if not trade_type:
            return Response({ 'error': 'trade_type required'}, status=status.HTTP_400_BAD_REQUEST)
        
        used_currencies = self.get_queryset().filter(owner__wallet_hash=wallet_hash, trade_type=trade_type).values_list('fiat_currency').distinct()
        unused_currencies = models.FiatCurrency.objects.exclude(Q(id__in=used_currencies))
        unused_currencies = unused_currencies.annotate(paymenttype_count=Count('payment_types')).filter(paymenttype_count__gt=0)
        serializer = serializers.FiatCurrencySerializer(unused_currencies, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def has_permissions(self, wallet_hash, ad_id):
        ''' Returns true if user is ad owner, returns false otherwise. '''
        return models.Ad.objects.filter(Q(pk=ad_id) & Q(owner__wallet_hash=wallet_hash)).exists()
    
    def has_payment_method_permissions(self, wallet_hash, payment_method_ids):
        ''' Returns true if user owns the payment methods, returns false otherwise'''
        if payment_method_ids:
            return models.PaymentMethod.objects.filter(Q(owner__wallet_hash=wallet_hash) & Q(id__in=payment_method_ids)).exists()
        return True
    
    def ad_count(self, user_wallet_hash, fiat_currency_id, trade_type):
        return models.Ad.objects.filter(owner__wallet_hash=user_wallet_hash, fiat_currency__id=fiat_currency_id, trade_type=trade_type, deleted_at__isnull=True).count()
    
    def public_ad_count(self, user_wallet_hash, fiat_currency_id, trade_type):
        return models.Ad.objects.filter(owner__wallet_hash=user_wallet_hash, fiat_currency__id=fiat_currency_id, trade_type=trade_type, is_public=True, deleted_at__isnull=True).count()

class AdShareLinkView(View):
    def get(self, request):
        ad_id = request.GET.get('id', '')
        ad = models.Ad.objects.filter(pk=ad_id)
        exists, trade_type, price, fiat_currency = False, '', None, None
        if ad.exists():
            exists = True
            ad = ad.first()
            trade_type = ad.trade_type.lower()
            price = f"{Decimal(ad.get_price()).quantize(Decimal('1.00')):,}"
            fiat_currency = ad.fiat_currency.symbol

        # Determine the appropriate action word based on trade type
        action_word = "buy" if trade_type == "sell" else "sell" if trade_type == "buy" else "order"
        
        context = {
            "ad_id": ad_id,
            "exists": exists,
            "trade_type": f"{trade_type}s",
            "price": price,
            "fiat_currency": fiat_currency,
            "title": f"This link opens a {trade_type} BCH ad!",
            "description": f"This link opens a {trade_type} Bitcoin Cash (BCH) ad for {price} {fiat_currency} per BCH. You can {action_word} using the Paytaca wallet app."
        }
        return render(request, "ad.html", context=context)

class AdSnapshotViewSet(viewsets.GenericViewSet):
    authentication_classes = [TokenAuthentication]

    def retrieve(self, _, pk):
        try:
            ad_snapshot = models.AdSnapshot.objects.get(pk=pk)
            serializer = serializers.AdSnapshotSerializer(ad_snapshot)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except models.AdSnapshot.DoesNotExist as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

    @action(method='get', detail=True)
    def retrieve_by_order(self, _, pk):
        try:
            ad_snapshot = models.Order.objects.get(pk=pk).ad_snapshot
            serializer = serializers.AdSnapshotSerializer(ad_snapshot)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except models.Order.DoesNotExist as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)