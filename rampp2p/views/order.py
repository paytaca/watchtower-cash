from rampp2p.serializers.contract import ContractSerializer
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import Http404
from django.core.exceptions import ValidationError
from django.db.models import Q, Value
from django.db import IntegrityError
from django.shortcuts import render
from typing import List
from decimal import Decimal, ROUND_HALF_UP
import math

from rampp2p.utils.utils import get_trading_fees
from rampp2p.utils.transaction import validate_transaction
from rampp2p.utils.websocket import send_order_update
from rampp2p.utils.signature import verify_signature, get_verification_headers
from rampp2p.viewcodes import ViewCode
from rampp2p.permissions import *
from rampp2p.validators import *
from rampp2p.serializers import (
    OrderSerializer, 
    OrderWriteSerializer, 
    StatusSerializer, 
    ContractSerializer,
    TransactionSerializer
)
from rampp2p.models import (
    Ad,
    StatusType,
    Status,
    Order,
    Peer,
    PaymentMethod,
    Contract,
    Transaction,
    PriceType,
    MarketRate
)

import json
import logging
logger = logging.getLogger(__name__)

from django.db.models import (
    OuterRef,
    Subquery
)

class OrderListCreate(APIView):

    def get(self, request):
        try:
            # validate signature
            signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.ORDER_LIST_OWNED.value + '::' + timestamp
            verify_signature(wallet_hash, signature, message)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
        
        order_state = request.query_params.get('state')
        if order_state is None:
            return Response({'error': 'parameter "state" is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            limit = int(request.query_params.get('limit', 0))
            page = int(request.query_params.get('page', 1))
        except ValueError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

        if limit < 0:
            return Response({'error': 'limit must be a non-negative number'}, status=status.HTTP_400_BAD_REQUEST)
        
        if page < 1:
            return Response({'error': 'invalid page number'}, status=status.HTTP_400_BAD_REQUEST)

        # Fetch orders created by user
        owned_orders = Order.objects.filter(owner__wallet_hash=wallet_hash)

        # Fetch orders created for ads owned by user
        ads = list(Ad.objects.filter(owner__wallet_hash=wallet_hash).values_list('id', flat=True))
        ad_orders = Order.objects.filter(ad__pk__in=ads)

        latest_status = Status.objects.filter(
            order=OuterRef('pk'), 
        ).order_by('-created_at')

        owned_orders = owned_orders.annotate(
            last_modified_at=Subquery(
                latest_status.values('created_at')[:1]
            )
        )

        ad_orders = ad_orders.annotate(
            last_modified_at=Subquery(
                latest_status.values('created_at')[:1]
            )
        )

        # Create subquery to filter/exclude completed status
        completed_status = [
            StatusType.CANCELED,
            StatusType.RELEASED,
            StatusType.REFUNDED
        ]

        latest_status = Status.objects.filter(
            order=OuterRef('pk'), 
            status__in=completed_status
        ).order_by('-created_at')

        # Filter or exclude orders according to their latest status
        if order_state == 'COMPLETED':            
            owned_orders = owned_orders.filter(pk__in=Subquery(latest_status.values('order')[:1]))
            ad_orders = ad_orders.filter(pk__in=Subquery(latest_status.values('order')[:1]))
        elif order_state == 'ONGOING':
            owned_orders = owned_orders.exclude(pk__in=Subquery(latest_status.values('order')[:1]))
            ad_orders = ad_orders.exclude(pk__in=Subquery(latest_status.values('order')[:1]))

        # Combine owned and ad orders
        queryset = owned_orders.union(ad_orders)
        queryset = queryset.order_by('-last_modified_at')

        # Count total pages
        count = queryset.count()
        total_pages = page
        if limit > 0:
            total_pages = math.ceil(count / limit)

        # Splice queryset
        offset = (page - 1) * limit
        page_results = queryset[offset:offset + limit]

        context = { 'wallet_hash': wallet_hash }
        serializer = OrderSerializer(page_results, many=True, context=context)
        data = {
            'orders': serializer.data,
            'count': count,
            'total_pages': total_pages
        }
        return Response(data, status.HTTP_200_OK)

    def post(self, request):

        try:
            # validate signature
            signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.ORDER_CREATE.value + '::' + timestamp
            verify_signature(wallet_hash, signature, message)

        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
        
        try:
            ad_id = request.data.get('ad', None)
            if ad_id is None:
                raise ValidationError('ad_id field is required')

            ad = Ad.objects.get(pk=ad_id)
            owner = Peer.objects.get(wallet_hash=wallet_hash)
            payment_method_ids = request.data.get('payment_methods')

            if ad.trade_type == TradeType.SELL:
                # order will inherit ad's payment methods
                payment_methods = ad.payment_methods.all()
                payment_method_ids = list(payment_methods.values_list('id', flat=True))
            else:
                if payment_method_ids is None:
                    raise ValidationError('payment_methods field is required')
                self.validate_payment_methods_ownership(wallet_hash, payment_method_ids)
            
            # validate permissions
            self.validate_permissions(wallet_hash, ad_id)

        except (Ad.DoesNotExist, Peer.DoesNotExist, ValidationError) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        
        # Create the order
        data = request.data.copy()
        data['owner'] = owner.id
        data['crypto_currency'] = ad.crypto_currency.id
        data['fiat_currency'] = ad.fiat_currency.id
        data['time_duration_choice'] = ad.time_duration_choice
        data['payment_methods'] = payment_method_ids

        price = None
        if ad.price_type == PriceType.FLOATING:
            market_price = MarketRate.objects.filter(currency=ad.fiat_currency.symbol)
            if market_price.exists():
                market_price = market_price.first().price
                price = market_price * (ad.floating_price/100)
        else:
            price = ad.fixed_price

        data['locked_price'] = Decimal(price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        serialized_order = OrderWriteSerializer(data=data)

        # return error if order isn't valid
        if not serialized_order.is_valid():
            return Response(serialized_order.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # save order and mark it with status=SUBMITTED
        order = serialized_order.save()
        # order_status = Status.objects.create(
        #     status=StatusType.SUBMITTED,
        #     order=Order.objects.get(pk=order.id)
        # )
        serialized_status = StatusSerializer(
            data={
                'status': StatusType.SUBMITTED,
                'order': order.id
            }
        )

        if serialized_status.is_valid():
            order_status = serialized_status.save()
            serialized_status = StatusSerializer(order_status)
        else:
            return Response(serialized_status.errors, status=status.HTTP_400_BAD_REQUEST)

        context = { 'wallet_hash': wallet_hash }
        serializer = OrderSerializer(order, context=context)        
        response = {
            'success': True,
            'order': serializer.data,
            'status': serialized_status.data
        }
    
        return Response(response, status=status.HTTP_201_CREATED)
    
    def get_contract_params(self, order: Order):

        arbiter_pubkey = order.arbiter.public_key
        seller_pubkey = None
        buyer_pubkey = None
        seller_address = None
        buyer_address = None

        if order.ad.trade_type == TradeType.SELL:
            seller_pubkey = order.ad.owner.public_key
            buyer_pubkey = order.owner.public_key
            seller_address = order.ad.owner.address
            buyer_address = order.owner.address
        else:
            seller_pubkey = order.owner.public_key
            buyer_pubkey = order.ad.owner.public_key
            seller_address = order.owner.address
            buyer_address = order.ad.owner.address

        if (arbiter_pubkey is None or 
            seller_pubkey is None or 
            buyer_pubkey is None or
            seller_address is None or
            buyer_address is None):
            raise ValidationError('contract parameters are required')
        
        params = {
            'arbiter_pubkey': arbiter_pubkey,
            'seller_pubkey': seller_pubkey,
            'buyer_pubkey': buyer_pubkey,
            'seller_address': seller_address,
            'buyer_address': buyer_address,
        }

        return params
    
    def validate_permissions(self, wallet_hash, pk):
        '''
        Ad owners cannot create orders for their ad
        Arbiters cannot create orders
        '''
        try:
            caller = Peer.objects.get(wallet_hash=wallet_hash)
            ad = Ad.objects.get(pk=pk)
        except Peer.DoesNotExist or Ad.DoesNotExist:
            raise ValidationError('peer or ad DoesNotExist')
        
        # if caller.is_arbiter:
        #     raise ValidationError('caller must not be an arbiter')
        
        if ad.owner.wallet_hash == caller.wallet_hash:
            raise ValidationError('ad owner not allowed to create order for this ad')

    def validate_payment_methods_ownership(self, wallet_hash, payment_method_ids: List[int]):
        '''
        Validates if caller owns the payment methods
        '''

        try:
            caller = Peer.objects.get(wallet_hash=wallet_hash)
        except Peer.DoesNotExist:
            raise ValidationError('peer DoesNotExist')

        payment_methods = PaymentMethod.objects.filter(Q(id__in=payment_method_ids))
        for payment_method in payment_methods:
            if payment_method.owner.wallet_hash != caller.wallet_hash:
                raise ValidationError('invalid payment method, not caller owned')

class OrderListStatus(APIView):
  def get(self, request, pk):
    queryset = Status.objects.filter(order=pk)
    serializer = StatusSerializer(queryset, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)

class OrderDetail(APIView):
  def get_object(self, pk):
    try:
      return Order.objects.get(pk=pk)
    except Order.DoesNotExist:
      raise Http404

  def get(self, request, pk):
    order = self.get_object(pk)
    wallet_hash = request.headers.get('wallet_hash')
    if wallet_hash is None:
        return Response({'error': 'wallet_hash is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    context = { 'wallet_hash': wallet_hash }
    response = {
        'order': OrderSerializer(order, context=context).data
    }

    order_contract = Contract.objects.filter(order__pk=pk)
    if order_contract.count() > 0:
        order_contract = order_contract.first()
        response['contract'] = ContractSerializer(order_contract).data
    
    total_fee, fees = get_trading_fees()
    response['fees'] = {
        'total': total_fee,
        'fees': fees
    }

    return Response(response, status=status.HTTP_200_OK)

class ConfirmOrder(APIView):
    '''
    ConfirmOrder creates a status=CONFIRMED for an order. This is callable only by the order's ad owner.
    '''
    def post(self, request, pk):
        try:
            # validate signature
            signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.ORDER_CONFIRM.value + '::' + timestamp
            verify_signature(wallet_hash, signature, message)

            # validate permissions
            self.validate_permissions(wallet_hash, pk)

        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)

        try:
            validate_status(pk, StatusType.SUBMITTED)
            validate_status_inst_count(StatusType.CONFIRMED, pk)
            validate_status_progression(StatusType.CONFIRMED, pk)
                
            # create CONFIRMED status for order
            status_serializer = StatusSerializer(data={
                'status': StatusType.CONFIRMED,
                'order': pk
            })

            if status_serializer.is_valid():
                status_serializer = StatusSerializer(status_serializer.save())
            else: 
                raise ValidationError(f"Encountered error saving status for order#{pk}")

            # notify order update subscribers
            send_order_update(json.dumps(status_serializer.data), pk)
            
        except (ValidationError, IntegrityError) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(status_serializer.data, status=status.HTTP_200_OK)  

    def validate_permissions(self, wallet_hash, pk):
        '''
        Only ad owners can set order status to CONFIRMED
        '''
        try:
            caller = Peer.objects.get(wallet_hash=wallet_hash)
            order = Order.objects.get(pk=pk)
        except (Peer.DoesNotExist, Order.DoesNotExist) as err:
            raise ValidationError(err.args[0])

        if order.ad.owner.wallet_hash != caller.wallet_hash:
            raise ValidationError('caller must be ad owner')

class PendingEscrowOrder(APIView):
    '''
    - EscrowPendingOrder creates a status=ESCROW_PENDING for the order.
    - Listener then waits for the contract address to receive an incoming
    transaction that satisfies the requisites of the contract, at which point the status
    is then automatically set to ESCROWED.    
    - Callable only by the order's seller.
    '''
    def post(self, request, pk):
        try:
            # validate signature
            signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.ORDER_ESCROW_PENDING.value + '::' + timestamp
            verify_signature(wallet_hash, signature, message)

            # validate permissions
            self.validate_permissions(wallet_hash, pk)

        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)

        try:
            validate_status(pk, StatusType.CONFIRMED)
            validate_status_inst_count(StatusType.ESCROW_PENDING, pk)
            validate_status_progression(StatusType.ESCROW_PENDING, pk)

            # create ESCROW_PENDING status for order
            status_serializer = StatusSerializer(data={
                'status': StatusType.ESCROW_PENDING,
                'order': pk
            })

            if status_serializer.is_valid():
                status_serializer = StatusSerializer(status_serializer.save())
            else: 
                raise ValidationError(f"Encountered error saving status for order#{pk}")

            # notify order update subscribers
            send_order_update(json.dumps(status_serializer.data), pk)
            
        except (ValidationError, IntegrityError) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(status_serializer.data, status=status.HTTP_200_OK)  

    def validate_permissions(self, wallet_hash, pk):
        '''
        Only order sellers can set order status to ESCROW_PENDING
        '''
        try:
            caller = Peer.objects.get(wallet_hash=wallet_hash)
            order = Order.objects.get(pk=pk)
        except (Peer.DoesNotExist, Order.DoesNotExist) as err:
            raise ValidationError(err.args[0])
        
        seller = None
        if order.ad.trade_type == TradeType.SELL:
            seller = order.ad.owner
        else:
            seller = order.owner

        if caller.wallet_hash != seller.wallet_hash:
            raise ValidationError('caller must be seller')

class EscrowVerifyOrder(APIView):
    '''
    Manually marks the order as ESCROWED by submitting the transaction id
    for validation (should only be used as fallback when listener fails to update the status 
    after calling ConfirmOrder).
    '''
    def post(self, request, pk):
        try:
            # validate signature
            signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.ORDER_ESCROW_VERIFY.value + '::' + timestamp
            verify_signature(wallet_hash, signature, message)

            # validate permissions
            self.validate_permissions(wallet_hash, pk)

        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)

        try:
            validate_status(pk, StatusType.ESCROW_PENDING)
            validate_status_inst_count(StatusType.ESCROWED, pk)
            validate_status_progression(StatusType.ESCROWED, pk)

            txid = request.data.get('txid')
            if txid is None:
                raise ValidationError('txid is required')
                
            contract = Contract.objects.get(order_id=pk)
            logger.warn('before tx get_or_create')
            transaction, _ = Transaction.objects.get_or_create(
                contract=contract,
                action=Transaction.ActionType.ESCROW,
                txid=txid
            )
            logger.warn('after tx get_or_create')
            validate_transaction(
                txid=transaction.txid,
                action=Transaction.ActionType.ESCROW,
                contract_id=contract.id
            )
            logger.warn('after validation')
        except (ValidationError, Contract.DoesNotExist) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        except IntegrityError as err:
            return Response({'error': 'duplicate txid'}, status=status.HTTP_400_BAD_REQUEST)
        
        serialized_tx = TransactionSerializer(transaction)
        return Response(serialized_tx.data, status=status.HTTP_200_OK)  

    def validate_permissions(self, wallet_hash, pk):
        '''
        Only owners of SELL ads can set order statuses to CONFIRMED.
        Creators of SELL orders skip the order status to CONFIRMED on creation.
        '''

        try:
            caller = Peer.objects.get(wallet_hash=wallet_hash)
            order = Order.objects.get(pk=pk)
        except (Peer.DoesNotExist, Order.DoesNotExist) as err:
            raise ValidationError(err.args[0])

        if order.ad.trade_type == TradeType.SELL:
            seller = order.ad.owner
            # require caller is seller
            if caller.wallet_hash != seller.wallet_hash:
                raise ValidationError('caller must be seller')
        else:
            raise ValidationError('ad trade_type is not {}'.format(TradeType.SELL))
    
class CryptoBuyerConfirmPayment(APIView):
  def post(self, request, pk):

    try:
        # validate signature
        signature, timestamp, wallet_hash = get_verification_headers(request)
        message = ViewCode.ORDER_BUYER_CONF_PAYMENT.value + '::' + timestamp
        verify_signature(wallet_hash, signature, message)

        # validate permissions
        self.validate_permissions(wallet_hash, pk)
    except ValidationError as err:
        return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
    
    try:
        # validations
        validate_status_inst_count(StatusType.PAID_PENDING, pk)
        validate_status_progression(StatusType.PAID_PENDING, pk)
    except ValidationError as err:
      return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

    # create PAID_PENDING status for order
    serializer = StatusSerializer(data={
        'status': StatusType.PAID_PENDING,
        'order': pk
    })

    if serializer.is_valid():
      stat = StatusSerializer(serializer.save())
      return Response(stat.data, status=status.HTTP_200_OK)        
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
  
  def validate_permissions(self, wallet_hash, pk):
    '''
    Only buyers can set order status to PAID_PENDING
    '''

    try:
        caller = Peer.objects.get(wallet_hash=wallet_hash)
        order = Order.objects.get(pk=pk)
    except (Peer.DoesNotExist, Order.DoesNotExist) as err:
        raise ValidationError(err.args[0])
    
    buyer = None
    if order.ad.trade_type == TradeType.SELL:
       buyer = order.owner
    else:
       buyer = order.ad.owner

    if caller.wallet_hash != buyer.wallet_hash:
        raise ValidationError('caller must be buyer')
    
class CryptoSellerConfirmPayment(APIView):
    def post(self, request, pk):
        
        try:
            # validate signature
            signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.ORDER_SELLER_CONF_PAYMENT.value + '::' + timestamp
            verify_signature(wallet_hash, signature, message)

            # validate permissions
            self.validate_permissions(wallet_hash, pk)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
        
        try:
            # status validations
            validate_status_inst_count(StatusType.PAID, pk)
            validate_status_progression(StatusType.PAID, pk)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

        # create PAID status for order
        serializer = StatusSerializer(data={
            'status': StatusType.PAID,
            'order': pk
        })

        if serializer.is_valid():
            stat = StatusSerializer(serializer.save())
            return Response(stat.data, status=status.HTTP_200_OK)        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
  
    def validate_permissions(self, wallet_hash, pk):
        '''
        Only the seller can set the order status to PAID
        '''
        try:
            caller = Peer.objects.get(wallet_hash=wallet_hash)
            order = Order.objects.get(pk=pk)
        except (Peer.DoesNotExist, Order.DoesNotExist) as err:
            raise ValidationError(err.args[0])
        
        seller = None
        if order.ad.trade_type == TradeType.SELL:
            seller = order.ad.owner
        else:
            seller = order.owner

        if caller.wallet_hash != seller.wallet_hash:
            raise ValidationError('caller must be seller')

class CancelOrder(APIView):
    def post(self, request, pk):

        try:
            # validate signature
            signature, timestamp, wallet_hash = get_verification_headers(request)
            message = ViewCode.ORDER_CANCEL.value + '::' + timestamp
            verify_signature(wallet_hash, signature, message)

            # validate permissions
            self.validate_permissions(wallet_hash, pk)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)

        try:
            # status validations
            validate_status_inst_count(StatusType.CANCELED, pk)
            validate_status_progression(StatusType.CANCELED, pk)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

        # create CANCELED status for order
        serializer = StatusSerializer(data={
            'status': StatusType.CANCELED,
            'order': pk
        })

        if serializer.is_valid():
            stat = StatusSerializer(serializer.save())
            return Response(stat.data, status=status.HTTP_200_OK)        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def validate_permissions(self, wallet_hash, pk):
        '''
        CancelOrder is callable by the order/ad owner.
        '''
        try:
            caller = Peer.objects.get(wallet_hash=wallet_hash)
            order = Order.objects.get(pk=pk)
        except (Peer.DoesNotExist, Order.DoesNotExist) as err:
            raise ValidationError(err.args[0])
        
        order_owner = order.owner.wallet_hash
        ad_owner = order.ad.owner.wallet_hash
        if caller.wallet_hash != order_owner and caller.wallet_hash != ad_owner:
           raise ValidationError('caller must be order/ad owner')
