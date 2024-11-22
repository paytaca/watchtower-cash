from rest_framework import status, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action

from django.utils import timezone
from django.db.models import Q
from django.http import Http404
from django.core.exceptions import ValidationError
from django.db.models import (Count, F, ExpressionWrapper, DecimalField, Case, Func, When, OuterRef, Subquery)

import math
from datetime import timedelta
from decimal import Decimal, ROUND_DOWN
from authentication.token import TokenAuthentication
from authentication.permissions import RampP2PIsAuthenticated

import rampp2p.serializers as rampp2p_serializers
import rampp2p.models as rampp2p_models

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

    @action(methods=['get'], detail=False)
    def list_presets(self, request):
        currency = request.query_params.get('currency')

        try: 
            currency = rampp2p_models.FiatCurrency.objects.get(symbol=currency)
            presets = currency.get_cashin_presets()
            return Response(presets, status=status.HTTP_200_OK)
        except rampp2p_models.FiatCurrency.DoesNotExist as err:
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
            currency = rampp2p_models.FiatCurrency.objects.get(symbol=currency)
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
        except rampp2p_models.FiatCurrency.DoesNotExist as err:
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
            currency = rampp2p_models.FiatCurrency.objects.get(symbol=currency)
            queryset = self.get_queryset(currency, wallet_hash)
            queryset = queryset.filter(payment_methods__payment_type_id=payment_type_id)

            ads_by_amount = {}
            presets = currency.get_cashin_presets()
            amounts = self.get_bch_preset_amounts(currency)
            
            if not by_fiat:
                bch = rampp2p_models.CryptoCurrency.objects.get(symbol="BCH")
                presets = bch.get_cashin_presets() or ['0.02', '0.04', '0.1', '0.25', '0.5', '1']
                amounts = presets 

            if presets:
                for index, amount in enumerate(amounts):
                    ads = queryset.filter(Q(rounded_bch_trade_floor__lte=amount) & Q(rounded_bch_trade_amount__gte=amount) & Q(rounded_bch_trade_ceiling__gte=amount))
                    serialized_ads = rampp2p_serializers.CashinAdSerializer(ads, many=True)
                    key = presets[index]
                    if key is None:
                        key = amounts[index]
                    ads_by_amount[key] = serialized_ads.data
            
            return Response(ads_by_amount, status=status.HTTP_200_OK)
        except (rampp2p_models.PaymentMethod.DoesNotExist, 
                rampp2p_models.FiatCurrency.DoesNotExist) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)    

    def get_queryset(self, currency, wallet_hash):
        ''' Retrieves the viewset queryset. Filters public SELL ads of a given currency, excluding ads 
        created by caller (wallet_hash), and ads with owners offline for more than 24 hours. '''

        trade_type = rampp2p_models.TradeType.SELL
        queryset = rampp2p_models.Ad.objects.filter(
            Q(deleted_at__isnull=True) & 
            Q(trade_type=trade_type) & 
            Q(is_public=True) & 
            Q(trade_amount__gt=0) &
            Q(fiat_currency__symbol=currency.symbol)) 
       
        # Exclude ads owned by caller
        queryset = queryset.exclude(owner__wallet_hash=wallet_hash)
        queryset = self.filter_by_access_control(currency, queryset)

        # Annotate price
        market_rate_subq = rampp2p_models.MarketRate.objects.filter(currency=OuterRef('fiat_currency__symbol')).values('price')[:1]
        queryset = queryset.annotate(market_rate=Subquery(market_rate_subq)).annotate(
            price=ExpressionWrapper(
                Case(
                    When(price_type=rampp2p_models.PriceType.FLOATING, then=(F('floating_price')/100 * F('market_rate'))),
                    default=F('fixed_price'),
                    output_field=DecimalField()
                ),
                output_field=DecimalField()
            )
        )

        queryset = queryset.annotate(
            bch_trade_amount=ExpressionWrapper(
                Case(When(
                    trade_amount_in_fiat=True,
                    then=(F('trade_amount') / F('price'))),
                    default=F('trade_amount'),
                    output_field=DecimalField()),
                output_field=DecimalField()
            )
        ).annotate(rounded_bch_trade_amount=Round('bch_trade_amount', output_field=DecimalField(max_digits=18, decimal_places=8)))
        
        queryset = queryset.annotate(
            bch_trade_floor=ExpressionWrapper(
                Case(When(
                    trade_limits_in_fiat=True,
                    then=(F('trade_floor') / F('price'))),
                    default=F('trade_floor'),
                    output_field=DecimalField()),
                output_field=DecimalField()
            )
        ).annotate(rounded_bch_trade_floor=Round('bch_trade_floor', output_field=DecimalField(max_digits=18, decimal_places=8)))
        
        queryset = queryset.annotate(
            bch_trade_ceiling=ExpressionWrapper(
                Case(When(
                    trade_limits_in_fiat=True,
                    then=(F('trade_ceiling') / F('price'))),
                    default=F('trade_ceiling'),
                    output_field=DecimalField()),
                output_field=DecimalField()
            )
        ).annotate(rounded_bch_trade_ceiling=Round('bch_trade_ceiling', output_field=DecimalField(max_digits=18, decimal_places=8)))

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
    
    def get_bch_preset_amounts(self, currency):
        ''' Retrives a currency's fiat preset amounts then converts it to BCH. If preset is not set,
         returns the crypto currency's set preset amounts or the hard coded preset amounts: ['0.02', '0.04', '0.1', '0.25', '0.5', '1'].'''

        # Use currency presets by default
        cashin_presets = currency.get_cashin_presets()
        convert_to_bch = True

        # Use bch presets if currency's cash-in presets are not set
        if cashin_presets is None:
            convert_to_bch = False
            bch_presets = rampp2p_models.CryptoCurrency.objects.get(symbol='BCH').get_cashin_presets()
            if bch_presets:
                cashin_presets = bch_presets
            else:
                # Use hard coded presets if cryptocurrency cash-in presets are not set
                cashin_presets = ['0.02', '0.04', '0.1', '0.25', '0.5', '1']
        
        # Convert to BCH using market price
        if convert_to_bch:
            bch_amounts = []
            market_rate_obj = rampp2p_models.MarketRate.objects.filter(currency=currency.symbol)
            market_price = None
            if market_rate_obj.exists:
                market_price = market_rate_obj.first().price
                
            for preset in cashin_presets:
                amount = (preset/market_price).quantize(Decimal('0.00000001'), rounding=ROUND_DOWN) # truncate to 8 decimals
                bch_amounts.append(str(amount))
            cashin_presets = bch_amounts
        
        return cashin_presets

    def filter_preset_available_ads(self, queryset, currency):
        ''' Filters only ads that can accomodate the currency's preset values. '''
        amounts = self.get_bch_preset_amounts(currency)
        combined_query = Q()
        for amount in amounts:
            combined_query |= Q(rounded_bch_trade_floor__lte=amount) & Q(rounded_bch_trade_amount__gte=amount) & Q(rounded_bch_trade_ceiling__gte=amount)
        return queryset.filter(combined_query)
    
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
    queryset = rampp2p_models.Ad.objects.filter(deleted_at__isnull=True)

    def get_object(self, pk):
        Ad = rampp2p_models.Ad
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
            owned = request.query_params.get('owned') == 'true'

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

            ''' Orders ads by price (if owned=True) or by created_at (if owned=False).
                Default order is ascending, descending if trade type is BUY. 
                price_order filter overrides this order '''
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

        # limit to one ad per user per fiat currency
        if self.ad_count(wallet_hash, data['fiat_currency'], data['trade_type']) >= 1:
            return Response({ 'error': 'Limited to 1 ad per fiat currency' }, status=status.HTTP_400_BAD_REQUEST)

        serializer = rampp2p_serializers.AdSerializer(data=data)
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
        if is_public == True and exceeds_ad_limit and currency_public_ad_count >= 1:
            return Response({ 'error': 'Limited to 1 ad per fiat currency' }, status=status.HTTP_400_BAD_REQUEST)
        
        data = request.data.copy()
        data.pop('crypto_currency', None)

        serializer = rampp2p_serializers.AdSerializer(ad, data=data)
        if serializer.is_valid():
            ad = serializer.save()
            context = { 'wallet_hash': wallet_hash }
            serializer = rampp2p_serializers.AdListSerializer(ad, context=context)
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
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

        currencies = rampp2p_models.FiatCurrency.objects.all()
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
        unused_currencies = rampp2p_models.FiatCurrency.objects.exclude(Q(id__in=used_currencies))
        unused_currencies = unused_currencies.annotate(paymenttype_count=Count('payment_types')).filter(paymenttype_count__gt=0)
        serializer = rampp2p_serializers.FiatCurrencySerializer(unused_currencies, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def has_permissions(self, wallet_hash, ad_id):
        ''' Returns true if user is ad owner, returns false otherwise. '''
        return rampp2p_models.Ad.objects.filter(Q(pk=ad_id) & Q(owner__wallet_hash=wallet_hash)).exists()
    
    def has_payment_method_permissions(self, wallet_hash, payment_method_ids):
        ''' Returns true if user owns the payment methods, returns false otherwise'''
        if payment_method_ids:
            return rampp2p_models.PaymentMethod.objects.filter(Q(owner__wallet_hash=wallet_hash) & Q(id__in=payment_method_ids)).exists()
        return True
    
    def ad_count(self, user_wallet_hash, fiat_currency_id, trade_type):
        return rampp2p_models.Ad.objects.filter(owner__wallet_hash=user_wallet_hash, fiat_currency__id=fiat_currency_id, trade_type=trade_type, deleted_at__isnull=True).count()
    
    def public_ad_count(self, user_wallet_hash, fiat_currency_id, trade_type):
        return rampp2p_models.Ad.objects.filter(owner__wallet_hash=user_wallet_hash, fiat_currency__id=fiat_currency_id, trade_type=trade_type, is_public=True, deleted_at__isnull=True).count()
        
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