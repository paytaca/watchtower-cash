from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response

from django.http import Http404
from django.db import IntegrityError
from django.db.models import Q, OuterRef, Subquery
from django.core.exceptions import ValidationError

import math
from typing import List
from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone

from authentication.token import TokenAuthentication
from main.utils.subscription import save_subscription

import rampp2p.utils.websocket as websocket
from rampp2p.utils.utils import get_trading_fees, get_latest_status
from rampp2p.utils.transaction import validate_transaction
from rampp2p.utils.notifications import send_push_notification
from rampp2p.validators import *
import rampp2p.serializers as serializers
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
import rampp2p.models as models

import logging
logger = logging.getLogger(__name__)

class OrderListCreate(APIView):
    authentication_classes = [TokenAuthentication]

    def unwrap_request(self, request):
        limit = request.query_params.get('limit', 0)
        page = request.query_params.get('page', 1)
        status_type = request.query_params.get('status_type')
        currency = request.query_params.get('currency')
        trade_type = request.query_params.get('trade_type')
        filtered_status = request.query_params.getlist('status')
        payment_types = request.query_params.getlist('payment_types')
        time_limits = request.query_params.getlist('time_limits')
        sort_by = request.query_params.get('sort_by')
        sort_type = request.query_params.get('sort_type')
        owned = request.query_params.get('owned')
        expired_only = request.query_params.get('expired_only')
        if owned is not None:
            owned = owned == 'true'
        if expired_only is not None:
            expired_only = expired_only == 'true'

        return {
            'limit': limit,
            'page': page,
            'status_type': status_type,
            'currency': currency,
            'trade_type': trade_type,
            'filtered_status': filtered_status,
            'payment_types': payment_types,
            'time_limits': time_limits,
            'sort_by': sort_by,
            'sort_type': sort_type,
            'owned': owned,
            'expired_only': expired_only
        }

    def get(self, request):
        wallet_hash = request.user.wallet_hash
        params = self.unwrap_request(request=request)

        if params['status_type'] is None:
            return Response(
                {'error': 'parameter status_type is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            limit = int(params['limit'])
            page = int(params['page'])
            if limit < 0:
                raise ValidationError('limit must be a non-negative number')
            if page < 1:
                raise ValidationError('invalid page number')
        except (ValueError, ValidationError) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

        queryset = Order.objects.all()

        # fetches orders created by user
        owned_orders = Q(owner__wallet_hash=wallet_hash)

        # fetches the orders that have ad ids owned by user
        ad_orders = Q(ad_snapshot__ad__pk__in=list(
                        # fetches the flat ids of ads owned by user
                        Ad.objects.filter(
                            owner__wallet_hash=wallet_hash
                        ).values_list('id', flat=True)
                    ))
                    
        if params['owned'] == True:
            queryset = queryset.filter(owned_orders)
        elif params['owned'] == False:
            queryset = queryset.filter(ad_orders)
        else:
            queryset = queryset.filter(owned_orders | ad_orders)

        # filter or exclude orders based to their latest status
        completed_status = [
            StatusType.CANCELED,
            StatusType.RELEASED,
            StatusType.REFUNDED
        ]
        last_status = Status.objects.filter(
            order=OuterRef('pk'),
            status__in=completed_status
        ).order_by('-created_at').values('order')[:1]

        if params['status_type'] == 'COMPLETED':            
            queryset = queryset.filter(pk__in=Subquery(last_status))
        elif params['status_type'] == 'ONGOING':
            queryset = queryset.exclude(pk__in=Subquery(last_status))
        
        if len(params['filtered_status']) > 0:
            filtered_status = Status.objects.filter(
                order=OuterRef('pk'),
                status__in=list(map(str, params['filtered_status']))
            ).order_by('-created_at').values('order')[:1]
            queryset = queryset.filter(pk__in=Subquery(filtered_status))

        # filters by ad payment types
        if len(params['payment_types']) > 0:
            payment_types = list(map(int, params['payment_types']))
            queryset = queryset.filter(ad_snapshot__payment_methods__payment_type__id__in=payment_types).distinct()

        # filters by ad time limits
        if len(params['time_limits']) > 0:
            time_limits = list(map(int, params['time_limits']))
            queryset = queryset.filter(ad_snapshot__time_duration_choice__in=time_limits).distinct()

        # filters by order trade type
        if params['trade_type'] is not None:
            queryset = queryset.exclude(Q(ad_snapshot__trade_type=params['trade_type']))

        # filters expired orders only
        if params['expired_only'] is True:
            queryset = queryset.filter(Q(expires_at__isnull=False) & Q(expires_at__lt=timezone.now()))

        if params['sort_by'] == 'last_modified_at':
            sort_field = 'last_modified_at'
            if params['sort_type'] == 'descending':
                sort_field = f'-{sort_field}'
            last_status_created_at = Status.objects.filter(
                order=OuterRef('pk')).order_by('-created_at').values('created_at')[:1]
            queryset = queryset.annotate(
                last_modified_at=Subquery(last_status_created_at)
            ).order_by(sort_field)
        else:
            sort_field = 'created_at'
            if (params['sort_type'] == 'descending'):
                sort_field = f'-{sort_field}'
            if params['status_type'] == 'ONGOING':
                queryset = queryset.order_by(sort_field)
            if params['status_type'] == 'COMPLETED':
                queryset = queryset.order_by(sort_field)
        
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
        wallet_hash = request.user.wallet_hash
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

            crypto_amount = Decimal(crypto_amount)
            if crypto_amount < ad.trade_floor or crypto_amount > ad.trade_amount or crypto_amount > ad.trade_ceiling:
                raise ValidationError('crypto_amount exceeds trade limits')

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
        serialized_status = StatusSerializer(
            data={
                'status': StatusType.SUBMITTED,
                'order': order.id
            }
        )

        if serialized_status.is_valid():
            order_status = serialized_status.save()
            serialized_status = StatusSerializer(order_status).data
        else:
            return Response(serialized_status.errors, status=status.HTTP_400_BAD_REQUEST)

        context = { 'wallet_hash': wallet_hash }
        serialized_order = OrderSerializer(order, context=context).data    
        response = {
            'success': True,
            'order': serialized_order,
            'status': serialized_status
        }

        # send push notification
        extra = {'order_id': serialized_order['id']}
        send_push_notification([ad.owner.wallet_hash], "Received new order", extra=extra)
    
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

class OrderMembers(APIView):
    authentication_classes = [TokenAuthentication]
    def get(self, _, pk):
        try:
            order = Order.objects.get(pk=pk)
            members = [order.owner, order.ad_snapshot.ad.owner]
            if order.arbiter:
                members.append(order.arbiter)

            member_info = []
            for member in members:
                member_info.append({
                    'id': member.id,
                    'chat_identity_id': member.chat_identity_id,
                    'public_key': member.public_key,
                    'name': member.name,
                    'address': member.address,
                    'is_arbiter': isinstance(member, models.Arbiter)
                })
            
            members = serializers.OrderMemberSerializer(member_info, many=True)
        except Order.DoesNotExist:
            raise Http404
        except Exception as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        return Response(members.data, status=status.HTTP_200_OK)

class OrderListStatus(APIView):
    authentication_classes = [TokenAuthentication]
    def get(self, request, pk):
        queryset = Status.objects.filter(order=pk)
        serializer = StatusSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class OrderDetail(APIView):
    authentication_classes = [TokenAuthentication]

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
        
        if serialized_order['status']['value'] == StatusType.APPEALED:
            appeal = Appeal.objects.filter(order_id=order.id)
            if appeal.exists():
                serialized_appeal = AppealSerializer(appeal.first()).data
                serialized_order['appeal'] = serialized_appeal
                # serialized_order['appeal'] = {
                #     'id': serialized_appeal['id'],
                #     'type': serialized_appeal['type'],
                #     'reasons': serialized_appeal['reasons'],
                #     'resolved_at': serialized_appeal['resolved_at'],
                #     'created_at': serialized_appeal['created_at']
                # }
        return Response(serialized_order, status=status.HTTP_200_OK)

class ConfirmOrder(APIView):
    authentication_classes = [TokenAuthentication]

    '''
    ConfirmOrder creates a status=CONFIRMED for an order. 
    This is callable only by the order's ad owner.
    '''
    def post(self, request, pk):
        wallet_hash = request.user.wallet_hash
        try:
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

        except (ValidationError, IntegrityError, Order.DoesNotExist, Ad.DoesNotExist) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
                
        serialized_status = StatusSerializer(data={
            'status': StatusType.CONFIRMED,
            'order': pk
        })

        if serialized_status.is_valid():
            serialized_status = StatusReadSerializer(serialized_status.save())
            
            # send websocket notification
            websocket.send_order_update({
                'success': True,
                'status': serialized_status.data
            }, pk)
            
            # send push notification
            message = f'Order {order.id} confirmed'
            send_push_notification([order.owner.wallet_hash], message, extra={'order_id': order.id})
            
            return Response(serialized_status.data, status=status.HTTP_200_OK)
        return Response(serialized_status.errors, status=status.HTTP_400_BAD_REQUEST)

    def validate_permissions(self, wallet_hash, pk):
        '''
        Only ad owners can set order status to CONFIRMED
        '''
        try:
            order = Order.objects.get(pk=pk)
        except Order.DoesNotExist as err:
            raise ValidationError(err.args[0])

        if order.ad_snapshot.ad.owner.wallet_hash != wallet_hash:
            raise ValidationError('Caller must be ad owner.')

class PendingEscrowOrder(APIView):
    authentication_classes = [TokenAuthentication]

    '''
    EscrowPendingOrder creates a status=ESCROW_PENDING for the given order.
    If transaction id is given, it is sent to a task queue for validation, if valid, 
    the order status is set to ESCROWED automatically.
    Callable only by the order's seller.
    '''
    def post(self, request, pk):
        try:
            self.validate_permissions(request.user.wallet_hash, pk)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_403_FORBIDDEN)

        try:
            validate_status(pk, StatusType.CONFIRMED)
            validate_status_inst_count(StatusType.ESCROW_PENDING, pk)
            validate_status_progression(StatusType.ESCROW_PENDING, pk)

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
            websocket_msg = {
                'success' : True,
                'status': status_serializer.data
            }

            transaction, _ = Transaction.objects.get_or_create(
                contract=contract,
                action=Transaction.ActionType.ESCROW,
            )
            websocket_msg['transaction'] = TransactionSerializer(transaction).data

            # Subscribe to contract address
            created = save_subscription(contract.address, contract.id)
            if created: logger.warn(f'Subscribed to contract {contract.address}')
            websocket_msg['subscribed'] = created
            
            websocket.send_order_update(websocket_msg, pk)
            response = websocket_msg
            
        except (ValidationError, IntegrityError, Contract.DoesNotExist) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        return Response(response, status=status.HTTP_200_OK)  

    def validate_permissions(self, wallet_hash, pk):
        '''
        Only order sellers can set order status to ESCROW_PENDING
        '''
        try:
            order = Order.objects.get(pk=pk)
        except Order.DoesNotExist as err:
            raise ValidationError(err.args[0])
        
        seller = None
        if order.ad_snapshot.trade_type == TradeType.SELL:
            seller = order.ad_snapshot.ad.owner
        else:
            seller = order.owner

        if wallet_hash != seller.wallet_hash:
            raise ValidationError('Caller must be seller.')

class VerifyEscrow(APIView):
    authentication_classes = [TokenAuthentication]

    '''
    Manually marks the order as ESCROWED by submitting the transaction id
    for validation (should only be used as fallback when listener fails to update the status 
    after calling ConfirmOrder).
    '''
    def post(self, request, pk):
        try:
            self.validate_permissions(request.user.wallet_hash, pk)
        except ValidationError as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_status(pk, StatusType.ESCROW_PENDING)
            validate_status_inst_count(StatusType.ESCROWED, pk)
            validate_status_progression(StatusType.ESCROWED, pk)

            txid = request.data.get('txid')
            if txid is None:
                raise ValidationError('txid is required')
                
            contract = Contract.objects.get(order_id=pk)

            # Validate the transaction
            validate_transaction(txid, Transaction.ActionType.ESCROW, contract.id)

        except (ValidationError, Contract.DoesNotExist) as err:
            return Response({'error': err.args[0]}, status=status.HTTP_400_BAD_REQUEST)
        except IntegrityError as err:
            return Response({'error': 'duplicate txid'}, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(status=status.HTTP_200_OK)  

    def validate_permissions(self, wallet_hash, pk):
        '''
        Only SELLERS can verify the ESCROW status of order.
        '''

        try:
            order = Order.objects.get(pk=pk)
        except Order.DoesNotExist as err:
            raise ValidationError(err.args[0])

        if order.ad_snapshot.trade_type == TradeType.SELL:
            seller = order.ad_snapshot.ad.owner
        else:
            seller = order.owner
        
        # Caller must be seller
        if wallet_hash != seller.wallet_hash:
            raise ValidationError('Caller is not seller')
    
class CryptoBuyerConfirmPayment(APIView):
    authentication_classes = [TokenAuthentication]

    def post(self, request, pk):
        wallet_hash = request.user.wallet_hash
        try:
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

        if serialized_status.is_valid():            
            serialized_status = StatusReadSerializer(serialized_status.save())
            websocket.send_order_update({
                'success' : True,
                'status': serialized_status.data
            }, pk)
            response = {
                "order": serialized_order.data,
                "status": serialized_status.data
            }
            return Response(response, status=status.HTTP_200_OK)
        return Response(serialized_status.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def validate_permissions(self, wallet_hash, order):
        '''
        Only buyers can set order status to PAID_PENDING
        '''        
        buyer = None
        if order.ad_snapshot.trade_type == TradeType.SELL:
            buyer = order.owner
        else:
            buyer = order.ad_snapshot.ad.owner

        if wallet_hash != buyer.wallet_hash:
            raise ValidationError('caller must be buyer')
    
class CryptoSellerConfirmPayment(APIView):
    authentication_classes = [TokenAuthentication]

    def post(self, request, pk):
        wallet_hash = request.user.wallet_hash
        try:
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

            contract = Contract.objects.get(order__id=pk)
            _, _ = Transaction.objects.get_or_create(
                contract=contract,
                action=Transaction.ActionType.RELEASE,
            )

            websocket.send_order_update({
                'success' : True,
                'status': serialized_status.data
            }, pk)
            return Response(serialized_status.data, status=status.HTTP_200_OK)        
        return Response(serialized_status.errors, status=status.HTTP_400_BAD_REQUEST)
  
    def validate_permissions(self, wallet_hash, pk):
        '''
        Only the seller can set the order status to PAID
        '''
        try:
            order = Order.objects.get(pk=pk)
        except Order.DoesNotExist as err:
            raise ValidationError(err.args[0])
        
        seller = None
        if order.ad_snapshot.trade_type == TradeType.SELL:
            seller = order.ad_snapshot.ad.owner
        else:
            seller = order.owner

        if wallet_hash != seller.wallet_hash:
            raise ValidationError('Caller must be seller')

class CancelOrder(APIView):
    authentication_classes = [TokenAuthentication]
        
    def post(self, request, pk):
        wallet_hash = request.user.wallet_hash
        try:
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
            serialized_status = StatusReadSerializer(serializer.save())
            websocket_msg = {
                'success' : True,
                'status': serialized_status.data
            }
            websocket.send_order_update(websocket_msg, pk)
            return Response(serialized_status.data, status=status.HTTP_200_OK)        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def validate_permissions(self, wallet_hash, pk):
        '''
        CancelOrder is callable by the order/ad owner.
        '''
        try:
            order = Order.objects.get(pk=pk)
        except Order.DoesNotExist as err:
            raise ValidationError(err.args[0])
        
        order_owner = order.owner.wallet_hash
        ad_owner = order.ad_snapshot.ad.owner.wallet_hash
        if wallet_hash != order_owner and wallet_hash != ad_owner:
           raise ValidationError('caller must be order/ad owner')
