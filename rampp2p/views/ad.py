from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Q
from django.utils import timezone
from django.http import Http404
from django.core.exceptions import ValidationError
import math

from rampp2p.viewcodes import ViewCode
from rampp2p.utils.signature import verify_signature, get_verification_headers
from rampp2p.serializers import (
    AdListSerializer, 
    AdDetailSerializer,
    AdCreateSerializer, 
    AdUpdateSerializer,
    AdOwnerSerializer
)
from rampp2p.models import (
    Ad, 
    Peer, 
    PaymentMethod,
    FiatCurrency,
    CryptoCurrency,
    TradeType,
    PriceType,
    MarketRate
)
from django.db.models import (
    F, 
    ExpressionWrapper, 
    DecimalField, 
    Case, 
    When
)

import logging
logger = logging.getLogger(__name__)

class AdListCreate(APIView):
    def get(self, request):
        queryset = Ad.objects.filter(is_deleted=False)

        wallet_hash = request.headers.get('wallet_hash')
        owner_id = request.query_params.get('owner_id')
        currency = request.query_params.get('currency')
        trade_type = request.query_params.get('trade_type')
        owned = request.query_params.get('owned', False)

        try:
            limit = int(request.query_params.get('limit', 0))
            page = int(request.query_params.get('page', 1))
        except ValueError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

        if limit < 0:
            return Response({'error': 'limit must be a non-negative number'}, status=status.HTTP_400_BAD_REQUEST)
        
        if page < 1:
            return Response({'error': 'invalid page number'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Verify owner signature
            signature, timestamp, _ = get_verification_headers(request)
            message = ViewCode.AD_LIST.value + '::' + timestamp
            verify_signature(wallet_hash, signature, message)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
        
        if not owned and currency is None:
            # Require currency param if fetching data for store page
            return Response({'error': 'currency is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        if owner_id is not None:
            queryset = queryset.filter(owner_id=owner_id)

        if currency is not None:
            queryset = queryset.filter(Q(fiat_currency__symbol=currency))
        
        if trade_type is not None:
            queryset = queryset.filter(Q(trade_type=trade_type))

        market_rate = MarketRate.objects.filter(currency=currency)

        # annotate to compute ad price based on price type (FIXED vs FLOATING)
        queryset = queryset.annotate(
            price=ExpressionWrapper(
                Case(
                    When(price_type=PriceType.FLOATING, then=(F('floating_price')/100 * market_rate.values('price'))),
                    default=F('fixed_price'),
                    output_field=DecimalField()
                ),
                output_field=DecimalField()
            )
        )

        if not owned:
            # Order ads by price (default: ascending order) if fetching ads for store page
            order = 'price'

            # switch to descending order if trade type is BUY
            if trade_type == TradeType.BUY:
                order = '-price'

            queryset = queryset.order_by(order, 'created_at')
        else:
            # Order by created_at if fetching ads for owner
            queryset = queryset.filter(Q(owner__wallet_hash=wallet_hash)).order_by('-created_at')

        count = queryset.count()
        total_pages = page
        if limit > 0:
            total_pages = math.ceil(count / limit)

        offset = (page - 1) * limit
        page_results = queryset[offset:offset + limit]

        context = { 'wallet_hash': wallet_hash }
        serializer = AdListSerializer(page_results, many=True, context=context)
        data = {
            'ads': serializer.data,
            'count': count,
            'total_pages': total_pages
        }
        return Response(data, status.HTTP_200_OK)

    def post(self, request):
        try:
            # validate signature
            signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.AD_CREATE.value + '::' + timestamp
            verify_signature(wallet_hash, signature, message)

            # Validate that user owns the payment methods
            payment_methods = request.data.get('payment_methods')
            validate_payment_methods_ownership(wallet_hash, payment_methods)

        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
    
        try:
            caller = Peer.objects.get(wallet_hash=wallet_hash)
        except Peer.DoesNotExist as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        
        data = request.data.copy()
        data['owner'] = caller.id

        try:
            crypto = data['crypto_currency']
            data['crypto_currency'] = CryptoCurrency.objects.get(symbol=crypto).id
            
            fiat = data['fiat_currency']
            data['fiat_currency'] = FiatCurrency.objects.get(symbol=fiat).id
        except (CryptoCurrency.DoesNotExist, FiatCurrency.DoesNotExist) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

        serializer = AdCreateSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class AdDetail(APIView):
    def get_object(self, pk):
        try:
            return Ad.objects.get(pk=pk)
        except Ad.DoesNotExist:
            raise Http404

    def get(self, request, pk):
        ad = self.get_object(pk)
        if ad.is_deleted:
            return Response(status=status.HTTP_204_NO_CONTENT)
        
        wallet_hash = request.headers.get('wallet_hash')

        try:
            # validate signature
            signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.AD_GET.value + '::' + timestamp
            verify_signature(wallet_hash, signature, message)

        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
        
        serializer = None
        context = { 'wallet_hash': wallet_hash }
        if ad.owner.wallet_hash == wallet_hash:
            serializer = AdOwnerSerializer(ad, context=context)
        else:
            serializer = AdDetailSerializer(ad, context=context)
        logger.warn(f'ad: {ad}')
        # return Response(serializer, status=status.HTTP_200_OK)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk):

        try:
            # validate signature
            signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.AD_UPDATE.value + '::' + timestamp
            verify_signature(wallet_hash, signature, message)

            # validate permissions
            self.validate_permissions(wallet_hash, pk)
            
            # Validate that user owns the payment methods
            payment_methods = request.data.get('payment_methods')
            validate_payment_methods_ownership(wallet_hash, payment_methods)

        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
        
        ad = self.get_object(pk)
        serializer = AdUpdateSerializer(ad, data=request.data)
        if serializer.is_valid():
            ad = serializer.save()
            context = { 'wallet_hash': wallet_hash }
            serializer = AdListSerializer(ad, context=context)
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, pk):
        try:
            # validate signature
            signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.AD_DELETE.value + '::' + timestamp
            verify_signature(wallet_hash, signature, message)

            # validate permissions
            self.validate_permissions(wallet_hash, pk)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
        
        # TODO: block deletion when ad has active orders
        
        ad = self.get_object(pk)
        if not ad.is_deleted:
            ad.is_deleted = True
            ad.deleted_at = timezone.now()
            ad.save()
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    def validate_permissions(self, wallet_hash, ad_id):
        '''
        Validates if caller is ad owner
        '''
        try:
            ad = Ad.objects.get(pk=ad_id)
            caller = Peer.objects.get(wallet_hash=wallet_hash)
        except (Ad.DoesNotExist, Peer.DoesNotExist) as err:
            raise ValidationError(err.args[0])
        
        if caller.wallet_hash != ad.owner.wallet_hash:
            raise ValidationError('caller must be ad owner')

def validate_payment_methods_ownership(wallet_hash, payment_method_ids):
    '''
    Validates if caller owns the payment methods
    '''
    if payment_method_ids is None:
        raise ValidationError('payment_methods field is required')
    
    try:
        caller = Peer.objects.get(wallet_hash=wallet_hash)
    except Peer.DoesNotExist as err:
        raise ValidationError(err.args[0])

    payment_methods = PaymentMethod.objects.filter(Q(id__in=payment_method_ids))
    for payment_method in payment_methods:
        if payment_method.owner.wallet_hash != caller.wallet_hash:
            raise ValidationError('caller must be owner of payment method')