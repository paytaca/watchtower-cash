from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import Http404
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.db import IntegrityError
from typing import List
from decimal import Decimal, ROUND_HALF_UP
import math

from rampp2p.utils.utils import get_trading_fees, get_latest_status
from rampp2p.utils.transaction import validate_transaction
from rampp2p.utils.websocket import send_order_update
from rampp2p.utils.signature import verify_signature, get_verification_headers
from rampp2p.viewcodes import ViewCode
from rampp2p.validators import *
from rampp2p.serializers import (
    OrderSerializer, 
    OrderWriteSerializer, 
    StatusSerializer, 
    StatusReadSerializer,
    ContractDetailSerializer,
    TransactionSerializer,
    AppealSerializer
)
from rampp2p.models import (
    Ad,
    AdSnapshot,
    StatusType,
    Status,
    Order,
    Peer,
    PaymentMethod,
    Contract,
    Transaction,
    PriceType,
    MarketRate,
    Appeal,
    TradeType
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
            message = ViewCode.ORDER_LIST.value + '::' + timestamp
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
        ad_orders = Order.objects.filter(ad_snapshot__ad__pk__in=ads)

        latest_status = Status.objects.filter(
            order=OuterRef('pk'), 
        ).order_by('-created_at')

        order_by = request.query_params.get('order_by')
        if order_by == 'last_modified':
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
        if order_by == 'last_modified':
            queryset = queryset.order_by('-last_modified_at')
        else:
            if order_state == 'ONGOING':
                queryset = queryset.order_by('-created_at')
            if order_state == 'COMPLETED':
                queryset = queryset.order_by('-created_at')
        
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
            
            crypto_amount = request.data.get('crypto_amount')
            if crypto_amount is None:
                raise ValidationError('crypto_amount field is required')

            ad = Ad.objects.get(pk=ad_id)
            owner = Peer.objects.get(wallet_hash=wallet_hash)
            payment_method_ids = request.data.get('payment_methods', [])

            if ad.trade_type == TradeType.BUY:
                if len(payment_method_ids) == 0:
                    raise ValidationError('payment_methods field is required')            
                self.validate_payment_methods_ownership(wallet_hash, payment_method_ids)
            
            # validate permissions
            self.validate_permissions(wallet_hash, ad_id)

            market_price = MarketRate.objects.filter(currency=ad.fiat_currency.symbol)
            if not market_price.exists():
                raise ValidationError(f'market price for currency {ad.fiat_currency.symbol} does not exist.')
            market_price = market_price.first()

        except (Ad.DoesNotExist, Peer.DoesNotExist, ValidationError) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

        # Create snapshot of ad
        ad_snapshot = AdSnapshot(
            ad = ad,
            trade_type = ad.trade_type,
            price_type = ad.price_type,
            fiat_currency = ad.fiat_currency,
            crypto_currency = ad.crypto_currency,
            fixed_price = ad.fixed_price,
            floating_price = ad.floating_price,
            market_price = market_price.price,
            trade_floor = ad.trade_floor,
            trade_ceiling = ad.trade_ceiling,
            trade_amount = ad.trade_amount,
            time_duration_choice = ad.time_duration_choice,
        )
        ad_snapshot.save()
        ad_snapshot.payment_methods.set(ad.payment_methods.all())

        # Create the order
        data = {
            'owner': owner.id,
            'ad_snapshot': ad_snapshot.id,
            'crypto_currency': ad_snapshot.crypto_currency.id,
            'fiat_currency': ad_snapshot.fiat_currency.id,
            'time_duration_choice': ad_snapshot.time_duration_choice,
            'payment_methods': payment_method_ids,
            'crypto_amount': crypto_amount
        }

        price = None
        if ad_snapshot.price_type == PriceType.FLOATING:
            market_price = market_price.price
            price = market_price * (ad_snapshot.floating_price/100)
        else:
            price = ad_snapshot.fixed_price

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

        if order.ad_snapshot.trade_type == TradeType.SELL:
            seller_pubkey = order.ad_snapshot.ad.owner.public_key
            buyer_pubkey = order.owner.public_key
            seller_address = order.ad_snapshot.ad.owner.address
            buyer_address = order.owner.address
        else:
            seller_pubkey = order.owner.public_key
            buyer_pubkey = order.ad_snapshot.ad.owner.public_key
            seller_address = order.owner.address
            buyer_address = order.ad_snapshot.ad.owner.address

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
    serialized_order = OrderSerializer(order, context=context).data
    response = {
        'order': serialized_order
    }

    order_contract = Contract.objects.filter(order__pk=pk)
    if order_contract.count() > 0:
        order_contract = order_contract.first()
        # serialized_contract = None
        # serialized_transactions = None
        # if (serialized_order['status']['value'] == StatusType.CONFIRMED or
        #     serialized_order['status']['value'] == StatusType.PAID):
        serialized_contract = ContractDetailSerializer(order_contract).data
        contract_txs = Transaction.objects.filter(contract__id=order_contract.id)
        serialized_transactions = TransactionSerializer(contract_txs, many=True).data
        
        response['contract'] = serialized_contract
        response['contract']['transactions'] = serialized_transactions
    
    if serialized_order['status']['value'] == StatusType.APPEALED:
        appeal = Appeal.objects.filter(order_id=order.id)
        if appeal.exists():
            serialized_appeal = AppealSerializer(appeal.first()).data
            # response['appeal'] = serialized_appeal
            response['appeal'] = {
                'id': serialized_appeal['id'],
                'type': serialized_appeal['type'],
                'reasons': serialized_appeal['reasons'],
                'resolved_at': serialized_appeal['resolved_at'],
                'created_at': serialized_appeal['created_at']
            }

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

            order = Order.objects.get(pk=pk)
            trade_amount = order.ad_snapshot.ad.trade_amount - order.crypto_amount
            if trade_amount < 0:
                raise ValidationError('crypto_amount exceeds ad remaining trade_amount')
            
            # Update Ad trade_amount
            ad = Ad.objects.get(pk=order.ad_snapshot.ad.id)
            ad.trade_amount = trade_amount
            ad.save()
                
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
            
        except (ValidationError, IntegrityError, Order.DoesNotExist, Ad.DoesNotExist) as err:
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

        if order.ad_snapshot.ad.owner.wallet_hash != caller.wallet_hash:
            raise ValidationError('caller must be ad owner')

class PendingEscrowOrder(APIView):
    '''
    EscrowPendingOrder creates a status=ESCROW_PENDING for the given order.
    If transaction id is given, it is sent to a task queue for validation, if valid, 
    the order status is set to ESCROWED automatically.
    Callable only by the order's seller.
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

            txid = request.data.get('txid')
            if txid is None:
                raise ValidationError('txid is required')

            contract = Contract.objects.get(order__id=pk)
            
            # create ESCROW_PENDING status for order
            status_serializer = StatusSerializer(data={
                'status': StatusType.ESCROW_PENDING,
                'order': pk
            })

            if status_serializer.is_valid():
                status_serializer = StatusReadSerializer(status_serializer.save())
            else: 
                raise ValidationError(f"Encountered error saving status for order#{pk}")

            # notify order update subscribers
            result = {
                'success' : True,
                'txid': txid,
                'status': status_serializer.data
            }

            transaction, _ = Transaction.objects.get_or_create(
                contract=contract,
                action=Transaction.ActionType.ESCROW,
                txid=txid
            )
            result['transaction'] = TransactionSerializer(transaction).data

            # Validate the transaction
            validate_transaction(
                txid=transaction.txid,
                action=Transaction.ActionType.ESCROW,
                contract_id=contract.id
            )
            send_order_update(result, pk)
            
        except (ValidationError, IntegrityError, Contract.DoesNotExist) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_200_OK)  

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
        if order.ad_snapshot.trade_type == TradeType.SELL:
            seller = order.ad_snapshot.ad.owner
        else:
            seller = order.owner

        if caller.wallet_hash != seller.wallet_hash:
            raise ValidationError('caller must be seller')

class VerifyEscrow(APIView):
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
            transaction, _ = Transaction.objects.get_or_create(
                contract=contract,
                action=Transaction.ActionType.ESCROW,
                txid=txid
            )

            # Validate the transaction
            validate_transaction(
                txid=transaction.txid,
                action=Transaction.ActionType.ESCROW,
                contract_id=contract.id
            )
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

        if order.ad_snapshot.trade_type == TradeType.SELL:
            seller = order.ad_snapshot.ad.owner
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
        order = Order.objects.get(pk=pk)
        self.validate_permissions(wallet_hash, order)

    except ValidationError as err:
        return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)
    except Order.DoesNotExist as err:
        return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # validations
        validate_status_inst_count(StatusType.PAID_PENDING, pk)
        validate_status_progression(StatusType.PAID_PENDING, pk)
    except ValidationError as err:
      return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
    
    payment_method_ids = request.data.get('payment_methods')
    if payment_method_ids is None or len(payment_method_ids) == 0:
        return Response({'error': 'payment_methods field is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    payment_methods = PaymentMethod.objects.filter(id__in=payment_method_ids)
    order.payment_methods.add(*payment_methods)
    order.save()    

    context = { 'wallet_hash': wallet_hash }
    serialized_order = OrderSerializer(order, context=context)

    # create PAID_PENDING status for order
    serialized_status = StatusSerializer(data={
        'status': StatusType.PAID_PENDING,
        'order': pk
    })

    if not serialized_status.is_valid():
        return Response(serialized_status.errors, status=status.HTTP_400_BAD_REQUEST)
    
    serialized_status = StatusReadSerializer(serialized_status.save())
    result = {
        'success' : True,
        'status': serialized_status.data
    }
    
    send_order_update(result, pk)
    response = {
        "order": serialized_order.data,
        "status": serialized_status.data
    }
    return Response(response, status=status.HTTP_200_OK)    
  
  def validate_permissions(self, wallet_hash, order):
    '''
    Only buyers can set order status to PAID_PENDING
    '''

    try:
        caller = Peer.objects.get(wallet_hash=wallet_hash)
    except Peer.DoesNotExist as err:
        raise ValidationError(err.args[0])
    
    buyer = None
    if order.ad_snapshot.trade_type == TradeType.SELL:
       buyer = order.owner
    else:
       buyer = order.ad_snapshot.ad.owner

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
        serialized_status = StatusSerializer(data={
            'status': StatusType.PAID,
            'order': pk
        })

        if serialized_status.is_valid():
            serialized_status = StatusReadSerializer(serialized_status.save())
            result = {
                'success' : True,
                'status': serialized_status.data
            }
            send_order_update(result, pk)
            return Response(serialized_status.data, status=status.HTTP_200_OK)        
        return Response(serialized_status.errors, status=status.HTTP_400_BAD_REQUEST)
  
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
        if order.ad_snapshot.trade_type == TradeType.SELL:
            seller = order.ad_snapshot.ad.owner
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

        # Update Ad trade_amount if order was CONFIRMED
        order = Order.objects.get(pk=pk)
        latest_status = get_latest_status(order.id)
        # Update Ad trade_amount
        if latest_status.status == StatusType.CONFIRMED:
            trade_amount = order.ad_snapshot.ad.trade_amount + order.crypto_amount        
            ad = Ad.objects.get(pk=order.ad_snapshot.ad.id)
            ad.trade_amount = trade_amount
            ad.save()
            
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
        ad_owner = order.ad_snapshot.ad.owner.wallet_hash
        if caller.wallet_hash != order_owner and caller.wallet_hash != ad_owner:
           raise ValidationError('caller must be order/ad owner')
